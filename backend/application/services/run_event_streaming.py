"""Helpers for scaling live run event delivery without changing canonical storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from application.services.event_categories import normalize_event_category

EVENT_LEVEL_MINIMAL = "minimal"
EVENT_LEVEL_DEFAULT = "default"
EVENT_LEVEL_VERBOSE = "verbose"
EVENT_LEVELS = (
    EVENT_LEVEL_MINIMAL,
    EVENT_LEVEL_DEFAULT,
    EVENT_LEVEL_VERBOSE,
)
DEFAULT_EVENT_LEVEL = EVENT_LEVEL_DEFAULT
STREAM_SUMMARY_EVENT_TYPE = "node_stream.summary"

_EVENT_LEVEL_RANK = {
    EVENT_LEVEL_MINIMAL: 0,
    EVENT_LEVEL_DEFAULT: 1,
    EVENT_LEVEL_VERBOSE: 2,
}
_EVENT_LEVEL_ALIASES = {
    "critical": EVENT_LEVEL_MINIMAL,
    "important": EVENT_LEVEL_DEFAULT,
}


def normalize_requested_event_level(raw_level: str | None) -> str:
    configured_default = str(
        getattr(settings, "RUN_EVENT_STREAM_DEFAULT_LEVEL", DEFAULT_EVENT_LEVEL)
    ).strip()
    candidate = str(raw_level or configured_default or DEFAULT_EVENT_LEVEL).strip().lower()
    candidate = _EVENT_LEVEL_ALIASES.get(candidate, candidate)
    if candidate in _EVENT_LEVEL_RANK:
        return candidate
    return DEFAULT_EVENT_LEVEL


def event_levels_for_subscription(max_level: str) -> list[str]:
    normalized = normalize_requested_event_level(max_level)
    max_rank = _EVENT_LEVEL_RANK[normalized]
    return [level for level in EVENT_LEVELS if _EVENT_LEVEL_RANK[level] <= max_rank]


def run_event_group_name(*, run_id: str, level: str) -> str:
    return f"run_{run_id}_{normalize_requested_event_level(level)}"


def classify_transport_event_level(
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    normalized_type = str(event_type or "").strip()
    normalized_payload = payload if isinstance(payload, dict) else {}

    if normalized_type == "run.updated":
        return EVENT_LEVEL_MINIMAL
    if normalized_type == "run.schema_validation":
        return EVENT_LEVEL_DEFAULT
    if normalized_type == "node_run.updated":
        return EVENT_LEVEL_MINIMAL
    if normalized_type == STREAM_SUMMARY_EVENT_TYPE:
        if bool(normalized_payload.get("final")):
            return EVENT_LEVEL_MINIMAL
        return EVENT_LEVEL_DEFAULT
    if normalized_type == "node_stream.chunk":
        return EVENT_LEVEL_VERBOSE
    if normalized_type.startswith("agent."):
        return EVENT_LEVEL_VERBOSE
    if "error" in normalized_type or "decision" in normalized_type:
        return EVENT_LEVEL_MINIMAL
    return EVENT_LEVEL_DEFAULT


def add_event_level(
    message: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    enriched = dict(message)
    enriched_level = normalize_requested_event_level(
        level or classify_transport_event_level(str(message.get("type") or ""), payload)
    )
    enriched["level"] = enriched_level
    enriched["category"] = normalize_event_category(
        str(message.get("type") or ""),
        category=cast_to_str(message.get("category")),
        payload=payload,
    )
    return enriched


def message_allowed_for_level(message: dict[str, Any], max_level: str) -> bool:
    message_level = normalize_requested_event_level(cast_to_str(message.get("level")))
    requested_level = normalize_requested_event_level(max_level)
    return _EVENT_LEVEL_RANK[message_level] <= _EVENT_LEVEL_RANK[requested_level]


def cast_to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _stream_summary_cache_ttl_seconds() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_CACHE_TTL_SECONDS", 900))


def _stream_summary_interval_ms() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_INTERVAL_MS", 100))


def _stream_summary_min_chunks() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_MIN_CHUNKS", 5))


def _stream_summary_preview_chars() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_PREVIEW_CHARS", 2000))


def _stream_summary_max_pending_chunks() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_MAX_PENDING_CHUNKS", 24))


def _stream_summary_max_active_streams_per_run() -> int:
    return int(getattr(settings, "RUN_EVENT_STREAM_SUMMARY_MAX_ACTIVE_STREAMS_PER_RUN", 16))


def _stream_summary_state_key(*, run_id: str, node_id: str, attempt: int) -> str:
    return f"run-stream-summary:{run_id}:{node_id}:{attempt}"


def _stream_summary_index_key(*, run_id: str) -> str:
    return f"run-stream-summary-index:{run_id}"


def _append_preview(*, existing: str, chunk: str, limit: int) -> tuple[str, bool]:
    if len(existing) >= limit:
        return existing, True

    remaining = limit - len(existing)
    if len(chunk) <= remaining:
        return existing + chunk, False
    return existing + chunk[:remaining], True


def _now_timestamp(value: datetime | None) -> float:
    if value is not None:
        return value.timestamp()
    return timezone.now().timestamp()


def _load_stream_state(*, key: str) -> dict[str, Any] | None:
    state = cache.get(key)
    if isinstance(state, dict):
        return state
    return None


def _store_stream_state(*, key: str, state: dict[str, Any]) -> None:
    cache.set(key, state, timeout=_stream_summary_cache_ttl_seconds())


def _remember_stream_key(*, run_id: str, state_key: str) -> None:
    index_key = _stream_summary_index_key(run_id=run_id)
    known_keys = cache.get(index_key) or []
    if not isinstance(known_keys, list):
        known_keys = []
    if state_key not in known_keys:
        known_keys.append(state_key)
    max_active = max(_stream_summary_max_active_streams_per_run(), 1)
    known_keys = known_keys[-max_active:]
    cache.set(index_key, known_keys, timeout=_stream_summary_cache_ttl_seconds())


def _forget_stream_key(*, run_id: str, state_key: str) -> None:
    index_key = _stream_summary_index_key(run_id=run_id)
    known_keys = cache.get(index_key) or []
    if not isinstance(known_keys, list):
        cache.delete(index_key)
        return
    remaining = [key for key in known_keys if key != state_key]
    if remaining:
        cache.set(index_key, remaining, timeout=_stream_summary_cache_ttl_seconds())
    else:
        cache.delete(index_key)


def _build_stream_summary_payload(
    state: dict[str, Any],
    *,
    new_chunks: int,
    final: bool,
    final_reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "node_id": state["node_id"],
        "node_type": state["node_type"],
        "attempt": state["attempt"],
        "chunk_count": state["total_chunk_count"],
        "new_chunks": new_chunks,
        "first_chunk_index": state["first_chunk_index"],
        "last_chunk_index": state["last_chunk_index"],
        "text_preview": state["text_preview"],
        "truncated": state["truncated"],
        "final": final,
    }
    agent_event = state.get("latest_agent_event")
    if isinstance(agent_event, dict):
        payload["agent_event"] = agent_event
    if final_reason:
        payload["final_reason"] = final_reason
    return payload


def update_stream_summary(
    *,
    run_id: str,
    payload: dict[str, Any],
    event_time: datetime | None,
) -> dict[str, Any] | None:
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return None

    attempt = int(payload.get("attempt") or 1)
    state_key = _stream_summary_state_key(run_id=run_id, node_id=node_id, attempt=attempt)
    state = _load_stream_state(key=state_key) or {
        "node_id": node_id,
        "node_type": str(payload.get("node_type") or ""),
        "attempt": attempt,
        "total_chunk_count": 0,
        "pending_chunk_count": 0,
        "pending_started_ts": None,
        "first_chunk_index": int(payload.get("chunk_index") or 0),
        "last_chunk_index": int(payload.get("chunk_index") or 0),
        "text_preview": "",
        "truncated": False,
        "last_emit_ts": None,
        "latest_agent_event": None,
    }

    now_ts = _now_timestamp(event_time)
    chunk = str(payload.get("chunk") or "")
    chunk_index = int(payload.get("chunk_index") or 0)

    state["node_type"] = str(payload.get("node_type") or state["node_type"])
    state["total_chunk_count"] += 1
    state["pending_chunk_count"] += 1
    if state.get("pending_started_ts") is None:
        state["pending_started_ts"] = now_ts
    state["last_chunk_index"] = chunk_index

    preview, truncated = _append_preview(
        existing=str(state.get("text_preview") or ""),
        chunk=chunk,
        limit=_stream_summary_preview_chars(),
    )
    state["text_preview"] = preview
    state["truncated"] = bool(state.get("truncated")) or truncated

    agent_event = payload.get("agent_event")
    if isinstance(agent_event, dict):
        state["latest_agent_event"] = agent_event

    summary_payload: dict[str, Any] | None = None
    pending_started_ts = float(state.get("pending_started_ts") or now_ts)
    pending_chunk_count = int(state["pending_chunk_count"])
    should_emit = False
    if isinstance(state.get("latest_agent_event"), dict):
        should_emit = True
    elif pending_chunk_count >= _stream_summary_max_pending_chunks():
        should_emit = True
    elif pending_chunk_count >= _stream_summary_min_chunks():
        should_emit = True
    elif (now_ts - pending_started_ts) * 1000 >= _stream_summary_interval_ms():
        should_emit = True

    if should_emit:
        summary_payload = _build_stream_summary_payload(
            state,
            new_chunks=pending_chunk_count,
            final=False,
        )
        state["pending_chunk_count"] = 0
        state["pending_started_ts"] = None
        state["last_emit_ts"] = now_ts
        state["latest_agent_event"] = None

    _store_stream_state(key=state_key, state=state)
    _remember_stream_key(run_id=run_id, state_key=state_key)
    return summary_payload


def flush_stream_summary(
    *,
    run_id: str,
    node_id: str,
    attempt: int,
    final_reason: str,
) -> dict[str, Any] | None:
    state_key = _stream_summary_state_key(run_id=run_id, node_id=node_id, attempt=attempt)
    state = _load_stream_state(key=state_key)
    if state is None:
        return None

    summary_payload = _build_stream_summary_payload(
        state,
        new_chunks=int(state.get("pending_chunk_count") or 0),
        final=True,
        final_reason=final_reason,
    )
    cache.delete(state_key)
    _forget_stream_key(run_id=run_id, state_key=state_key)
    return summary_payload


def flush_all_stream_summaries(*, run_id: str, final_reason: str) -> list[dict[str, Any]]:
    index_key = _stream_summary_index_key(run_id=run_id)
    state_keys = cache.get(index_key) or []
    if not isinstance(state_keys, list):
        cache.delete(index_key)
        return []

    summaries: list[dict[str, Any]] = []
    for state_key in state_keys:
        state = _load_stream_state(key=str(state_key))
        if state is None:
            continue
        summaries.append(
            _build_stream_summary_payload(
                state,
                new_chunks=int(state.get("pending_chunk_count") or 0),
                final=True,
                final_reason=final_reason,
            )
        )
        cache.delete(str(state_key))

    cache.delete(index_key)
    return summaries
