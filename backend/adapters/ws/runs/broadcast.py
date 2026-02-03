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
from infrastructure.orm.models import NodeRun, Run


def _send_to_run_group(*, run_id: str, message: dict[str, Any]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"run_{run_id}",
        {
            "type": "broadcast.message",
            "message": message,
        },
    )


def broadcast_run_updated(run: Run) -> dict[str, Any]:
    message = {
        "event_id": str(uuid.uuid4()),
        "timestamp": timezone.now().isoformat(),
        "type": "run.updated",
        "run_id": str(run.id),
        "run": RunDeltaBroadcastSerializer(run).data,
    }
    _send_to_run_group(run_id=str(run.id), message=message)
    return message


def broadcast_node_run_updated(*, run: Run, node_run: NodeRun) -> dict[str, Any]:
    message = {
        "event_id": str(uuid.uuid4()),
        "timestamp": timezone.now().isoformat(),
        "type": "node_run.updated",
        "run_id": str(run.id),
        "node_run": NodeRunSerializer(node_run).data,
    }
    _send_to_run_group(run_id=str(run.id), message=message)
    return message
