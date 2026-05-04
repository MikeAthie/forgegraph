"""Public WebSocket protocol helpers for run streaming."""

from __future__ import annotations

from typing import Any

from django.utils import timezone


def build_ws_public_message(
    event_type: str,
    *,
    run_id: str,
    trace_id: str = "",
    event_id: str = "",
    tenant_id: str = "",
    state_version: int | None = None,
    requires_refetch: bool = False,
    payload: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    message = {
        "type": event_type,
        "timestamp": timestamp or timezone.now().isoformat(),
        "trace_id": trace_id,
        "run_id": run_id,
        "event_id": event_id,
        "tenant_id": tenant_id,
        "requires_refetch": requires_refetch,
        "payload": payload or {},
    }
    if state_version is not None:
        message["state_version"] = state_version
    return message


def normalize_ws_public_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if _is_public_ws_message(message):
        return _with_state_feed_fields(
            {
                "type": str(message.get("type") or ""),
                "timestamp": str(message.get("timestamp") or timezone.now().isoformat()),
                "trace_id": str(message.get("trace_id") or ""),
                "run_id": str(message.get("run_id") or ""),
                "event_id": str(message.get("event_id") or ""),
                "tenant_id": str(message.get("tenant_id") or ""),
                "requires_refetch": bool(message.get("requires_refetch") or False),
                "payload": dict(message.get("payload") or {}),
            },
            message,
        )

    message_type = str(message.get("type") or "").strip()
    if not message_type:
        return None

    run_id = str(message.get("run_id") or "")
    trace_id = str(
        message.get("trace_id")
        or _payload_dict(message.get("run")).get("trace_id")
        or _payload_dict(message.get("node_run")).get("trace_id")
        or ""
    )
    timestamp = str(message.get("timestamp") or timezone.now().isoformat())
    event_id = str(message.get("event_id") or "")

    if message_type == "connected":
        return _with_state_feed_fields(
            build_ws_public_message(
                "connection_established",
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload={
                    "event_level": str(message.get("level") or ""),
                },
            ),
            message,
        )

    if message_type == "run.updated":
        run_payload = _payload_dict(message.get("run"))
        status = str(run_payload.get("status") or "").strip().lower()
        event_type = _run_status_to_event_type(status)
        return _with_state_feed_fields(
            build_ws_public_message(
                event_type,
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload={
                    "status": status,
                    "run": run_payload,
                },
            ),
            message,
        )

    if message_type == "node_run.updated":
        node_payload = _payload_dict(message.get("node_run"))
        status = str(node_payload.get("status") or "").strip().lower()
        event_type = _node_status_to_event_type(status)
        return _with_state_feed_fields(
            build_ws_public_message(
                event_type,
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload={
                    "status": status,
                    "node_run": node_payload,
                },
            ),
            message,
        )

    if message_type == "node_stream.chunk":
        return _with_state_feed_fields(
            build_ws_public_message(
                "node_stream_chunk",
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload=_payload_dict(message.get("node_stream")),
            ),
            message,
        )

    if message_type == "node_stream.summary":
        stream_payload = _payload_dict(message.get("node_stream"))
        public_type = (
            "node_stream_end" if bool(stream_payload.get("final")) else "node_stream_chunk"
        )
        return _with_state_feed_fields(
            build_ws_public_message(
                public_type,
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload=stream_payload,
            ),
            message,
        )

    if message_type == "run.schema_validation":
        return _with_state_feed_fields(
            build_ws_public_message(
                "error",
                run_id=run_id,
                trace_id=trace_id,
                event_id=event_id,
                timestamp=timestamp,
                payload={
                    "code": "run_schema_validation",
                    "details": _payload_dict(message.get("payload")),
                },
            ),
            message,
        )

    return _with_state_feed_fields(
        build_ws_public_message(
            message_type,
            run_id=run_id,
            trace_id=trace_id,
            event_id=event_id,
            timestamp=timestamp,
            payload=_legacy_payload_for_unknown_message(message),
        ),
        message,
    )


def _is_public_ws_message(message: dict[str, Any]) -> bool:
    return (
        isinstance(message.get("type"), str)
        and isinstance(message.get("timestamp"), str)
        and isinstance(message.get("trace_id"), str)
        and isinstance(message.get("run_id"), str)
        and isinstance(message.get("payload"), dict)
    )


def _with_state_feed_fields(
    public_message: dict[str, Any],
    source_message: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(public_message)
    for key in ("state_version", "tenant_id", "requires_refetch", "level", "category"):
        if key in source_message:
            enriched[key] = source_message[key]
    return enriched


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _run_status_to_event_type(status: str) -> str:
    if status == "succeeded":
        return "run_completed"
    if status == "failed":
        return "run_failed"
    if status == "paused":
        return "run_paused"
    if status == "canceled":
        return "run_canceled"
    if status == "running":
        return "run_started"
    return "run_updated"


def _node_status_to_event_type(status: str) -> str:
    if status == "succeeded":
        return "node_completed"
    if status == "failed":
        return "node_failed"
    if status == "waiting":
        return "decision_required"
    if status == "skipped":
        return "node_skipped"
    if status == "running":
        return "node_started"
    return "node_updated"


def _legacy_payload_for_unknown_message(message: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_dict(message.get("payload"))
    if payload:
        return payload
    if isinstance(message.get("run"), dict):
        return {"run": dict(message["run"])}
    if isinstance(message.get("node_run"), dict):
        return {"node_run": dict(message["node_run"])}
    if isinstance(message.get("node_stream"), dict):
        return {"node_stream": dict(message["node_stream"])}
    return {}
