"""Generic service catalog, engagement, and deliverable API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.service_engagements.serializers import (
    AtlasDeliverableAssembleSerializer,
    AtlasLaunchReadinessSerializer,
    DepartmentPipelineCompleteStageSerializer,
    DepartmentPipelineCreateSerializer,
    DepartmentPipelineReasonSerializer,
    ServiceCatalogCreateSerializer,
    ServiceCatalogPatchSerializer,
    ServiceCatalogQuerySerializer,
    ServiceDeliverableActionSerializer,
    ServiceDeliverableCreateSerializer,
    ServiceEngagementCreateSerializer,
    ServiceEngagementPatchSerializer,
    ServiceEngagementQuerySerializer,
)
from application.services.agency_deliverables import (
    assemble_atlas_deliverable,
    assemble_atlas_mvp_deliverables,
)
from application.services.agency_launch_readiness import CampaignLaunchReadiness
from application.services.audit_log import record_audit_log
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.department_pipeline import (
    DepartmentPipelineError,
    block_stage,
    complete_stage,
    create_pipeline_for_engagement,
    get_pipeline_snapshot,
    skip_stage,
    stage_state_for_engagement,
    start_stage,
)
from application.services.departments import can_mutate_department_work
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from application.services.service_engagements import (
    ServiceEngagementError,
    apply_service_deliverable_action,
    create_service_catalog_item,
    create_service_deliverable,
    create_service_engagement,
    service_catalog_payload,
    service_deliverable_payload,
    service_engagement_payload,
    update_service_catalog_item,
    update_service_engagement,
)
from infrastructure.orm.models import (
    Asset,
    DepartmentRegistry,
    Graph,
    OrganizationMembership,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
)


class ServiceCatalogListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view service catalog items.")
        serializer = ServiceCatalogQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        organization = user.default_organization
        if organization is None:
            return success_response({"services": []})
        queryset = ServiceCatalogItem.objects.filter(organization=organization)
        if not has_min_role(user, "admin"):
            queryset = queryset.filter(status="active").exclude(visibility="internal")
        status_filter = str(serializer.validated_data.get("status") or "")
        visibility_filter = str(serializer.validated_data.get("visibility") or "")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if visibility_filter:
            queryset = queryset.filter(visibility=visibility_filter)
        return success_response(
            {
                "services": [
                    service_catalog_payload(item) for item in queryset.order_by("title", "slug")
                ]
            }
        )

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to manage service catalog items.")
        organization = user.default_organization
        if organization is None:
            return _forbidden("You must belong to an organization to create service catalog items.")
        serializer = ServiceCatalogCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            item = create_service_catalog_item(
                organization=organization,
                user=user,
                data=serializer.validated_data,
            )
        except IntegrityError:
            return error_response(
                "SERVICE_SLUG_CONFLICT",
                "A service catalog item with this slug already exists.",
                status=http_status.HTTP_409_CONFLICT,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(organization.id),
            action="service_catalog.created",
            resource_type="service_catalog_item",
            resource_id=str(item.id),
            metadata={"slug": item.slug, "status": item.status},
        )
        return success_response(
            {"service": service_catalog_payload(item)},
            status=http_status.HTTP_201_CREATED,
        )


class ServiceCatalogDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, service_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view service catalog items.")
        item = _catalog_item_for_user(user, service_id)
        if item is None:
            return _not_found("Service catalog item was not found.")
        return success_response({"service": service_catalog_payload(item)})

    def patch(self, request: Request, service_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to manage service catalog items.")
        item = _catalog_item_for_user(user, service_id, include_inactive=True)
        if item is None:
            return _not_found("Service catalog item was not found.")
        serializer = ServiceCatalogPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            item = update_service_catalog_item(item=item, data=serializer.validated_data)
        except IntegrityError:
            return error_response(
                "SERVICE_SLUG_CONFLICT",
                "A service catalog item with this slug already exists.",
                status=http_status.HTTP_409_CONFLICT,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(item.organization_id),
            action="service_catalog.updated",
            resource_type="service_catalog_item",
            resource_id=str(item.id),
            metadata={"slug": item.slug, "status": item.status},
        )
        return success_response({"service": service_catalog_payload(item)})


class ServiceEngagementListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view service engagements.")
        serializer = ServiceEngagementQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        companies = accessible_company_queryset(user, minimum_role="viewer")
        company_id = serializer.validated_data.get("company_id")
        if company_id:
            companies = companies.filter(id=company_id)
        queryset = (
            ServiceEngagement.objects.filter(company__in=companies)
            .select_related("company", "catalog_item", "assigned_operator", "requested_by")
            .order_by("-updated_at")
        )
        status_filter = str(serializer.validated_data.get("status") or "")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return success_response(
            {
                "engagements": [
                    service_engagement_payload(
                        item,
                        include_internal=has_company_access(user, item.company, "member"),
                    )
                    for item in queryset
                ]
            }
        )

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = ServiceEngagementCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            user, serializer.validated_data["company_id"], minimum_role="member"
        )
        if company is None:
            return _not_found(
                "Company was not found or you do not have access to create engagements."
            )
        catalog_item = _catalog_item_for_engagement(
            user, serializer.validated_data["catalog_item_id"]
        )
        if catalog_item is None:
            return _not_found("Service catalog item was not found.")
        assigned_operator = _assigned_operator(
            company, serializer.validated_data.get("assigned_operator_id")
        )
        if isinstance(assigned_operator, Response):
            return assigned_operator
        context, error = _command_context(
            request=request,
            company=company,
            action="service_engagement.create",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        data = dict(serializer.validated_data)
        data["assigned_operator"] = assigned_operator
        try:
            engagement = create_service_engagement(
                company=company,
                catalog_item=catalog_item,
                user=user,
                data=data,
            )
        except IntegrityError:
            return error_response(
                "SERVICE_ENGAGEMENT_SOURCE_CONFLICT",
                "A service engagement with this source key already exists for the company.",
                status=http_status.HTTP_409_CONFLICT,
            )
        except ServiceEngagementError as exc:
            return _service_error(exc)
        record_audit_log(
            actor=user,
            tenant_id=str(company.organization_id),
            action="service_engagement.created",
            resource_type="service_engagement",
            resource_id=str(engagement.id),
            metadata={"company_id": str(company.id), "catalog_item_id": str(catalog_item.id)},
        )
        response = success_response(
            {"engagement": service_engagement_payload(engagement, include_internal=True)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="service_engagement",
            resource_id=str(engagement.id),
        )


class ServiceEngagementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="viewer")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        return success_response(
            {
                "engagement": service_engagement_payload(
                    engagement,
                    include_internal=has_company_access(user, engagement.company, "member"),
                )
            }
        )

    def patch(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="member")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        serializer = ServiceEngagementPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        assigned_operator = None
        if "assigned_operator_id" in serializer.validated_data:
            assigned_operator = _assigned_operator(
                engagement.company,
                serializer.validated_data.get("assigned_operator_id"),
            )
            if isinstance(assigned_operator, Response):
                return assigned_operator
        data = dict(serializer.validated_data)
        data.pop("company_id", None)
        data.pop("catalog_item_id", None)
        if "assigned_operator_id" in data:
            data.pop("assigned_operator_id", None)
            data["assigned_operator"] = assigned_operator
        context, error = _command_context(
            request=request,
            company=engagement.company,
            action=f"service_engagement.update:{engagement_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        try:
            engagement = update_service_engagement(engagement=engagement, data=data)
        except IntegrityError:
            return error_response(
                "SERVICE_ENGAGEMENT_SOURCE_CONFLICT",
                "A service engagement with this source key already exists for the company.",
                status=http_status.HTTP_409_CONFLICT,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(engagement.organization_id),
            action="service_engagement.updated",
            resource_type="service_engagement",
            resource_id=str(engagement.id),
            metadata={"company_id": str(engagement.company_id), "status": engagement.status},
        )
        response = success_response(
            {"engagement": service_engagement_payload(engagement, include_internal=True)}
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="service_engagement",
            resource_id=str(engagement.id),
        )


class ServiceEngagementDepartmentPipelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="viewer")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        return success_response({"department_pipeline": get_pipeline_snapshot(engagement)})

    def post(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="member")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        serializer = DepartmentPipelineCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            create_pipeline_for_engagement(
                engagement,
                template_id=serializer.validated_data.get(
                    "template_id", "digital_marketing_pro.weekend_social_launch.v1"
                )
                or "digital_marketing_pro.weekend_social_launch.v1",
                created_by=user,
            )
        except DepartmentPipelineError as exc:
            return _department_pipeline_error(exc)
        record_audit_log(
            actor=user,
            tenant_id=str(engagement.organization_id),
            action="service_engagement.department_pipeline.created",
            resource_type="service_engagement",
            resource_id=str(engagement.id),
            metadata={"company_id": str(engagement.company_id)},
        )
        return success_response(
            {"department_pipeline": get_pipeline_snapshot(engagement)},
            status=http_status.HTTP_201_CREATED,
        )


class ServiceEngagementDepartmentPipelineStageActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, engagement_id: UUID, stage_id: str, action: str) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="member")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        try:
            stage = stage_state_for_engagement(engagement, stage_id)
            if action == "start":
                start_stage(stage, actor=user)
            elif action == "complete":
                complete_serializer = DepartmentPipelineCompleteStageSerializer(data=request.data)
                if not complete_serializer.is_valid():
                    return _validation_error(complete_serializer.errors)
                complete_stage(
                    stage,
                    outputs=complete_serializer.validated_data.get("outputs") or [],
                    actor=user,
                )
            elif action == "block":
                block_serializer = DepartmentPipelineReasonSerializer(data=request.data)
                if not block_serializer.is_valid():
                    return _validation_error(block_serializer.errors)
                block_stage(stage, reason=block_serializer.validated_data["reason"], actor=user)
            elif action == "skip":
                skip_serializer = DepartmentPipelineReasonSerializer(data=request.data)
                if not skip_serializer.is_valid():
                    return _validation_error(skip_serializer.errors)
                skip_stage(stage, reason=skip_serializer.validated_data["reason"], actor=user)
            else:
                return _not_found("Department pipeline stage action was not found.")
        except DepartmentPipelineError as exc:
            return _department_pipeline_error(exc)
        record_audit_log(
            actor=user,
            tenant_id=str(engagement.organization_id),
            action=f"service_engagement.department_pipeline.stage.{action}",
            resource_type="service_engagement",
            resource_id=str(engagement.id),
            metadata={"stage_id": stage_id, "company_id": str(engagement.company_id)},
        )
        return success_response({"department_pipeline": get_pipeline_snapshot(engagement)})


class ServiceDeliverableListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="viewer")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        queryset = ServiceDeliverable.objects.filter(engagement=engagement).order_by("-updated_at")
        if not has_company_access(user, engagement.company, "member"):
            queryset = queryset.exclude(visibility="internal")
        include_internal = has_company_access(user, engagement.company, "member")
        return success_response(
            {
                "deliverables": [
                    service_deliverable_payload(item, include_internal=include_internal)
                    for item in queryset
                ]
            }
        )

    def post(self, request: Request, engagement_id: UUID) -> Response:
        user = cast(User, request.user)
        engagement = _engagement_for_user(user, engagement_id, minimum_role="member")
        if engagement is None:
            return _not_found("Service engagement was not found.")
        serializer = ServiceDeliverableCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = dict(serializer.validated_data)
        artifact = _artifact_for_company(engagement.company, data.pop("artifact_id", None))
        if isinstance(artifact, Response):
            return artifact
        report_run = _report_for_company(engagement.company, data.pop("report_run_id", None))
        if isinstance(report_run, Response):
            return report_run
        department = _department_for_company_user(
            user,
            engagement.company,
            data.pop("department_id", None),
        )
        if isinstance(department, Response):
            return department
        context, error = _command_context(
            request=request,
            company=engagement.company,
            action=f"service_deliverable.create:{engagement_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        data["artifact"] = artifact
        data["report_run"] = report_run
        data["department"] = department
        try:
            deliverable = create_service_deliverable(
                engagement=engagement,
                user=user,
                data=data,
            )
        except ServiceEngagementError as exc:
            return _service_error(exc)
        record_audit_log(
            actor=user,
            tenant_id=str(engagement.organization_id),
            action="service_deliverable.created",
            resource_type="service_deliverable",
            resource_id=str(deliverable.id),
            metadata={
                "company_id": str(engagement.company_id),
                "engagement_id": str(engagement.id),
            },
        )
        response = success_response(
            {"deliverable": service_deliverable_payload(deliverable, include_internal=True)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="service_deliverable",
            resource_id=str(deliverable.id),
        )


class ServiceDeliverableActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, deliverable_id: UUID) -> Response:
        user = cast(User, request.user)
        serializer = ServiceDeliverableActionSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        deliverable = _deliverable_for_user(user, deliverable_id, minimum_role="member")
        if deliverable is None:
            return _not_found("Service deliverable was not found.")
        action = str(serializer.validated_data["action"])
        context, error = _command_context(
            request=request,
            company=deliverable.company,
            action=f"service_deliverable.action:{deliverable_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        try:
            deliverable = apply_service_deliverable_action(
                deliverable=deliverable,
                action=action,
                actor=user,
            )
        except ServiceEngagementError as exc:
            return _service_error(exc)
        response = success_response(
            {
                "deliverable": service_deliverable_payload(
                    deliverable,
                    include_internal=has_company_access(user, deliverable.company, "member"),
                )
            }
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="service_deliverable",
            resource_id=str(deliverable.id),
        )


class AtlasDeliverableAssembleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        serializer = AtlasDeliverableAssembleSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        whiteboard = _whiteboard_for_user(user, whiteboard_id, minimum_role="member")
        if whiteboard is None:
            return _not_found("Whiteboard was not found.")
        context, error = _command_context(
            request=request,
            company=whiteboard.company,
            action=f"atlas.deliverables.assemble:{whiteboard_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        deliverable_type = serializer.validated_data.get("deliverable_type")
        with transaction.atomic():
            if deliverable_type:
                deliverables = [
                    assemble_atlas_deliverable(
                        whiteboard=whiteboard,
                        user=user,
                        deliverable_type=str(deliverable_type),
                    )
                ]
            else:
                deliverables = assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=user)
            engagement = deliverables[0].engagement
            record_audit_log(
                actor=user,
                tenant_id=str(whiteboard.organization_id),
                action="atlas_deliverables.assembled",
                resource_type="work_whiteboard",
                resource_id=str(whiteboard.id),
                metadata={
                    "company_id": str(whiteboard.company_id),
                    "engagement_id": str(engagement.id),
                    "deliverable_types": [
                        deliverable.deliverable_type for deliverable in deliverables
                    ],
                },
            )

        response = success_response(
            {
                "engagement": service_engagement_payload(engagement, include_internal=True),
                "deliverables": [
                    service_deliverable_payload(deliverable, include_internal=True)
                    for deliverable in deliverables
                ],
            }
        )
        if len(deliverables) == 1:
            idempotency_resource_type = "service_deliverable"
            idempotency_resource_id = str(deliverables[0].id)
        else:
            idempotency_resource_type = "work_whiteboard"
            idempotency_resource_id = str(whiteboard.id)
        return record_processed_command(
            context=context,
            response=response,
            resource_type=idempotency_resource_type,
            resource_id=idempotency_resource_id,
        )


class AtlasLaunchReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        serializer = AtlasLaunchReadinessSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        whiteboard = _whiteboard_for_user(user, whiteboard_id, minimum_role="member")
        if whiteboard is None:
            return _not_found("Whiteboard was not found.")

        validated = dict(serializer.validated_data)
        live_mode = (
            str(validated.get("mode") or "dry_run") == "live"
            or bool(validated.get("live_mode"))
            or not bool(validated.get("dry_run", True))
        )
        create_receipt = bool(validated.get("create_receipt"))
        context = None
        if create_receipt:
            context, error = _command_context(
                request=request,
                company=whiteboard.company,
                action=f"atlas.launch_readiness.receipt:{whiteboard_id}",
            )
            if error is not None:
                return error
            try:
                replay = replay_processed_command(context)
            except IdempotencyConflict as exc:
                return _idempotency_conflict_response(exc)
            if replay is not None:
                return replay
        readiness = CampaignLaunchReadiness().evaluate(
            whiteboard=whiteboard,
            user=user,
            live_mode=live_mode,
            idempotency_key=str(
                validated.get("idempotency_key") or idempotency_key_from_request(request)
            ),
            create_receipt=create_receipt,
        )
        receipt = readiness.get("receipt_deliverable")
        readiness_payload = {
            key: value for key, value in readiness.items() if key != "receipt_deliverable"
        }
        payload: dict[str, Any] = {"readiness": readiness_payload}
        if isinstance(receipt, dict):
            payload["receipt_deliverable"] = receipt
        response = success_response(payload)
        return record_processed_command(
            context=context,
            response=response,
            resource_type="service_deliverable",
            resource_id=str(receipt.get("id") if isinstance(receipt, dict) else ""),
        )


def _catalog_item_for_user(
    user: User,
    service_id: UUID,
    *,
    include_inactive: bool = False,
) -> ServiceCatalogItem | None:
    organization = user.default_organization
    if organization is None:
        return None
    queryset = ServiceCatalogItem.objects.filter(organization=organization, id=service_id)
    if not include_inactive and not has_min_role(user, "admin"):
        queryset = queryset.filter(status="active").exclude(visibility="internal")
    return queryset.first()


def _catalog_item_for_engagement(user: User, service_id: UUID) -> ServiceCatalogItem | None:
    item = _catalog_item_for_user(user, service_id, include_inactive=has_min_role(user, "admin"))
    if item is None:
        return None
    if item.status == "active" or has_min_role(user, "admin"):
        return item
    return None


def _company_for_user(user: User, company_id: UUID, *, minimum_role: str) -> Graph | None:
    return (
        accessible_company_queryset(user, minimum_role=minimum_role)
        .filter(id=company_id)
        .select_related("organization")
        .first()
    )


def _engagement_for_user(
    user: User,
    engagement_id: UUID,
    *,
    minimum_role: str,
) -> ServiceEngagement | None:
    companies = accessible_company_queryset(user, minimum_role=minimum_role)
    return (
        ServiceEngagement.objects.filter(id=engagement_id, company__in=companies)
        .select_related("company", "catalog_item", "assigned_operator", "requested_by")
        .first()
    )


def _deliverable_for_user(
    user: User,
    deliverable_id: UUID,
    *,
    minimum_role: str,
) -> ServiceDeliverable | None:
    companies = accessible_company_queryset(user, minimum_role=minimum_role)
    return (
        ServiceDeliverable.objects.filter(id=deliverable_id, company__in=companies)
        .select_related(
            "company", "engagement", "engagement__catalog_item", "artifact", "report_run"
        )
        .first()
    )


def _whiteboard_for_user(
    user: User,
    whiteboard_id: UUID,
    *,
    minimum_role: str,
) -> WorkWhiteboard | None:
    companies = accessible_company_queryset(user, minimum_role=minimum_role)
    return (
        WorkWhiteboard.objects.filter(id=whiteboard_id, company__in=companies)
        .select_related("company", "organization")
        .first()
    )


def _assigned_operator(company: Graph, user_id: UUID | None) -> User | Response | None:
    if user_id is None:
        return None
    operator = User.objects.filter(id=user_id).first()
    if operator is None:
        return _not_found("Assigned operator was not found.")
    if not OrganizationMembership.objects.filter(
        organization=company.organization,
        user=operator,
    ).exists():
        return error_response(
            "ASSIGNED_OPERATOR_NOT_ORG_MEMBER",
            "Assigned operator must belong to the company organization.",
            status=http_status.HTTP_400_BAD_REQUEST,
        )
    return operator


def _artifact_for_company(company: Graph, artifact_id: UUID | None) -> Asset | Response | None:
    if artifact_id is None:
        return None
    artifact = Asset.objects.filter(id=artifact_id, company=company).first()
    if artifact is None:
        return _not_found("Artifact was not found for this company.")
    return artifact


def _report_for_company(company: Graph, report_id: UUID | None) -> ReportRun | Response | None:
    if report_id is None:
        return None
    report_run = ReportRun.objects.filter(id=report_id, company=company).first()
    if report_run is None:
        return _not_found("Report run was not found for this company.")
    return report_run


def _department_for_company_user(
    user: User,
    company: Graph,
    department_id: UUID | None,
) -> DepartmentRegistry | Response | None:
    if department_id is None:
        return None
    department = DepartmentRegistry.objects.filter(
        id=department_id,
        organization=company.organization,
    ).first()
    if department is None:
        return _not_found("Department was not found for this company organization.")
    if not can_mutate_department_work(user=user, company=company, department=department):
        return _forbidden("You do not have permission to assign this department.")
    return department


def _service_error(exc: ServiceEngagementError) -> Response:
    return error_response(
        exc.code.upper(),
        exc.message,
        status=http_status.HTTP_400_BAD_REQUEST,
        details=exc.details,
    )


def _department_pipeline_error(exc: DepartmentPipelineError) -> Response:
    return error_response(
        exc.code.upper(),
        exc.message,
        status=http_status.HTTP_400_BAD_REQUEST,
        details=exc.details,
    )


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)


def _command_context(
    *,
    request: Request,
    company: Graph,
    action: str,
) -> tuple[Any, Response | None]:
    if not idempotency_key_from_request(request):
        return None, error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for service engagement mutation commands.",
            status=http_status.HTTP_400_BAD_REQUEST,
        )
    return (
        build_idempotency_context(
            request=request,
            organization=company.organization,
            action=action,
            request_payload=request.data,
        ),
        None,
    )


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        "IDEMPOTENCY_CONFLICT",
        str(exc),
        status=http_status.HTTP_409_CONFLICT,
        details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
    )
