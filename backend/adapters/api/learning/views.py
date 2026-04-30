"""Company learning API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.learning.serializers import (
    OutcomeReviewCreateSerializer,
    OutcomeReviewQuerySerializer,
    PolicyRuleCreateSerializer,
    PolicyRuleQuerySerializer,
    PreferenceEventQuerySerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.company_learning import (
    OutcomeReviewService,
    PolicyCandidateService,
    outcome_review_payload,
    policy_rule_payload,
    preference_event_payload,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import (
    Asset,
    DecisionRecord,
    Graph,
    NodeRun,
    OutcomeReview,
    PolicyRule,
    PreferenceEvent,
    Run,
    TaskRecord,
    User,
)


class PreferenceEventListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = PreferenceEventQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view preference events.")
        queryset = PreferenceEvent.objects.filter(company=company).select_related(
            "operation",
            "task",
            "decision",
            "approval_task",
            "context_pack",
        )
        operation_id = serializer.validated_data.get("operation_id")
        if operation_id:
            queryset = queryset.filter(operation_id=operation_id)
        return success_response(
            {"preference_events": [preference_event_payload(event) for event in queryset[:100]]}
        )


class OutcomeReviewListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = OutcomeReviewQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view outcome reviews.")

        queryset = OutcomeReview.objects.filter(company=company).select_related(
            "operation",
            "task",
            "decision",
            "asset",
        )
        operation_id = serializer.validated_data.get("operation_id")
        asset_id = serializer.validated_data.get("asset_id")
        deliverable_id = serializer.validated_data.get("deliverable_id")
        if operation_id:
            queryset = queryset.filter(operation_id=operation_id)
        if asset_id:
            queryset = queryset.filter(asset_id=asset_id)
        if deliverable_id:
            queryset = queryset.filter(deliverable_id=deliverable_id)
        return success_response(
            {"outcome_reviews": [outcome_review_payload(review) for review in queryset[:100]]}
        )

    def post(self, request: Request) -> Response:
        serializer = OutcomeReviewCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "member"):
            return _forbidden("You do not have permission to create outcome reviews.")

        try:
            review = OutcomeReviewService().create_outcome_review(
                company=company,
                operation=_resolve_operation(
                    company, serializer.validated_data.get("operation_id")
                ),
                task=_resolve_task(company, serializer.validated_data.get("task_id")),
                node_run=_resolve_node_run(company, serializer.validated_data.get("node_run_id")),
                decision=_resolve_decision(company, serializer.validated_data.get("decision_id")),
                asset=_resolve_asset(company, serializer.validated_data.get("asset_id")),
                deliverable_id=serializer.validated_data.get("deliverable_id"),
                success_score=serializer.validated_data.get("success_score"),
                success_metrics=serializer.validated_data.get("success_metrics") or {},
                human_feedback=serializer.validated_data.get("human_feedback"),
                issues=serializer.validated_data.get("issues") or [],
                root_cause=serializer.validated_data.get("root_cause"),
                created_by_type="user",
                created_by_id=user.id,
            )
        except ValueError as exc:
            return error_response(
                "VALIDATION_ERROR",
                str(exc),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            {"outcome_review": outcome_review_payload(review)},
            status=http_status.HTTP_201_CREATED,
        )


class PolicyRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = PolicyRuleQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view policies.")

        queryset = PolicyRule.objects.filter(company=company)
        status_filter = str(serializer.validated_data.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return success_response(
            {"policy_rules": [policy_rule_payload(rule) for rule in queryset[:100]]}
        )

    def post(self, request: Request) -> Response:
        serializer = PolicyRuleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "member"):
            return _forbidden("You do not have permission to create policy candidates.")
        try:
            rule = PolicyCandidateService().create_policy_candidate(
                company=company,
                title=serializer.validated_data["title"],
                condition=serializer.validated_data.get("condition") or {},
                recommendation=serializer.validated_data.get("recommendation") or {},
                confidence=serializer.validated_data.get("confidence", 0.5),
                scope_type=serializer.validated_data.get("scope_type") or "company",
                scope_id=serializer.validated_data.get("scope_id") or "",
                supporting_preference_event_ids=serializer.validated_data.get(
                    "supporting_preference_event_ids"
                )
                or [],
                supporting_outcome_review_ids=serializer.validated_data.get(
                    "supporting_outcome_review_ids"
                )
                or [],
            )
        except ValueError as exc:
            return error_response(
                "VALIDATION_ERROR",
                str(exc),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            {"policy_rule": policy_rule_payload(rule)},
            status=http_status.HTTP_201_CREATED,
        )


class PolicyRulePromoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, policy_rule_id: UUID) -> Response:
        user = cast(User, request.user)
        rule = _get_policy_rule_for_user(user=user, policy_rule_id=policy_rule_id)
        if rule is None:
            return _not_found("Policy rule was not found.")
        if not _has_company_role(user, rule.company, "admin"):
            return _forbidden("You do not have permission to promote policies.")
        try:
            rule = PolicyCandidateService().promote_policy_rule(policy_rule=rule)
        except ValueError as exc:
            return error_response(
                "VALIDATION_ERROR",
                str(exc),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return success_response({"policy_rule": policy_rule_payload(rule)})


class PolicyRuleRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, policy_rule_id: UUID) -> Response:
        user = cast(User, request.user)
        rule = _get_policy_rule_for_user(user=user, policy_rule_id=policy_rule_id)
        if rule is None:
            return _not_found("Policy rule was not found.")
        if not _has_company_role(user, rule.company, "admin"):
            return _forbidden("You do not have permission to reject policies.")
        rule = PolicyCandidateService().reject_policy_candidate(policy_rule=rule)
        return success_response({"policy_rule": policy_rule_payload(rule)})


def _get_company(user: User, company_id: UUID) -> Graph | None:
    return cast(Graph | None, Graph.objects.for_user(user).filter(id=company_id).first())


def _get_policy_rule_for_user(*, user: User, policy_rule_id: UUID) -> PolicyRule | None:
    return (
        PolicyRule.objects.select_related("company")
        .filter(id=policy_rule_id, company__in=Graph.objects.for_user(user))
        .first()
    )


def _has_company_role(user: User, company: Graph, role: str) -> bool:
    return bool(company.organization_id) and has_min_role(user, role, str(company.organization_id))


def _resolve_operation(company: Graph, operation_id: UUID | None) -> Run | None:
    if operation_id is None:
        return None
    operation = Run.objects.filter(id=operation_id, graph_version__graph=company).first()
    if operation is None:
        raise ValueError("Operation does not belong to company.")
    return operation


def _resolve_task(company: Graph, task_id: UUID | None) -> TaskRecord | None:
    if task_id is None:
        return None
    task = TaskRecord.objects.filter(id=task_id, execution__graph_version__graph=company).first()
    if task is None:
        raise ValueError("Task does not belong to company.")
    return task


def _resolve_node_run(company: Graph, node_run_id: UUID | None) -> NodeRun | None:
    if node_run_id is None:
        return None
    node_run = NodeRun.objects.filter(id=node_run_id, run__graph_version__graph=company).first()
    if node_run is None:
        raise ValueError("Node run does not belong to company.")
    return node_run


def _resolve_decision(company: Graph, decision_id: UUID | None) -> DecisionRecord | None:
    if decision_id is None:
        return None
    decision = (
        DecisionRecord.objects.select_related(
            "execution__graph_version__graph",
            "task__execution__graph_version__graph",
            "source_approval_task__run__graph_version__graph",
        )
        .filter(id=decision_id, organization=company.organization)
        .first()
    )
    if decision is None or not _decision_belongs_to_company(decision=decision, company=company):
        raise ValueError("Decision does not belong to company.")
    return decision


def _resolve_asset(company: Graph, asset_id: UUID | None) -> Asset | None:
    if asset_id is None:
        return None
    asset = Asset.objects.filter(id=asset_id, company=company).first()
    if asset is None:
        raise ValueError("Asset does not belong to company.")
    return asset


def _decision_belongs_to_company(*, decision: DecisionRecord, company: Graph) -> bool:
    execution = decision.execution
    if execution is not None and execution.graph_version.graph_id == company.id:
        return True
    task = decision.task
    if task is not None and task.execution.graph_version.graph_id == company.id:
        return True
    approval = decision.source_approval_task
    if approval is not None and approval.run.graph_version.graph_id == company.id:
        return True
    return False


def _validation_error(errors: dict[str, Any]) -> Response:
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(str(error) for error in field_errors)}
            for field, field_errors in errors.items()
        ],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)
