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
    WhiteboardBoardCardCreateSerializer,
    WhiteboardBoardCardPatchSerializer,
    WhiteboardBoardEvidenceSerializer,
    WhiteboardDeploymentExecuteSerializer,
    WhiteboardDeploymentPrepareSerializer,
    WhiteboardPatchSerializer,
    WhiteboardPerformanceEvaluationSerializer,
    WhiteboardPerformanceReportSerializer,
    WhiteboardPerformanceStartSerializer,
    WhiteboardPhaseEvaluationSerializer,
    WhiteboardPhaseWorkstreamCompleteSerializer,
    WhiteboardQuerySerializer,
)
from application.services.company_access import has_company_access
from application.services.deployment_orchestration import (
    DeploymentOrchestrationError,
    list_deployment_state,
    load_deployment_policy,
    prepare_deployment_for_whiteboard,
    request_tool_execution_for_channel,
)
from application.services.idempotency import annotate_response
from application.services.performance_orchestration import (
    PerformanceOrchestrationError,
    create_performance_report,
    evaluate_performance,
    list_performance_state,
    load_performance_policy,
    start_performance_review_for_whiteboard,
)
from application.services.product_operations import (
    TERMINAL_OPERATION_STATUSES,
    ProductOperationError,
    begin_product_operation,
    block_product_operation,
    complete_product_operation,
    fail_product_operation,
    get_product_operation_for_user,
    operation_payload,
)
from application.services.rbac import has_min_role
from application.services.strategy_orchestration import (
    StrategyOrchestrationError,
    advance_whiteboard_to_content_if_ready,
    evaluate_planning_gate,
    evaluate_strategy_gate,
    planning_state_payload,
    start_planning_for_whiteboard,
    start_strategy_for_whiteboard,
    strategy_state_payload,
    synthesize_planning,
    synthesize_strategy,
)
from application.services.whiteboard_boards import (
    WhiteboardBoardError,
    attach_card_evidence,
    build_whiteboard_board_snapshot,
    create_whiteboard_card,
    update_whiteboard_card,
)
from application.services.work_whiteboards import (
    WorkWhiteboardError,
    get_whiteboard_for_user,
    list_whiteboards_for_user,
    mark_whiteboard_ready_for_planning,
    mark_whiteboard_ready_for_strategy,
    update_whiteboard_field,
    whiteboard_payload,
)
from application.services.workstream_gates import (
    WorkstreamGateError,
    complete_workstream,
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
            status_code = (
                http_status.HTTP_403_FORBIDDEN
                if exc.code == "permission_denied"
                else http_status.HTTP_400_BAD_REQUEST
            )
            return error_response(exc.code.upper(), exc.message, status=status_code)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        return success_response({"whiteboard": whiteboard_payload(updated, user=user)})


class WhiteboardOperationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID, operation_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        operation = get_product_operation_for_user(
            user=user,
            whiteboard=whiteboard,
            operation_id=str(operation_id),
        )
        if operation is None:
            return _not_found("Product operation was not found.")
        return success_response({"operation": operation_payload(operation)})


class WhiteboardBoardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        return success_response({"board": build_whiteboard_board_snapshot(whiteboard, user=user)})


class WhiteboardBoardCardsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardBoardCardCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = dict(serializer.validated_data)
        idempotency_key = _idempotency_key(request, data)
        try:
            card = create_whiteboard_card(
                user=user,
                whiteboard=whiteboard,
                department_id=data["department_id"],
                title=str(data.get("title") or ""),
                reason=str(data.get("reason") or ""),
                status=str(data.get("status") or "queued"),
                priority=str(data.get("priority") or "normal"),
                due_at=data.get("due_at"),
                assigned_user_id=data.get("assigned_user_id"),
                customer_visible=bool(data.get("customer_visible", False)),
                links=dict(data.get("links") or {}),
                idempotency_key=idempotency_key,
            )
        except WhiteboardBoardError as exc:
            return _board_error(exc)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        whiteboard.refresh_from_db()
        response = success_response(
            {"board": build_whiteboard_board_snapshot(whiteboard, user=user)},
            status=http_status.HTTP_201_CREATED,
        )
        return _annotate_board_idempotency(response, card, idempotency_key)


class WhiteboardBoardCardView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, whiteboard_id: UUID, card_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardBoardCardPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = dict(serializer.validated_data)
        idempotency_key = _idempotency_key(request, data)
        kwargs: dict[str, Any] = {
            "user": user,
            "whiteboard": whiteboard,
            "card_id": card_id,
            "idempotency_key": idempotency_key,
            "expected_updated_at": str(data.get("expected_updated_at") or ""),
        }
        for field_name in (
            "status",
            "department_id",
            "assigned_user_id",
            "priority",
            "due_at",
            "blocker_reason",
            "title",
            "customer_visible",
        ):
            if field_name in data:
                kwargs[field_name] = data[field_name]
        try:
            card = update_whiteboard_card(**kwargs)
        except WhiteboardBoardError as exc:
            return _board_error(exc)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        whiteboard.refresh_from_db()
        response = success_response(
            {"board": build_whiteboard_board_snapshot(whiteboard, user=user)}
        )
        return _annotate_board_idempotency(response, card, idempotency_key)


class WhiteboardBoardCardEvidenceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, card_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardBoardEvidenceSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        data = dict(serializer.validated_data)
        idempotency_key = _idempotency_key(request, data)
        try:
            card = attach_card_evidence(
                user=user,
                whiteboard=whiteboard,
                card_id=card_id,
                evidence_type=str(data.get("evidence_type") or "note"),
                target_id=data.get("target_id"),
                summary=str(data.get("summary") or ""),
                metadata=dict(data.get("metadata") or {}),
                idempotency_key=idempotency_key,
            )
        except WhiteboardBoardError as exc:
            return _board_error(exc)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        whiteboard.refresh_from_db()
        response = success_response(
            {"board": build_whiteboard_board_snapshot(whiteboard, user=user)}
        )
        return _annotate_board_idempotency(response, card, idempotency_key)


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
            status_code = (
                http_status.HTTP_403_FORBIDDEN
                if exc.code == "permission_denied"
                else http_status.HTTP_400_BAD_REQUEST
            )
            return error_response(exc.code.upper(), exc.message, status=status_code)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        return success_response(
            {
                "whiteboard": whiteboard_payload(whiteboard, user=user),
                "routing_record_id": str(routing_record.id),
            }
        )


class WhiteboardReadyForPlanningView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            routing_record = mark_whiteboard_ready_for_planning(user=user, whiteboard=whiteboard)
        except WorkWhiteboardError as exc:
            status_code = (
                http_status.HTTP_403_FORBIDDEN
                if exc.code == "permission_denied"
                else http_status.HTTP_400_BAD_REQUEST
            )
            return error_response(exc.code.upper(), exc.message, status=status_code)
        except ValidationError as exc:
            return _validation_error(exc.message_dict if hasattr(exc, "message_dict") else exc)
        return success_response(
            {
                "whiteboard": whiteboard_payload(whiteboard, user=user),
                "routing_record_id": str(routing_record.id),
            }
        )


class WhiteboardPlanningStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to view planning work.")
        try:
            planning = start_planning_for_whiteboard(user=user, whiteboard=whiteboard)
        except StrategyOrchestrationError as exc:
            return _strategy_error(exc)
        return success_response(
            {
                "planning": planning,
                "strategy": planning,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
            }
        )


class WhiteboardPlanningDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to view planning work.")
        planning = planning_state_payload(whiteboard)
        return success_response({"planning": planning, "strategy": planning})


class WhiteboardPlanningSynthesizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        if not _can_view_strategy(user, whiteboard):
            return _forbidden("You do not have permission to manage planning work.")
        serializer = StrategySynthesisSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            synthesize_planning(user=user, whiteboard=whiteboard)
            evaluation = evaluate_planning_gate(
                user=user,
                whiteboard=whiteboard,
                scores=dict(serializer.validated_data.get("scores") or {}),
            )
            advance_whiteboard_to_content_if_ready(user=user, whiteboard=whiteboard)
        except StrategyOrchestrationError as exc:
            return _strategy_error(exc)
        whiteboard.refresh_from_db()
        planning = planning_state_payload(whiteboard)
        planning["evaluation_id"] = str(evaluation.id)
        return success_response(
            {
                "planning": planning,
                "strategy": planning,
                "whiteboard": whiteboard_payload(whiteboard, user=user),
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
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="phase_start",
                target_type="phase_contract",
                target_id=phase_id,
                idempotency_key=_idempotency_key(request, {}),
                metadata={"phase_id": phase_id},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        try:
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                start_phase_for_whiteboard(user=user, whiteboard=whiteboard, phase_id=phase_id)
                complete_product_operation(operation)
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                whiteboard_phase_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
        )


class WhiteboardPhaseSynthesizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, whiteboard_id: UUID, phase_id: str) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        try:
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="phase_synthesize",
                target_type="phase_contract",
                target_id=phase_id,
                idempotency_key=_idempotency_key(request, {}),
                metadata={"phase_id": phase_id},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        try:
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                synthesize_phase_outputs(user=user, whiteboard=whiteboard, phase_id=phase_id)
                complete_product_operation(operation)
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                whiteboard_phase_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
        )


class WhiteboardPhaseWorkstreamCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(
        self,
        request: Request,
        whiteboard_id: UUID,
        phase_id: str,
        workstream_id: str,
    ) -> Response:
        user = cast(User, request.user)
        whiteboard = get_whiteboard_for_user(user=user, whiteboard_id=whiteboard_id)
        if whiteboard is None:
            return _not_found("Work whiteboard was not found.")
        serializer = WhiteboardPhaseWorkstreamCompleteSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            workstream = complete_workstream(
                user=user,
                whiteboard=whiteboard,
                phase_id=phase_id,
                workstream_id=workstream_id,
                result=dict(serializer.validated_data.get("result") or {}),
            )
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            {
                "workstream": workstream,
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
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="phase_gate_evaluate",
                target_type="phase_contract",
                target_id=phase_id,
                idempotency_key=_idempotency_key(request, dict(serializer.validated_data)),
                metadata={"phase_id": phase_id},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        try:
            evaluation_id = str(_operation_metadata_value(operation, "evaluation_id"))
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                evaluation = evaluate_gate(
                    user=user,
                    whiteboard=whiteboard,
                    phase_id=phase_id,
                    scorecard=scorecard,
                )
                evaluation_id = str(evaluation.id)
                complete_product_operation(operation, metadata={"evaluation_id": evaluation_id})
            contract = get_phase_contract(user=user, whiteboard=whiteboard, phase_id=phase_id)
        except WorkstreamGateError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _phase_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                evaluation_id=evaluation_id,
                whiteboard_phase_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
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
        policy_id = str(serializer.validated_data.get("policy_id") or "")
        try:
            policy = load_deployment_policy(whiteboard=whiteboard, policy_id=policy_id)
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="deployment_prepare",
                target_type="deployment_contract",
                target_id=str(policy["policy_id"]),
                idempotency_key=_idempotency_key(request, dict(serializer.validated_data)),
                metadata={"policy_id": str(policy["policy_id"])},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        except DeploymentOrchestrationError as exc:
            return _deployment_error(exc)
        try:
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                prepare_deployment_for_whiteboard(
                    user=user,
                    whiteboard=whiteboard,
                    policy_id=policy_id,
                )
                complete_product_operation(operation)
            contract = list_deployment_state(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(policy["policy_id"]),
            )
        except DeploymentOrchestrationError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _deployment_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                deployment_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
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
        policy_id = str(serializer.validated_data.get("policy_id") or "")
        try:
            policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id)
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="performance_start",
                target_type="performance_contract",
                target_id=str(policy["policy_id"]),
                idempotency_key=_idempotency_key(request, dict(serializer.validated_data)),
                metadata={"policy_id": str(policy["policy_id"])},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        try:
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                start_performance_review_for_whiteboard(
                    user=user,
                    whiteboard=whiteboard,
                    policy_id=policy_id,
                    period_start=serializer.validated_data.get("period_start"),
                    period_end=serializer.validated_data.get("period_end"),
                )
                complete_product_operation(operation)
            contract = list_performance_state(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(policy["policy_id"]),
            )
        except PerformanceOrchestrationError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                performance_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
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
        policy_id = str(serializer.validated_data.get("policy_id") or "")
        try:
            policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id)
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="performance_report",
                target_type="performance_contract",
                target_id=str(policy["policy_id"]),
                idempotency_key=_idempotency_key(request, dict(serializer.validated_data)),
                metadata={"policy_id": str(policy["policy_id"])},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        try:
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                create_performance_report(
                    user=user,
                    whiteboard=whiteboard,
                    policy_id=policy_id,
                )
                complete_product_operation(operation)
            contract = list_performance_state(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(policy["policy_id"]),
            )
        except PerformanceOrchestrationError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                performance_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
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
        policy_id = str(serializer.validated_data.get("policy_id") or "")
        try:
            policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id)
            operation, created = begin_product_operation(
                user=user,
                whiteboard=whiteboard,
                kind="performance_evaluate",
                target_type="performance_contract",
                target_id=str(policy["policy_id"]),
                idempotency_key=_idempotency_key(request, dict(serializer.validated_data)),
                metadata={"policy_id": str(policy["policy_id"])},
            )
        except ProductOperationError as exc:
            return _operation_error(exc)
        except PerformanceOrchestrationError as exc:
            return _performance_error(exc)
        try:
            evaluation_id = str(_operation_metadata_value(operation, "evaluation_id"))
            if created or operation.status not in TERMINAL_OPERATION_STATUSES:
                evaluation = evaluate_performance(
                    user=user,
                    whiteboard=whiteboard,
                    policy_id=policy_id,
                    scorecard=scorecard,
                )
                evaluation_id = str(evaluation.id)
                complete_product_operation(operation, metadata={"evaluation_id": evaluation_id})
            contract = list_performance_state(
                user=user,
                whiteboard=whiteboard,
                policy_id=str(policy["policy_id"]),
            )
        except PerformanceOrchestrationError as exc:
            _finish_operation_for_error(operation, code=exc.code, message=exc.message)
            return _performance_error(exc)
        whiteboard.refresh_from_db()
        return success_response(
            _operation_envelope(
                operation,
                accepted=created,
                evaluation_id=evaluation_id,
                performance_contract=contract,
                whiteboard=whiteboard_payload(whiteboard, user=user),
            )
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


def _idempotency_key(request: Request, data: dict[str, Any]) -> str:
    return str(
        request.headers.get("Idempotency-Key")
        or request.META.get("HTTP_IDEMPOTENCY_KEY")
        or data.get("idempotency_key")
        or ""
    )


def _operation_envelope(
    operation: Any,
    *,
    accepted: bool,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "operation": operation_payload(operation),
        **payload,
    }


def _operation_metadata_value(operation: Any, key: str) -> Any:
    metadata = getattr(operation, "metadata_json", None)
    if not isinstance(metadata, dict):
        return ""
    return metadata.get(key) or ""


def _finish_operation_for_error(operation: Any, *, code: str, message: str) -> None:
    if str(code).lower() in _BLOCKED_OPERATION_ERROR_CODES or any(
        marker in str(code).lower()
        for marker in ("blocked", "approval", "required", "not_ready", "dependency")
    ):
        block_product_operation(operation, error_code=code, error_message=message)
        return
    fail_product_operation(operation, error_code=code, error_message=message)


_BLOCKED_OPERATION_ERROR_CODES = {
    "phase_synthesis_incomplete",
    "deployment_status_required",
    "deployment_approval_required",
    "performance_deployment_required",
    "performance_report_required",
}


def _operation_error(exc: ProductOperationError) -> Response:
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


def _board_error(exc: WhiteboardBoardError) -> Response:
    status_code: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code == "permission_denied":
        status_code = http_status.HTTP_403_FORBIDDEN
    elif exc.code in {"card_not_found", "department_not_found"}:
        status_code = http_status.HTTP_404_NOT_FOUND
    elif exc.code in {"stale_card_version", "idempotency_conflict"}:
        status_code = http_status.HTTP_409_CONFLICT
    return error_response(
        exc.code.upper(),
        exc.message,
        status=status_code,
        details=exc.details,
    )


def _annotate_board_idempotency(
    response: Response,
    card: Any,
    idempotency_key: str,
) -> Response:
    if not idempotency_key:
        return response
    status_value = str(getattr(card, "_whiteboard_board_idempotency_status", "applied"))
    if status_value not in {"applied", "already_applied", "rejected", "retry_required"}:
        status_value = "applied"
    return annotate_response(
        response,
        status=cast(Any, status_value),
        idempotency_key=idempotency_key,
        resource_type="task_routing_record",
        resource_id=str(getattr(card, "id", "")),
    )


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
