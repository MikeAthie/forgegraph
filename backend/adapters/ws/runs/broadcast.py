"""
Broadcast helpers for Run WebSocket events.
"""

from __future__ import annotations

import uuid
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from adapters.api.runs.serializers import NodeRunSerializer, RunDeltaBroadcastSerializer
from application.services.run_event_streaming import (
    EVENT_LEVEL_DEFAULT,
    EVENT_LEVEL_MINIMAL,
from application.services.run_event_streaming import (
    EVENT_LEVEL_IMPORTANT,
    STREAM_SUMMARY_EVENT_TYPE,
    add_event_level,
    classify_transport_event_level,
    run_event_group_name,
)
from application.services.run_ws_protocol import build_ws_public_message
from infrastructure.orm.models import NodeRun, Run


def _send_to_run_group(*, run_id: str, message: dict[str, Any]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    event_level = str(
        message.get("level")
        or classify_transport_event_level(str(message.get("type") or ""), _message_payload(message))
    )
    async_to_sync(channel_layer.group_send)(
        run_event_group_name(run_id=run_id, level=event_level),
        {
            "type": "broadcast.message",
            "message": message,
        },
    )


def _message_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("run", "node_run", "node_stream", "payload"):
        payload = message.get(key)
        if isinstance(payload, dict):
            return payload
    return None


def broadcast_run_updated(run: Run) -> dict[str, Any]:
    message = add_event_level(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": timezone.now().isoformat(),
            "type": "run.updated",
            "run_id": str(run.id),
            "trace_id": run.trace_id,
            "run": RunDeltaBroadcastSerializer(run).data,
        }
    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_node_run_updated(*, run: Run, node_run: NodeRun) -> dict[str, Any]:
    payload = NodeRunSerializer(node_run).data
    message = add_event_level(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": timezone.now().isoformat(),
            "type": "node_run.updated",
            "run_id": str(run.id),
            "trace_id": node_run.trace_id or run.trace_id,
            "node_run": payload,
        },
        payload=payload,
    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_run_schema_validation(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    message = add_event_level(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": timezone.now().isoformat(),
            "type": "run.schema_validation",
            "run_id": str(run.id),
            "trace_id": run.trace_id,
            "payload": payload,
        },
        payload=payload,
    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_node_stream_chunk(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    message = {
        "event_id": str(uuid.uuid4()),
        "timestamp": timezone.now().isoformat(),
        "type": "node_stream.chunk",
        "run_id": str(run.id),
        "node_stream": payload,
    }
    message = add_event_level(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": timezone.now().isoformat(),
            "type": "node_stream.chunk",
            "run_id": str(run.id),
            "trace_id": run.trace_id,
            "node_stream": payload,
        },
        payload=payload,
    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_node_stream_summary(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    message = add_event_level(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": timezone.now().isoformat(),
            "type": STREAM_SUMMARY_EVENT_TYPE,
            "run_id": str(run.id),
            "trace_id": run.trace_id,
            "node_stream": payload,
        },
        payload=payload,
        level=EVENT_LEVEL_DEFAULT,
    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_transport_event(
    *,
    run: Run,
    event_type: str,
    payload: dict[str, Any],
    level: str | None = None,
) -> dict[str, Any]:
    message = add_event_level(
        build_ws_public_message(
            event_type,
            run_id=str(run.id),
            trace_id=run.trace_id,
            payload=payload,
        ),
        payload=payload,
        level=level,

        level=EVENT_LEVEL_IMPORTANT,

    )
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_decision_required(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    return broadcast_transport_event(
        run=run,
        event_type="decision_required",
        payload=payload,
        level=EVENT_LEVEL_MINIMAL,
    )


def broadcast_decision_resolved(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    return broadcast_transport_event(
        run=run,
        event_type="decision_resolved",
        payload=payload,
        level=EVENT_LEVEL_MINIMAL,
    )


def broadcast_cost_update(*, run: Run, payload: dict[str, Any]) -> dict[str, Any]:
    return broadcast_transport_event(
        run=run,
        event_type="cost_update",
        payload=payload,
        level=EVENT_LEVEL_DEFAULT,
    )
