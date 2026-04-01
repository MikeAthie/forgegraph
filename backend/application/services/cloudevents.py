from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

CLOUDEVENT_TYPE_TO_ENGINE_EVENT = {
    "forgegraph.run.started": "run_started",
    "forgegraph.run.completed": "run_completed",
    "forgegraph.run.failed": "run_failed",
    "forgegraph.run.paused": "run_paused",
    "forgegraph.run.resumed": "run_resumed",
    "forgegraph.run.canceled": "run_canceled",
    "forgegraph.run.schema_validation": "run.schema_validation",
    "forgegraph.node.started": "node_started",
    "forgegraph.node.completed": "node_completed",
    "forgegraph.node.failed": "node_failed",
    "forgegraph.node.skipped": "node_skipped",
    "forgegraph.node.retrying": "node_retrying",
    "forgegraph.node.stream_chunk": "node_stream_chunk",
}
ENGINE_EVENT_TO_CLOUDEVENT_TYPE = {
    value: key for key, value in CLOUDEVENT_TYPE_TO_ENGINE_EVENT.items()
}


def unwrap_engine_event(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    specversion = str(payload.get("specversion") or "").strip()
    if specversion != "1.0":
        return payload

    data = payload.get("data")
    if not isinstance(data, dict):
        return {}

    event_payload = dict(data)
    cloud_type = str(payload.get("type") or "").strip()
    if cloud_type:
        event_payload["type"] = CLOUDEVENT_TYPE_TO_ENGINE_EVENT.get(cloud_type, cloud_type)
    if payload.get("id") and "event_id" not in event_payload:
        event_payload["event_id"] = payload["id"]
    if payload.get("time") and "timestamp" not in event_payload:
        try:
            dt = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
            event_payload["timestamp"] = int(dt.astimezone(UTC).timestamp() * 1000)
        except ValueError:
            pass
    if payload.get("traceparent") and "traceparent" not in event_payload:
        event_payload["traceparent"] = payload["traceparent"]
    if payload.get("tracestate") and "tracestate" not in event_payload:
        event_payload["tracestate"] = payload["tracestate"]
    return event_payload
