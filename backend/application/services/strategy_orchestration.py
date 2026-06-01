"""Compatibility wrappers for the generic whiteboard phase/gate engine."""

from __future__ import annotations

from typing import Any

from application.services.work_whiteboards import effective_work_status_for_whiteboard
from application.services.workstream_gates import (
    WorkstreamGateError,
    complete_workstream,
    create_workstreams_from_definition,
    evaluate_gate,
    list_phase_workstreams,
    load_phase_definition,
    phase_state_payload,
    start_phase_for_whiteboard,
    synthesize_phase_outputs,
)
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    EvaluationRun,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

DEFAULT_STRATEGY_PHASE_ID = "strategy"
STRATEGY_WORKSTREAMS: tuple[str, ...] = ()
StrategyOrchestrationError = WorkstreamGateError


def start_strategy_for_whiteboard(*, user: User, whiteboard: WorkWhiteboard) -> dict[str, Any]:
    return start_phase_for_whiteboard(
        user=user,
        whiteboard=whiteboard,
        phase_id=DEFAULT_STRATEGY_PHASE_ID,
    )


def start_planning_for_whiteboard(*, user: User, whiteboard: WorkWhiteboard) -> dict[str, Any]:
    return start_strategy_for_whiteboard(user=user, whiteboard=whiteboard)


def create_strategy_workstreams(
    *, user: User, whiteboard: WorkWhiteboard
) -> list[TaskRoutingRecord]:
    definition = load_phase_definition(whiteboard=whiteboard, phase_id=DEFAULT_STRATEGY_PHASE_ID)
    return create_workstreams_from_definition(
        user=user, whiteboard=whiteboard, definition=definition
    )


def list_strategy_workstreams(*, whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    try:
        return [
            {**item, "workstream": item.get("id") or item.get("workstream") or ""}
            for item in list_phase_workstreams(
                whiteboard=whiteboard,
                phase_id=DEFAULT_STRATEGY_PHASE_ID,
                include_internal=True,
            )
        ]
    except WorkstreamGateError as exc:
        if exc.code == "phase_definition_not_found":
            return []
        raise


def complete_strategy_workstream(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    workstream: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = complete_workstream(
        user=user,
        whiteboard=whiteboard,
        phase_id=DEFAULT_STRATEGY_PHASE_ID,
        workstream_id=workstream,
        result=result,
    )
    return {**payload, "workstream": payload.get("id") or workstream}


def synthesize_strategy(*, user: User, whiteboard: WorkWhiteboard) -> tuple[Asset, AssetVersion]:
    return synthesize_phase_outputs(
        user=user, whiteboard=whiteboard, phase_id=DEFAULT_STRATEGY_PHASE_ID
    )


def synthesize_planning(*, user: User, whiteboard: WorkWhiteboard) -> tuple[Asset, AssetVersion]:
    return synthesize_strategy(user=user, whiteboard=whiteboard)


def evaluate_strategy_gate(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    scores: dict[str, Any] | None = None,
) -> EvaluationRun:
    return evaluate_gate(
        user=user,
        whiteboard=whiteboard,
        phase_id=DEFAULT_STRATEGY_PHASE_ID,
        scorecard=scores or {},
    )


def evaluate_planning_gate(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    scores: dict[str, Any] | None = None,
) -> EvaluationRun:
    return evaluate_strategy_gate(user=user, whiteboard=whiteboard, scores=scores)


def advance_whiteboard_to_content_if_ready(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
) -> TaskRoutingRecord | None:
    _ = user
    evaluation = _latest_strategy_evaluation(whiteboard)
    if evaluation is None:
        return None
    result = evaluation.result_json if isinstance(evaluation.result_json, dict) else {}
    if result.get("gate_result") != "pass":
        return None
    return (
        TaskRoutingRecord.objects.filter(
            company=whiteboard.company,
            metadata_json__whiteboard_id=str(whiteboard.id),
            metadata_json__phase_id=DEFAULT_STRATEGY_PHASE_ID,
            metadata_json__gate_result="pass",
        )
        .order_by("-created_at")
        .first()
    )


def strategy_state_payload(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    try:
        state = phase_state_payload(
            whiteboard=whiteboard,
            phase_id=DEFAULT_STRATEGY_PHASE_ID,
            include_internal=True,
        )
        workstreams = list_strategy_workstreams(whiteboard=whiteboard)
    except WorkstreamGateError as exc:
        if exc.code != "phase_definition_not_found":
            raise
        workstreams = []
        state = {
            "status": whiteboard.status,
            "all_workstreams_completed": False,
            "synthesis": None,
            "gate": None,
        }
    gate = state.get("gate") if isinstance(state.get("gate"), dict) else None
    gate_passed = bool(gate and gate.get("result") == "pass")
    route = None
    if whiteboard.created_by_id and whiteboard.created_by is not None:
        route = advance_whiteboard_to_content_if_ready(
            user=whiteboard.created_by,
            whiteboard=whiteboard,
        )
    return {
        "status": str(state.get("status") or whiteboard.status),
        "work_status": effective_work_status_for_whiteboard(whiteboard),
        "workstreams": workstreams,
        "all_workstreams_completed": bool(state.get("all_workstreams_completed")),
        "synthesis": state.get("synthesis"),
        "gate": {
            **gate,
            "gate_passed": gate_passed,
        }
        if gate
        else None,
        "content_unblocked": gate_passed,
        "content_routing_record_id": str(route.id) if route is not None else None,
    }


def planning_state_payload(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    state = strategy_state_payload(whiteboard)
    return {
        **state,
        "planning_complete": bool(state.get("content_unblocked")),
        "next_routing_record_id": state.get("content_routing_record_id"),
    }


def _latest_strategy_evaluation(whiteboard: WorkWhiteboard) -> EvaluationRun | None:
    return (
        EvaluationRun.objects.filter(
            company=whiteboard.company,
            result_json__whiteboard_id=str(whiteboard.id),
            result_json__phase_id=DEFAULT_STRATEGY_PHASE_ID,
        )
        .order_by("-created_at")
        .first()
    )
