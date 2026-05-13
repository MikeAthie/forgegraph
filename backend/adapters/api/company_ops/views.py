"""Authenticated company operating-loop API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.company_ops.serializers import (
    ApprovalRequestSerializer,
    CompanyOperationLaunchSerializer,
    CompanyOperationObjectiveEvaluationSerializer,
    CompanyOpportunityStatusSerializer,
    CompanyOpsCompanyQuerySerializer,
    CompanySignalCreateSerializer,
    CompanySignalQualifySerializer,
    ProcurementDraftCreateSerializer,
    PublicationDraftCreateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.company_ops import (
    CompanyOpsError,
    company_opportunity_payload,
    company_ops_overview_payload,
    company_signal_payload,
    create_company_signal,
    create_procurement_draft,
    create_publication_draft,
    evaluate_company_operation_objective,
    launch_company_operation,
    operation_objective_payload,
    operation_payload,
    procurement_draft_payload,
    publication_draft_payload,
    qualify_signal,
    request_procurement_approval,
    request_publication_approval,
    update_opportunity_status,
)
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from infrastructure.orm.models import (
    CommerceProcurementDraft,
    CompanyOperationObjective,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    PublicationDraft,
    User,
)


class CompanyOpsOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        company_or_response = _company_from_query(request, minimum_role="viewer")
        if isinstance(company_or_response, Response):
            return company_or_response
        return success_response({"company_ops": company_ops_overview_payload(company_or_response)})


class CompanySignalsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        company_or_response = _company_from_query(request, minimum_role="viewer")
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        signals = CompanySignal.objects.filter(company=company).order_by(
            "-occurred_at", "-created_at"
        )[:100]
        return success_response(
            {
                "company_id": str(company.id),
                "signals": [company_signal_payload(item) for item in signals],
            }
        )

    def post(self, request: Request) -> Response:
        serializer = CompanySignalCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_or_response = _company_from_body(
            request,
            serializer.validated_data["company_id"],
            minimum_role="member",
        )
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        context, error = _command_context(
            request=request, company=company, action="company_ops.signal.create"
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
            signal = create_company_signal(
                company=company,
                actor=cast(User, request.user),
                signal_type=str(serializer.validated_data["signal_type"]),
                title=str(serializer.validated_data["title"]),
                summary=str(serializer.validated_data.get("summary") or ""),
                source=str(serializer.validated_data.get("source") or "manual"),
                external_key=str(serializer.validated_data.get("external_key") or ""),
                channel=str(serializer.validated_data.get("channel") or ""),
                contact_alias=str(serializer.validated_data.get("contact_alias") or ""),
                product_id=_optional_str(serializer.validated_data.get("product_id")),
                order_id=_optional_str(serializer.validated_data.get("order_id")),
                fulfillment_id=_optional_str(serializer.validated_data.get("fulfillment_id")),
                metadata=cast(dict[str, Any], serializer.validated_data.get("metadata") or {}),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response(
            {"signal": company_signal_payload(signal)}, status=http_status.HTTP_201_CREATED
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_signal",
            resource_id=str(signal.id),
        )


class CompanySignalQualifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, signal_id: UUID) -> Response:
        serializer = CompanySignalQualifySerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        signal_or_response = _signal_for_user(request, signal_id, minimum_role="member")
        if isinstance(signal_or_response, Response):
            return signal_or_response
        signal = signal_or_response
        context, error = _command_context(
            request=request,
            company=signal.company,
            action=f"company_ops.signal.qualify:{signal_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        opportunity = qualify_signal(
            signal=signal,
            actor=cast(User, request.user),
            title=str(serializer.validated_data.get("title") or ""),
            summary=str(serializer.validated_data.get("summary") or ""),
            next_action=str(serializer.validated_data.get("next_action") or ""),
        )
        response = success_response({"opportunity": company_opportunity_payload(opportunity)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_opportunity",
            resource_id=str(opportunity.id),
        )


class CompanyOpportunitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        company_or_response = _company_from_query(request, minimum_role="viewer")
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        opportunities = CompanyOpportunity.objects.filter(company=company).order_by(
            "-updated_at", "-created_at"
        )[:100]
        return success_response(
            {
                "company_id": str(company.id),
                "opportunities": [company_opportunity_payload(item) for item in opportunities],
            }
        )


class CompanyOpportunityStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, opportunity_id: UUID) -> Response:
        serializer = CompanyOpportunityStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        opportunity_or_response = _opportunity_for_user(
            request, opportunity_id, minimum_role="member"
        )
        if isinstance(opportunity_or_response, Response):
            return opportunity_or_response
        opportunity = opportunity_or_response
        context, error = _command_context(
            request=request,
            company=opportunity.company,
            action=f"company_ops.opportunity.status:{opportunity_id}",
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
            opportunity = update_opportunity_status(
                opportunity=opportunity,
                status=str(serializer.validated_data["status"]),
                next_action=str(serializer.validated_data.get("next_action") or ""),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response({"opportunity": company_opportunity_payload(opportunity)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_opportunity",
            resource_id=str(opportunity.id),
        )


class PublicationDraftsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        company_or_response = _company_from_query(request, minimum_role="viewer")
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        drafts = PublicationDraft.objects.filter(company=company).order_by(
            "-updated_at", "-created_at"
        )[:100]
        return success_response(
            {
                "company_id": str(company.id),
                "publication_drafts": [publication_draft_payload(item) for item in drafts],
            }
        )

    def post(self, request: Request) -> Response:
        serializer = PublicationDraftCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_or_response = _company_from_body(
            request,
            serializer.validated_data["company_id"],
            minimum_role="member",
        )
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        context, error = _command_context(
            request=request, company=company, action="company_ops.publication.create"
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
            draft = create_publication_draft(
                company=company,
                actor=cast(User, request.user),
                idempotency_key=idempotency_key_from_request(request),
                title=str(serializer.validated_data["title"]),
                channel=str(serializer.validated_data.get("channel") or ""),
                audience=str(serializer.validated_data.get("audience") or ""),
                body=str(serializer.validated_data.get("body") or ""),
                call_to_action=str(serializer.validated_data.get("call_to_action") or ""),
                signal_id=_optional_str(serializer.validated_data.get("signal_id")),
                opportunity_id=_optional_str(serializer.validated_data.get("opportunity_id")),
                asset_id=_optional_str(serializer.validated_data.get("asset_id")),
                asset_version_id=_optional_str(serializer.validated_data.get("asset_version_id")),
                media_job_id=_optional_str(serializer.validated_data.get("media_job_id")),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response(
            {"publication_draft": publication_draft_payload(draft)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="publication_draft",
            resource_id=str(draft.id),
        )


class PublicationDraftApprovalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, draft_id: UUID) -> Response:
        serializer = ApprovalRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        draft_or_response = _publication_draft_for_user(request, draft_id, minimum_role="member")
        if isinstance(draft_or_response, Response):
            return draft_or_response
        draft = draft_or_response
        context, error = _command_context(
            request=request,
            company=draft.company,
            action=f"company_ops.publication.approval:{draft_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        draft = request_publication_approval(
            draft=draft,
            actor=cast(User, request.user),
            note=str(serializer.validated_data.get("note") or ""),
        )
        response = success_response({"publication_draft": publication_draft_payload(draft)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="publication_draft",
            resource_id=str(draft.id),
        )


class ProcurementDraftsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        company_or_response = _company_from_query(request, minimum_role="viewer")
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        drafts = (
            CommerceProcurementDraft.objects.filter(company=company)
            .prefetch_related("lines")
            .order_by("-updated_at", "-created_at")[:100]
        )
        return success_response(
            {
                "company_id": str(company.id),
                "procurement_drafts": [procurement_draft_payload(item) for item in drafts],
            }
        )

    def post(self, request: Request) -> Response:
        serializer = ProcurementDraftCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_or_response = _company_from_body(
            request,
            serializer.validated_data["company_id"],
            minimum_role="member",
        )
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        context, error = _command_context(
            request=request, company=company, action="company_ops.procurement.create"
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
            draft = create_procurement_draft(
                company=company,
                actor=cast(User, request.user),
                idempotency_key=idempotency_key_from_request(request),
                title=str(serializer.validated_data["title"]),
                rationale=str(serializer.validated_data.get("rationale") or ""),
                budget_amount=serializer.validated_data.get("budget_amount") or 0,
                currency=str(serializer.validated_data.get("currency") or "mxn"),
                lines=list(serializer.validated_data.get("lines") or []),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response(
            {"procurement_draft": procurement_draft_payload(draft)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="commerce_procurement_draft",
            resource_id=str(draft.id),
        )


class ProcurementDraftApprovalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, draft_id: UUID) -> Response:
        serializer = ApprovalRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        draft_or_response = _procurement_draft_for_user(request, draft_id, minimum_role="member")
        if isinstance(draft_or_response, Response):
            return draft_or_response
        draft = draft_or_response
        context, error = _command_context(
            request=request,
            company=draft.company,
            action=f"company_ops.procurement.approval:{draft_id}",
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay
        draft = request_procurement_approval(
            draft=draft,
            actor=cast(User, request.user),
            note=str(serializer.validated_data.get("note") or ""),
        )
        response = success_response({"procurement_draft": procurement_draft_payload(draft)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="commerce_procurement_draft",
            resource_id=str(draft.id),
        )


class CompanyOperationsLaunchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CompanyOperationLaunchSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_or_response = _company_from_body(
            request,
            serializer.validated_data["company_id"],
            minimum_role="member",
        )
        if isinstance(company_or_response, Response):
            return company_or_response
        company = company_or_response
        source_signal = None
        source_signal_id = serializer.validated_data.get("source_signal_id")
        if source_signal_id:
            source_signal_or_response = _signal_for_user(
                request,
                cast(UUID, source_signal_id),
                minimum_role="member",
            )
            if isinstance(source_signal_or_response, Response):
                return source_signal_or_response
            source_signal = source_signal_or_response
        context, error = _command_context(
            request=request, company=company, action="company_ops.operation.launch"
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
            run = launch_company_operation(
                company=company,
                actor=cast(User, request.user),
                operation_type=str(serializer.validated_data["operation_type"]),
                source_signal=source_signal,
                context_note=str(serializer.validated_data.get("context_note") or ""),
                run_type=str(serializer.validated_data.get("run_type") or "rehearsal"),
                run_goal=str(serializer.validated_data.get("run_goal") or ""),
                hypothesis=str(serializer.validated_data.get("hypothesis") or ""),
                target_signal=str(serializer.validated_data.get("target_signal") or ""),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response(
            {"operation": operation_payload(run)}, status=http_status.HTTP_201_CREATED
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )


class CompanyOperationObjectiveEvaluationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, operation_id: UUID) -> Response:
        serializer = CompanyOperationObjectiveEvaluationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        objective_or_response = _objective_for_user(
            request,
            operation_id,
            minimum_role="member",
        )
        if isinstance(objective_or_response, Response):
            return objective_or_response
        objective = objective_or_response
        context, error = _command_context(
            request=request,
            company=objective.company,
            action=f"company_ops.operation.objective.evaluate:{operation_id}",
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
            objective = evaluate_company_operation_objective(
                objective=objective,
                success_score=int(serializer.validated_data["success_score"]),
                miss_analysis=str(serializer.validated_data.get("miss_analysis") or ""),
                next_decision=str(serializer.validated_data.get("next_decision") or ""),
                integrity_gates=cast(
                    dict[str, Any],
                    serializer.validated_data.get("integrity_gates") or {},
                ),
            )
        except CompanyOpsError as exc:
            return _company_ops_error_response(exc)
        response = success_response({"objective_contract": operation_objective_payload(objective)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_operation_objective",
            resource_id=str(objective.id),
        )


def _company_from_query(request: Request, *, minimum_role: str) -> Graph | Response:
    serializer = CompanyOpsCompanyQuerySerializer(data=request.query_params)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    return _company_from_body(
        request, serializer.validated_data["company_id"], minimum_role=minimum_role
    )


def _company_from_body(request: Request, company_id: Any, *, minimum_role: str) -> Graph | Response:
    user = cast(User, request.user)
    company = (
        accessible_company_queryset(user, minimum_role=minimum_role)
        .filter(id=company_id)
        .select_related("organization")
        .first()
    )
    if company is None:
        return _not_found("Company was not found or you do not have access to it.")
    if not has_company_access(user, company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to use company operations.")
    return cast(Graph, company)


def _signal_for_user(
    request: Request, signal_id: UUID, *, minimum_role: str
) -> CompanySignal | Response:
    user = cast(User, request.user)
    signal = (
        CompanySignal.objects.select_related("company", "company__organization")
        .filter(
            id=signal_id, company__in=accessible_company_queryset(user, minimum_role=minimum_role)
        )
        .first()
    )
    if signal is None:
        return _not_found("Company signal was not found.")
    if not has_company_access(user, signal.company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to use this company signal.")
    return signal


def _opportunity_for_user(
    request: Request, opportunity_id: UUID, *, minimum_role: str
) -> CompanyOpportunity | Response:
    user = cast(User, request.user)
    opportunity = (
        CompanyOpportunity.objects.select_related("company", "company__organization")
        .filter(
            id=opportunity_id,
            company__in=accessible_company_queryset(user, minimum_role=minimum_role),
        )
        .first()
    )
    if opportunity is None:
        return _not_found("Company opportunity was not found.")
    if not has_company_access(user, opportunity.company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to use this company opportunity.")
    return opportunity


def _publication_draft_for_user(
    request: Request, draft_id: UUID, *, minimum_role: str
) -> PublicationDraft | Response:
    user = cast(User, request.user)
    draft = (
        PublicationDraft.objects.select_related("company", "company__organization")
        .filter(
            id=draft_id, company__in=accessible_company_queryset(user, minimum_role=minimum_role)
        )
        .first()
    )
    if draft is None:
        return _not_found("Publication draft was not found.")
    if not has_company_access(user, draft.company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to use this publication draft.")
    return draft


def _procurement_draft_for_user(
    request: Request, draft_id: UUID, *, minimum_role: str
) -> CommerceProcurementDraft | Response:
    user = cast(User, request.user)
    draft = (
        CommerceProcurementDraft.objects.select_related("company", "company__organization")
        .filter(
            id=draft_id, company__in=accessible_company_queryset(user, minimum_role=minimum_role)
        )
        .first()
    )
    if draft is None:
        return _not_found("Procurement draft was not found.")
    if not has_company_access(user, draft.company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to use this procurement draft.")
    return draft


def _objective_for_user(
    request: Request, operation_id: UUID, *, minimum_role: str
) -> CompanyOperationObjective | Response:
    user = cast(User, request.user)
    objective = (
        CompanyOperationObjective.objects.select_related(
            "company",
            "company__organization",
            "operation",
            "source_signal",
        )
        .filter(
            operation_id=operation_id,
            company__in=accessible_company_queryset(user, minimum_role=minimum_role),
        )
        .first()
    )
    if objective is None:
        return _not_found("Company operation objective was not found.")
    if not has_company_access(user, objective.company, minimum_role=minimum_role):
        return _forbidden("You do not have permission to evaluate this company operation.")
    return objective


def _command_context(
    *, request: Request, company: Graph, action: str
) -> tuple[Any, Response | None]:
    if not idempotency_key_from_request(request):
        return None, error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for company operation commands.",
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


def _optional_str(value: Any) -> str | None:
    return str(value) if value else None


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


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        "IDEMPOTENCY_CONFLICT",
        str(exc),
        status=http_status.HTTP_409_CONFLICT,
        details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
    )


def _company_ops_error_response(exc: CompanyOpsError) -> Response:
    response_status: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code in {
        "asset_not_found",
        "asset_version_not_found",
        "fulfillment_not_found",
        "media_job_not_found",
        "opportunity_not_found",
        "order_not_found",
        "product_not_found",
        "signal_not_found",
    }:
        response_status = http_status.HTTP_404_NOT_FOUND
    if exc.code in {"graph_version_missing"}:
        response_status = http_status.HTTP_409_CONFLICT
    return error_response(exc.code.upper(), exc.message, status=response_status)
