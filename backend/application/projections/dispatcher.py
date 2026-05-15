from __future__ import annotations

from collections.abc import Callable

from application.projections import accounting, activity, agents, decisions, memory, tasks
from infrastructure.orm.models import DomainEvent, TaskLifecycleRecord

PROJECTION_NAMES = ("agents", "tasks", "decisions", "accounting", "memory", "activity")
NOOP_PROJECTION_NAMES = ("memory", "activity")

_HANDLERS: dict[str, Callable[[DomainEvent], None]] = {
    "agents": agents.apply,
    "tasks": tasks.apply,
    "decisions": decisions.apply,
    "accounting": accounting.apply,
    "memory": memory.apply,
    "activity": activity.apply,
}


def apply_projection_event(projection_name: str, event: DomainEvent) -> None:
    handler = _HANDLERS.get(projection_name)
    if handler is None:
        raise ValueError(f"Unknown projection handler: {projection_name}")
    handler(event)


def projection_names_for_event(event: DomainEvent) -> tuple[str, ...]:
    """Return projection handlers that can mutate read models for this event."""

    event_type = str(event.event_type or "")
    payload = event.payload if isinstance(event.payload, dict) else {}
    names: set[str] = set()

    if event_type == "agent.registry_source_updated":
        names.add("agents")
    elif event_type in {"run.created", "run.updated"}:
        if _payload_has_policy_decision(payload):
            names.add("decisions")
    elif event_type in {"node_run.created", "node_run.updated"}:
        if str(payload.get("node_type") or "").strip().lower() == "agent":
            names.add("agents")
        if not _node_run_has_lifecycle_task(event, payload):
            names.add("tasks")
    elif event_type in {"task.lifecycle_transitioned", "task.routing_created"}:
        names.add("tasks")
    elif event_type in {
        "decision.approval_created",
        "decision.approval_updated",
        "decision.audit_review_recorded",
    }:
        names.update({"agents", "decisions"})
    elif event_type.startswith("accounting."):
        names.add("accounting")

    return tuple(name for name in PROJECTION_NAMES if name in names)


def _payload_has_policy_decision(payload: dict[str, object]) -> bool:
    text = str(payload.get("error_message") or "").lower()
    return any(
        token in text
        for token in (
            "policy denied",
            "budget exceeded",
            "quota exceeded",
            "entitlement exceeded",
        )
    )


def _node_run_has_lifecycle_task(event: DomainEvent, payload: dict[str, object]) -> bool:
    run_id = str(payload.get("run_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not run_id or not node_id:
        return False
    return TaskLifecycleRecord.objects.filter(
        organization_id=event.organization_id,
        external_key=f"{run_id}:{node_id}",
    ).exists()
