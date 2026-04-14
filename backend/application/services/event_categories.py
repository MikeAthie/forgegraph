from __future__ import annotations

from typing import Any

EVENT_CATEGORY_STATE = "state"
EVENT_CATEGORY_OBSERVABILITY = "observability"
EVENT_CATEGORIES = (EVENT_CATEGORY_STATE, EVENT_CATEGORY_OBSERVABILITY)

STATE_EVENT_TYPES = {
    "run_started",
    "run_completed",
    "run_failed",
    "run_paused",
    "run_resumed",
    "run_canceled",
    "node_started",
    "node_completed",
    "node_failed",
    "node_skipped",
    "node_retrying",
    "run.updated",
    "node_run.updated",
}

OBSERVABILITY_EVENT_TYPES = {
    "node_stream_chunk",
    "node_stream.chunk",
    "node_stream.summary",
    "run.schema_validation",
}


class EventSafetyViolation(ValueError):
    """Raised when a non-state event attempts to mutate runtime state."""


def normalize_event_category(
    event_type: str,
    *,
    category: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    normalized_type = str(event_type or "").strip()
    normalized_category = str(category or "").strip().lower()

    if normalized_type in STATE_EVENT_TYPES:
        return EVENT_CATEGORY_STATE
    if normalized_type in OBSERVABILITY_EVENT_TYPES:
        return EVENT_CATEGORY_OBSERVABILITY
    if normalized_type.startswith("agent."):
        return EVENT_CATEGORY_OBSERVABILITY
    if isinstance(payload, dict) and normalized_category in EVENT_CATEGORIES:
        return normalized_category
    return EVENT_CATEGORY_OBSERVABILITY


def event_allows_runtime_state_mutation(
    event_type: str,
    *,
    category: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    return (
        normalize_event_category(event_type, category=category, payload=payload)
        == EVENT_CATEGORY_STATE
    )


def assert_runtime_state_mutation_allowed(
    event_type: str,
    *,
    category: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    normalized = normalize_event_category(event_type, category=category, payload=payload)
    if normalized != EVENT_CATEGORY_STATE:
        raise EventSafetyViolation(
            f"event '{event_type}' is categorized as '{normalized}' and must not mutate runtime state"
        )
    return normalized
