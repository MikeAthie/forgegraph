"""Agent stream and nested payload normalization helpers."""

# ruff: noqa: F401,F403,F405,I001

from adapters.api.runs.common_base import *  # noqa: F403


def _datetime_from_timestamp_ms(timestamp_ms: int | None) -> datetime | None:
    if not timestamp_ms:
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _serialize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _persist_run_updated_event(run: Run) -> None:
    RunEvent.objects.create(
        run=run,
        event_type="run.updated",
        trace_id=run.trace_id,
        payload=_serialize_event_payload(
            redact_payload(
                {
                    "status": run.status,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "output_json": run.output_json,
                    "error_message": run.error_message,
                    "paused_node_id": run.paused_node_id,
                    "pause_state_json": run.pause_state_json,
                    "category": "state",
                }
            )
        ),
    )


def _parse_agent_stream_chunk(chunk: Any) -> dict[str, Any] | None:
    if not isinstance(chunk, str):
        return None
    stripped = chunk.strip()
    if not stripped:
        return None

    try:
        parsed = pyjson.loads(stripped)
    except (TypeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    event_name = parsed.get("event")
    if not isinstance(event_name, str) or not event_name.startswith("agent."):
        return None

    return parsed


def _normalize_agent_stream_event(
    *,
    node_id: str,
    node_type: str,
    attempt: int,
    chunk_index: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "event": str(payload.get("event") or ""),
        "node_id": node_id,
        "node_type": node_type,
        "attempt": attempt,
        "chunk_index": chunk_index,
    }
    for key in ("step_index", "action", "tool", "stop_reason", "status"):
        value = payload.get(key)
        if value is not None:
            normalized[key] = value
    return cast(dict[str, Any], redact_payload(normalized))


def _derive_agent_trace(
    *,
    node_run: NodeRun,
    agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if node_run.node_type != "agent":
        return None

    output_json = redact_payload(node_run.output_json) if node_run.output_json else None
    agent_output = None
    if isinstance(output_json, dict):
        candidate = output_json.get("output")
        if isinstance(candidate, dict):
            agent_output = candidate
        elif isinstance(output_json.get("pause_payload"), dict):
            pause_payload = cast(dict[str, Any], output_json["pause_payload"])
            pause_trace = pause_payload.get("agent_trace")
            if isinstance(pause_trace, dict):
                agent_output = pause_trace

    stream_events = agent_events_by_node.get((str(node_run.node_id), int(node_run.attempt)), [])
    if not agent_output and not stream_events:
        return None

    trace: dict[str, Any] = {
        "events": stream_events,
    }
    if isinstance(agent_output, dict):
        for key in (
            "final_output",
            "stop_reason",
            "step_count",
            "tool_call_count",
            "steps",
            "usage",
            "approval_pending",
            "allowed_tools",
        ):
            value = agent_output.get(key)
            if value is not None:
                trace[key] = value
    return trace


def _merge_nested_payload(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_nested_payload(existing, value)
        else:
            merged[key] = value
    return merged


def _insert_dotted_payload_value(root: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = [part for part in dotted_key.split(".") if part]
    if not parts:
        return

    current = root
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing

    leaf_key = parts[-1]
    existing_leaf = current.get(leaf_key)
    if isinstance(existing_leaf, dict) and isinstance(value, dict):
        current[leaf_key] = _merge_nested_payload(existing_leaf, value)
    else:
        current[leaf_key] = value


def _expand_dotted_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [_expand_dotted_payload(item) for item in value]
    if not isinstance(value, dict):
        return value

    expanded: dict[str, Any] = {}
    for key, item in value.items():
        nested_item = _expand_dotted_payload(item)
        if not isinstance(key, str) or "." not in key:
            existing = expanded.get(key)
            if isinstance(existing, dict) and isinstance(nested_item, dict):
                expanded[key] = _merge_nested_payload(existing, nested_item)
            else:
                expanded[key] = nested_item
            continue
        _insert_dotted_payload_value(expanded, key, nested_item)
    return expanded


__all__ = [name for name in globals() if not name.startswith("__")]
