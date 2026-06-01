"""Department routing API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.routing.serializers import (
    RoutingInboxQuerySerializer,
    RoutingPolicyCreateSerializer,
    RoutingPolicyPatchSerializer,
    RoutingPolicyQuerySerializer,
    RoutingRecordPatchSerializer,
)
from application.services.audit_log import record_audit_log
from application.services.company_access import accessible_company_queryset
from application.services.departments import can_mutate_department_work, has_department_role
from application.services.rbac import has_min_role
from application.services.routing import (
    RoutingError,
    create_or_update_routing_policy,
    list_inbox_for_user,
    mark_routing_record_status,
    routing_policy_payload,
    routing_record_payload,
)
from infrastructure.orm.models import (
    DepartmentRegistry,
    Graph,
    RoutingPolicy,
    TaskRoutingRecord,
    User,
)


class RoutingPolicyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = RoutingPolicyQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        organization = user.default_organization
        if organization is None:
            return success_response({"policies": []})
        queryset = RoutingPolicy.objects.filter(organization=organization).select_related(
            "company",
            "department",
            "fallback_department",
        )
        if not has_min_role(user, "admin", str(organization.id)):
            queryset = queryset.filter(department__in=_lead_departments_for_user(user))
        department_id = serializer.validated_data.get("department_id")
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        company_id = serializer.validated_data.get("company_id")
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if "active" in serializer.validated_data:
            queryset = queryset.filter(active=serializer.validated_data["active"])
        return success_response(
            {
                "policies": [
                    routing_policy_payload(policy) for policy in queryset.order_by("-updated_at")
                ]
            }
        )

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = RoutingPolicyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        resolved = _resolve_policy_refs(user, serializer.validated_data)
        if isinstance(resolved, Response):
            return resolved
        company, department, fallback_department = resolved
        if not _can_manage_policy(user=user, company=company, department=department):
            return _forbidden("You do not have permission to manage routing policies.")
        try:
            policy = create_or_update_routing_policy(
                organization=department.organization,
                company=company,
                department=department,
                trigger_type=str(serializer.validated_data.get("trigger_type") or ""),
                event_type=str(serializer.validated_data.get("event_type") or ""),
                service_type=str(serializer.validated_data.get("service_type") or ""),
                channel=str(serializer.validated_data.get("channel") or ""),
                signal_type=str(serializer.validated_data.get("signal_type") or ""),
                entry_conditions=dict(serializer.validated_data.get("entry_conditions") or {}),
                priority_rules=dict(serializer.validated_data.get("priority_rules") or {}),
                sla=dict(serializer.validated_data.get("sla") or {}),
                required_approval_types=list(
                    serializer.validated_data.get("required_approval_types") or []
                ),
                fallback_department=fallback_department,
                active=bool(serializer.validated_data.get("active", True)),
                metadata=dict(serializer.validated_data.get("metadata") or {}),
                created_by=user,
            )
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        except IntegrityError:
            return error_response(
                "ROUTING_POLICY_CREATE_FAILED",
                "Routing policy could not be created.",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(policy.organization_id),
            action="routing_policy.created",
            resource_type="routing_policy",
            resource_id=str(policy.id),
            metadata={
                "department_id": str(policy.department_id),
                "company_id": str(policy.company_id) if policy.company_id else None,
            },
        )
        return success_response(
            {"policy": routing_policy_payload(policy)},
            status=http_status.HTTP_201_CREATED,
        )


class RoutingPolicyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, policy_id: UUID) -> Response:
        user = cast(User, request.user)
        policy = _policy_for_user(user, policy_id)
        if policy is None:
            return _not_found("Routing policy was not found.")
        serializer = RoutingPolicyPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = dict(serializer.validated_data)
        resolved = _resolve_policy_refs(
            user,
            {
                "company_id": data.get("company_id", policy.company_id),
                "department_id": data.get("department_id", policy.department_id),
                "fallback_department_id": data.get(
                    "fallback_department_id",
                    policy.fallback_department_id,
                ),
            },
        )
        if isinstance(resolved, Response):
            return resolved
        company, department, fallback_department = resolved
        if not _can_manage_policy(user=user, company=company, department=department):
            return _forbidden("You do not have permission to manage routing policies.")
        update_fields = ["updated_at"]
        policy.company = company
        policy.department = department
        policy.fallback_department = fallback_department
        update_fields.extend(["company", "department", "fallback_department"])
        field_map = {
            "trigger_type": "trigger_type",
            "event_type": "event_type",
            "service_type": "service_type",
            "channel": "channel",
            "signal_type": "signal_type",
            "active": "active",
        }
        for input_key, attr in field_map.items():
            if input_key in data:
                setattr(policy, attr, data[input_key])
                update_fields.append(attr)
        for input_key, attr, caster in (
            ("entry_conditions", "entry_conditions_json", dict),
            ("priority_rules", "priority_rules_json", dict),
            ("sla", "sla_json", dict),
            ("required_approval_types", "required_approval_types_json", list),
            ("metadata", "metadata_json", dict),
        ):
            if input_key in data:
                setattr(policy, attr, caster(data.get(input_key) or caster()))
                update_fields.append(attr)
        try:
            policy.full_clean()
            policy.save(update_fields=sorted(set(update_fields)))
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        record_audit_log(
            actor=user,
            tenant_id=str(policy.organization_id),
            action="routing_policy.updated",
            resource_type="routing_policy",
            resource_id=str(policy.id),
            metadata={
                "department_id": str(policy.department_id),
                "company_id": str(policy.company_id) if policy.company_id else None,
            },
        )
        return success_response({"policy": routing_policy_payload(policy)})


class RoutingInboxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = RoutingInboxQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        records = list_inbox_for_user(
            user=user,
            department_id=serializer.validated_data.get("department_id"),
            company_id=serializer.validated_data.get("company_id"),
            status=str(serializer.validated_data.get("status") or ""),
        )
        return success_response(
            {
                "items": [
                    routing_record_payload(record)
                    for record in records.order_by("due_at", "-created_at")
                ]
            }
        )


class RoutingRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, record_id: UUID) -> Response:
        user = cast(User, request.user)
        record = _routing_record_for_user(user, record_id)
        if record is None:
            return _not_found("Routing record was not found.")
        serializer = RoutingRecordPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        assigned_user = None
        assigned_user_id = serializer.validated_data.get("assigned_user_id")
        if assigned_user_id:
            assigned_user = User.objects.filter(id=assigned_user_id).first()
            if assigned_user is None:
                return _not_found("Assigned user was not found.")
        try:
            updated = mark_routing_record_status(
                user=user,
                record=record,
                status=str(serializer.validated_data["status"]),
                assigned_user=assigned_user,
                resolution=dict(serializer.validated_data.get("resolution") or {}),
            )
        except RoutingError as exc:
            status_code = (
                http_status.HTTP_403_FORBIDDEN
                if exc.code == "permission_denied"
                else http_status.HTTP_400_BAD_REQUEST
            )
            return error_response(
                exc.code.upper(),
                exc.message,
                status=status_code,
                details=exc.details,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(updated.organization_id),
            action="routing_record.updated",
            resource_type="task_routing_record",
            resource_id=str(updated.id),
            metadata={"status": updated.status, "department_id": str(updated.to_department_id)},
        )
        return success_response({"routing_record": routing_record_payload(updated)})


def _policy_for_user(user: User, policy_id: UUID) -> RoutingPolicy | None:
    organization = user.default_organization
    if organization is None:
        return None
    policy = (
        RoutingPolicy.objects.filter(id=policy_id, organization=organization)
        .select_related("company", "department", "fallback_department")
        .first()
    )
    if policy is None:
        return None
    if has_min_role(user, "admin", str(organization.id)):
        return policy
    if has_department_role(user, policy.department, "lead"):
        return policy
    return None


def _routing_record_for_user(user: User, record_id: UUID) -> TaskRoutingRecord | None:
    return (
        list_inbox_for_user(user=user)
        .filter(id=record_id)
        .select_related("company", "to_department", "assigned_user")
        .first()
    )


def _resolve_policy_refs(
    user: User,
    data: dict[str, Any],
) -> tuple[Graph | None, DepartmentRegistry, DepartmentRegistry | None] | Response:
    organization = user.default_organization
    if organization is None:
        return _forbidden("You must belong to an organization to manage routing policies.")
    company = None
    company_id = data.get("company_id")
    if company_id:
        company = (
            accessible_company_queryset(user, minimum_role="member")
            .filter(id=company_id)
            .select_related("organization")
            .first()
        )
        if company is None:
            return _not_found("Company was not found or you do not have access.")
    department_id = data.get("department_id")
    if not isinstance(department_id, str | UUID):
        return _not_found("Department was not found.")
    department = DepartmentRegistry.objects.filter(
        id=department_id,
        organization=organization,
    ).first()
    if department is None:
        return _not_found("Department was not found.")
    fallback_department = None
    fallback_department_id = data.get("fallback_department_id")
    if fallback_department_id:
        fallback_department = DepartmentRegistry.objects.filter(
            id=fallback_department_id,
            organization=organization,
        ).first()
        if fallback_department is None:
            return _not_found("Fallback department was not found.")
    return company, department, fallback_department


def _can_manage_policy(
    *,
    user: User,
    company: Graph | None,
    department: DepartmentRegistry,
) -> bool:
    if has_min_role(user, "admin", str(department.organization_id)):
        return True
    if company is None:
        return False
    return can_mutate_department_work(user=user, company=company, department=department)


def _lead_departments_for_user(user: User) -> list[DepartmentRegistry]:
    organization = user.default_organization
    if organization is None:
        return []
    return list(
        DepartmentRegistry.objects.filter(
            organization=organization,
            memberships__user=user,
            memberships__role="lead",
            memberships__status="active",
        )
        .filter(
            Q(memberships__expires_at__isnull=True) | Q(memberships__expires_at__gt=timezone.now())
        )
        .distinct()
    )


def _validation_error(details: Any) -> Response:
    detail_items = (
        [{"field": key, "errors": value} for key, value in dict(details).items()]
        if isinstance(details, dict)
        else [{"errors": str(details)}]
    )
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=detail_items,
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)
