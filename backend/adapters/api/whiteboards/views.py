"""Generic WorkWhiteboard API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.whiteboards.serializers import (
    StrategySynthesisSerializer,
    WhiteboardDeploymentExecuteSerializer,
    WhiteboardDeploymentPrepareSerializer,
    WhiteboardPatchSerializer,
    WhiteboardPerformanceEvaluationSerializer,
    WhiteboardPerformanceReportSerializer,
    WhiteboardPerformanceStartSerializer,
    WhiteboardPhaseEvaluationSerializer,
    WhiteboardQuerySerializer,
)
from application.services.company_access import has_company_access
from application.services.deployment_orchestration import (
    DeploymentOrchestrationError,
    list_deployment_state,
    prepare_deployment_for_whiteboard,
    request_tool_execution_for_channel,
)
from application.services.performance_orchestration import (
    PerformanceOrchestrationError,
    create_performance_report,
    evaluate_performance,
    list_performance_state,
    start_performance_review_for_whiteboard,
)
from application.services.rbac import has_min_role
from application.services.strategy_orchestration import (
    StrategyOrchestrationError,
    advance_whiteboard_to_content_if_ready,
    evaluate_strategy_gate,
    start_strategy_for_whiteboard,
    strategy_state_payload,
    synthesize_strategy,
)
from application.services.work_whiteboards import (
    WorkWhiteboardError,
    get_whiteboard_for_user,
    list_whiteboards_for_user,
    mark_whiteboard_ready_for_strategy,
    update_whiteboard_field,
    whiteboard_payload,
)
from application.services.workstream_gates import (
    WorkstreamGateError,
    evaluate_gate,
    get_phase_contract,
    start_phase_for_whiteboard,
    synthesize_phase_outputs,
)
from infrastructure.orm.models import User


class WhiteboardListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = WhiteboardQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        whiteboards = list_whiteboards_for_user(
            user=user,
            company_id=serializer.validated_data.get("company_id"),
            status=str(serializer.validated_data.get("status") or ""),
        )
        return success_response(
            {
                "whiteboards": [
                    whiteboard_payload(whiteboard, user=user)
                    for whiteboard in whiteboards.order_by("-updated_at")
                ]
            }
        )


class WhiteboardDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        return success_response({"whiteboard": whiteboard_payload(whiteboard, user=user)})

    def patch(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            updated = update_whiteboard_field(
                user=user,
                whiteboard=whiteboard,
                fields=dict(serializer.validated_data),
            )
        except WorkWhiteboardError as exc:
            status_code = http_status.HTTP_403_FORBIDDEN if exc.code == "permission_denied" else http_status.HTTP_400_BAD_REQUEST
            return error_response(exc.code.upper(), exc.message, status=status_code)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        return success_response({"whiteboard": whiteboard_payload(updated, user=user)})


class WhiteboardReadyForStrategyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            routing_record = mark_whiteboard_ready_for_strategy(user=user, whiteboard=whiteboard)
        except WorkWhiteboardError as exc:
            status_code = http_status.HTTP_403_FORBIDDEN if exc.code == "permission_denied" else http_status.HTTP_400_BAD_REQUEST
            return error_response(exc.code.upper(), exc.message, status=status_code)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        return success_response(
            {
                "whiteboard": whiteboard_payload(whiteboard, user=user),
                "routing_record_id": str(routing_record.id),
            }
        )


class WhiteboardStrategyStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to view strategy work.")
        try:
            strategy = start_strategy_for_whiteboard(user=user, whiteboard=whiteboard)
        except StrategyOrchestrationError as exc:
            return _strategy_error(exc)
        return success_response(
            {"strategy": strategy, "whiteboard": whiteboard_payload(whiteboard, user=user)}
        )


class WhiteboardStrategyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to view strategy work.")
        return success_response({"strategy": strategy_state_payload(whiteboard)})


class WhiteboardStrategySynthesizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to manage strategy work.")
        serializer = StrategySynthesisSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            synthesize_strategy(user=user, whiteboard=whiteboard)
            evaluation = evaluate_strategy_gate(
                user=user,
                whiteboard=whiteboard,
                scores=dict(serializer.validated_data.get("scores") or {}),
            )
            advance_whiteboard_to_content_if_ready(user=user, whiteboard=whiteboard)
        except StrategyOrchestrationError as exc:
            return _strategy_error(exc)
        whiteboard.refresh_from_db()
        strategy = strategy_state_payload(whiteboard)
        strategy["evaluation_id"] = str(evaluation.id)
        return success_response(
            {"strategy": strategy, "whiteboard": whiteboard_payload(whiteboard, user=user)}
        )


class WhiteboardPhaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID, phase_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            return _phase_error(exc)
        return success_response({"whiteboard_phase_contract": contract})


class WhiteboardPhaseStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, phase_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            contract = start_phase_for_whiteboard(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "whiteboard_phase_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPhaseSynthesizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, phase_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            synthesize_phase_outputs(user=user, whiteboard=whiteboard, phase_id=phase_id)
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "whiteboard_phase_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPhaseEvaluateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, phase_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPhaseEvaluationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        scorecard = dict(
            serializer.validated_data.get("scorecard")
            or serializer.validated_data.get("scores")
            or {}
        )
        try:
            evaluation = evaluate_gate(
                user=user,
                whiteboard=whiteboard,
                phase_id=phase_id,
                scorecard=scorecard,
            )
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "evaluation_id": str(evaluation.id),
                "whiteboard_phase_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardDeploymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            contract = list_deployment_state(user=user, whiteboard=whiteboard)
        except DeploymentOrchestrationError as exc:
            return _deployment_error(exc)
        return success_response({"deployment_contract": contract})


class WhiteboardDeploymentPrepareView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardDeploymentPrepareSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            contract = prepare_deployment_for_whiteboard(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(serializer.validated_data.get("policy_id") or ""),
            )
        except DeploymentOrchestrationError as exc:
            return _deployment_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "deployment_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardDeploymentChannelExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, channel_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardDeploymentExecuteSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            channel = request_tool_execution_for_channel(
                user=user,
                whiteboard=whiteboard,
                channel_id=channel_id,
                dry_run=bool(serializer.validated_data.get("dry_run", True)),
                inputs=dict(serializer.validated_data.get("inputs") or {}),
                policy_id=str(serializer.validated_data.get("policy_id") or ""),
            )
            contract = list_deployment_state(user=user, whiteboard=whiteboard)
        except DeploymentOrchestrationError as exc:
            return _deployment_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "deployment_channel": channel,
                "deployment_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPerformanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            contract = list_performance_state(user=user, whiteboard=whiteboard)
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        return success_response({"performance_contract": contract})


class WhiteboardPerformanceStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPerformanceStartSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            contract = start_performance_review_for_whiteboard(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(serializer.validated_data.get("policy_id") or ""),
                period_start=serializer.validated_data.get("period_start"),
                period_end=serializer.validated_data.get("period_end"),
            )
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "performance_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPerformanceReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPerformanceReportSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            contract = create_performance_report(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(serializer.validated_data.get("policy_id") or ""),
            )
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "performance_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPerformanceEvaluateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPerformanceEvaluationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        scorecard = dict(
            serializer.validated_data.get("scorecard")
            or serializer.validated_data.get("scores")
            or {}
        )
        try:
            evaluation = evaluate_performance(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(serializer.validated_data.get("policy_id") or ""),
                scorecard=scorecard,
            )
            contract = list_performance_state(user=user, whiteboard=whiteboard)
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "evaluation_id": str(evaluation.id),
                "performance_contract": contract,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request payload is invalid.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": str(key), "issue": str(value)} for key, value in dict(details).items()],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)


def _can_view_strategy(user: User, whiteboard: Any) -> bool:
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _strategy_error(exc: StrategyOrchestrationError) -> Response:
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


def _phase_error(exc: WorkstreamGateError) -> Response:
    status_code = (
        http_status.HTTP_403_FORBIDDEN
        if exc.code == "permission_denied"
        else http_status.HTTP_404_NOT_FOUND
        if exc.code == "phase_definition_not_found"
        else http_status.HTTP_400_BAD_REQUEST
    )
    return error_response(
        exc.code.upper(),
        exc.message,
        status=status_code,
        details=exc.details,
    )


def _deployment_error(exc: DeploymentOrchestrationError) -> Response:
    status_code = (
        http_status.HTTP_403_FORBIDDEN
        if exc.code == "permission_denied"
        else http_status.HTTP_404_NOT_FOUND
        if exc.code == "deployment_policy_not_found"
        else http_status.HTTP_400_BAD_REQUEST
    )
    return error_response(
        exc.code.upper(),
        exc.message,
        status=status_code,
        details=exc.details,
    )


def _performance_error(exc: PerformanceOrchestrationError) -> Response:
    status_code = (
        http_status.HTTP_403_FORBIDDEN
        if exc.code == "permission_denied"
        else http_status.HTTP_404_NOT_FOUND
        if exc.code == "performance_policy_not_found"
        else http_status.HTTP_400_BAD_REQUEST
    )
    return error_response(
        exc.code.upper(),
        exc.message,
        status=status_code,
        details=exc.details,
    )
