from __future__ import annotations

from collections.abc import Callable

from application.projections import accounting, activity, agents, decisions, memory, tasks
from infrastructure.orm.models import DomainEvent

PROJECTION_NAMES = ("agents", "tasks", "decisions", "accounting", "memory", "activity")

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
