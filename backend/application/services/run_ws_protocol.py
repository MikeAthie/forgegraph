"""Public WebSocket protocol helpers for run streaming."""

from __future__ import annotations

from typing import Any

from django.utils import timezone


def build_ws_public_message(
    event_type: str,
    *,
    run_id: str,
    trace_id: str = "",
    payload: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "timestamp": timestamp or timezone.now().isoformat(),
        "trace_id": trace_id,
        "run_id": run_id,
        "payload": payload or {},
    }


def normalize_ws_public_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if _is_public_ws_message(message):
        return {
            "type": str(message.get("type") or ""),
            "timestamp": str(message.get("timestamp") or timezone.now().isoformat()),
            "trace_id": str(message.get("trace_id") or ""),
            "run_id": str(message.get("run_id") or ""),
            "payload": dict(message.get("payload") or {}),
        }

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

    if message_type == "connected":
        return build_ws_public_message(
            "connection_established",
            run_id=run_id,
            trace_id=trace_id,
            timestamp=timestamp,
            payload={
                "event_level": str(message.get("level") or ""),
            },
        )

    if message_type == "run.updated":
        run_payload = _payload_dict(message.get("run"))
        status = str(run_payload.get("status") or "").strip().lower()
        event_type = _run_status_to_event_type(status)
        return build_ws_public_message(
            event_type,
            run_id=run_id,
            trace_id=trace_id,
            timestamp=timestamp,
            payload={
                "status": status,
                "run": run_payload,
            },
        )

    if message_type == "node_run.updated":
        node_payload = _payload_dict(message.get("node_run"))
        status = str(node_payload.get("status") or "").strip().lower()
        event_type = _node_status_to_event_type(status)
        return build_ws_public_message(
            event_type,
            run_id=run_id,
            trace_id=trace_id,
            timestamp=timestamp,
            payload={
                "status": status,
                "node_run": node_payload,
            },
        )

    if message_type == "node_stream.chunk":
        return None

    if message_type == "node_stream.summary":
        stream_payload = _payload_dict(message.get("node_stream"))
        public_type = "node_stream_end" if bool(stream_payload.get("final")) else "node_stream_chunk"
        return build_ws_public_message(
            public_type,
            run_id=run_id,
            trace_id=trace_id,
            timestamp=timestamp,
            payload=stream_payload,
        )

    if message_type == "run.schema_validation":
        return build_ws_public_message(
            "error",
            run_id=run_id,
            trace_id=trace_id,
            timestamp=timestamp,
            payload={
                "code": "run_schema_validation",
                "details": _payload_dict(message.get("payload")),
            },
        )

    return build_ws_public_message(
        message_type,
        run_id=run_id,
        trace_id=trace_id,
        timestamp=timestamp,
        payload=_legacy_payload_for_unknown_message(message),
    )


def _is_public_ws_message(message: dict[str, Any]) -> bool:
    return (
        isinstance(message.get("type"), str)
        and isinstance(message.get("timestamp"), str)
        and isinstance(message.get("trace_id"), str)
        and isinstance(message.get("run_id"), str)
        and isinstance(message.get("payload"), dict)
    )


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
