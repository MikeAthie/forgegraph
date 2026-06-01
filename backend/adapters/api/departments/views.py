"""Department registry API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.departments.serializers import (
    DepartmentCreateSerializer,
    DepartmentMembershipSerializer,
    DepartmentPatchSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.departments import (
    DepartmentError,
    assert_user_belongs_to_department_org,
    can_manage_department,
    can_manage_department_member,
    can_read_department,
    department_membership_payload,
    department_payload,
    department_queryset_for_user,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import DepartmentMembership, DepartmentRegistry, User


class DepartmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        departments = department_queryset_for_user(user).order_by("name", "slug")
        return success_response(
            {
                "departments": [
                    department_payload(department, user=user) for department in departments
                ]
            }
        )

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to create departments.")
        organization = user.default_organization
        if organization is None:
            return _forbidden("You must belong to an organization to create departments.")
        serializer = DepartmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lead_user_or_response = _lead_user_from_data(
            organization=organization, data=serializer.validated_data
        )
        if isinstance(lead_user_or_response, Response):
            return lead_user_or_response
        try:
            department = DepartmentRegistry(
                organization=organization,
                slug=str(serializer.validated_data["slug"]).strip(),
                name=str(serializer.validated_data["name"]).strip(),
                department_type=str(serializer.validated_data.get("department_type") or ""),
                lead_user=lead_user_or_response,
                service_tags_json=list(serializer.validated_data.get("service_tags") or []),
                active=bool(serializer.validated_data.get("active", True)),
                metadata_json=dict(serializer.validated_data.get("metadata") or {}),
            )
            department.full_clean()
            department.save()
        except IntegrityError:
            return error_response(
                "DEPARTMENT_SLUG_CONFLICT",
                "A department with this slug already exists in the organization.",
                status=http_status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        record_audit_log(
            actor=user,
            tenant_id=str(organization.id),
            action="department.created",
            resource_type="department",
            resource_id=str(department.id),
            metadata={"slug": department.slug},
        )
        return success_response(
            {"department": department_payload(department, user=user)},
            status=http_status.HTTP_201_CREATED,
        )


class DepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, department_id: UUID) -> Response:
        user = cast(User, request.user)
        department = _department_for_user(user, department_id)
        if department is None:
            return _not_found("Department was not found.")
        if not can_read_department(user, department):
            return _not_found("Department was not found.")
        return success_response({"department": department_payload(department, user=user)})

    def patch(self, request: Request, department_id: UUID) -> Response:
        user = cast(User, request.user)
        department = _department_for_user(user, department_id)
        if department is None:
            return _not_found("Department was not found.")
        if not can_manage_department(user, department):
            return _forbidden("You do not have permission to update this department.")
        serializer = DepartmentPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = serializer.validated_data
        lead_user_or_response = _lead_user_from_data(
            organization=department.organization,
            data=data,
        )
        if isinstance(lead_user_or_response, Response):
            return lead_user_or_response
        update_fields = _apply_department_patch(
            department=department,
            data=data,
            lead_user=lead_user_or_response,
        )
        try:
            department.full_clean()
            department.save(update_fields=sorted(set(update_fields)))
        except IntegrityError:
            return error_response(
                "DEPARTMENT_SLUG_CONFLICT",
                "A department with this slug already exists in the organization.",
                status=http_status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        record_audit_log(
            actor=user,
            tenant_id=str(department.organization_id),
            action="department.updated",
            resource_type="department",
            resource_id=str(department.id),
            metadata={"slug": department.slug},
        )
        return success_response({"department": department_payload(department, user=user)})


class DepartmentMembershipView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, department_id: UUID) -> Response:
        user = cast(User, request.user)
        department = _department_for_user(user, department_id)
        if department is None or not can_read_department(user, department):
            return _not_found("Department was not found.")
        memberships = DepartmentMembership.objects.filter(department=department).order_by(
            "user__email", "created_at"
        )
        return success_response(
            {
                "memberships": [
                    department_membership_payload(membership) for membership in memberships
                ]
            }
        )

    def post(self, request: Request, department_id: UUID) -> Response:
        return self._upsert(request, department_id, status_code=http_status.HTTP_201_CREATED)

    def patch(self, request: Request, department_id: UUID) -> Response:
        return self._upsert(request, department_id, status_code=http_status.HTTP_200_OK)

    def _upsert(self, request: Request, department_id: UUID, *, status_code: int) -> Response:
        actor = cast(User, request.user)
        department = _department_for_user(actor, department_id)
        if department is None:
            return _not_found("Department was not found.")
        serializer = DepartmentMembershipSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        target = User.objects.filter(id=serializer.validated_data["user_id"]).first()
        if target is None:
            return _not_found("Department member user was not found.")
        role = str(serializer.validated_data.get("role") or "viewer")
        if not can_manage_department_member(actor=actor, department=department, target_role=role):
            return _forbidden("You do not have permission to manage this department membership.")
        try:
            assert_user_belongs_to_department_org(user=target, department=department)
        except DepartmentError as exc:
            return error_response(
                exc.code.upper(),
                exc.message,
                status=http_status.HTTP_400_BAD_REQUEST,
                details=exc.details,
            )
        defaults = {
            "organization": department.organization,
            "role": role,
            "status": str(serializer.validated_data.get("status") or "active"),
            "expires_at": serializer.validated_data.get("expires_at"),
            "metadata_json": dict(serializer.validated_data.get("metadata") or {}),
        }
        membership, created = DepartmentMembership.objects.update_or_create(
            department=department,
            user=target,
            defaults={**defaults, "created_by": actor},
        )
        membership.full_clean()
        membership.save()
        record_audit_log(
            actor=actor,
            tenant_id=str(department.organization_id),
            action="department.membership.upserted",
            resource_type="department_membership",
            resource_id=str(membership.id),
            metadata={
                "department_id": str(department.id),
                "user_id": str(target.id),
                "role": membership.role,
                "created": created,
            },
        )
        return success_response(
            {"membership": department_membership_payload(membership)},
            status=status_code if created else http_status.HTTP_200_OK,
        )


def _department_for_user(user: User, department_id: UUID) -> DepartmentRegistry | None:
    organization = user.default_organization
    if organization is None:
        return None
    return DepartmentRegistry.objects.filter(
        id=department_id,
        organization=organization,
    ).first()


def _lead_user_from_data(
    *,
    organization: Any,
    data: dict[str, Any],
) -> User | None | Response:
    if "lead_user_id" not in data or data.get("lead_user_id") is None:
        return None
    lead_user = User.objects.filter(
        id=data["lead_user_id"],
        organization_memberships__organization=organization,
    ).first()
    if lead_user is None:
        return _not_found("Department lead user was not found.")
    return lead_user


def _apply_department_patch(
    *,
    department: DepartmentRegistry,
    data: dict[str, Any],
    lead_user: User | None,
) -> list[str]:
    update_fields = ["updated_at"]
    for input_key, attr in {
        "slug": "slug",
        "name": "name",
        "department_type": "department_type",
        "active": "active",
    }.items():
        if input_key in data:
            setattr(department, attr, data[input_key])
            update_fields.append(attr)
    if "lead_user_id" in data:
        department.lead_user = lead_user
        update_fields.append("lead_user")
    if "service_tags" in data:
        department.service_tags_json = list(data.get("service_tags") or [])
        update_fields.append("service_tags_json")
    if "metadata" in data:
        department.metadata_json = dict(data.get("metadata") or {})
        update_fields.append("metadata_json")
    return update_fields


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
