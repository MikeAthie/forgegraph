"""
WebSocket consumer for live Run updates.

Clients subscribe to a specific run:
  ws://<backend>/ws/runs/<run_id>/?ticket=<single_use_ticket>
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from application.services.run_event_streaming import (
    event_levels_for_subscription,
    normalize_requested_event_level,
    run_event_group_name,
)
from infrastructure.orm.models import Run


async def _user_owns_run(*, run_id: str, user_id: UUID) -> bool:
    return bool(
        await database_sync_to_async(
            lambda: Run.objects.filter(id=run_id, owner_id=user_id).exists()
        )()
    )


class RunUpdatesConsumer(AsyncJsonWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        user = self.scope.get("user")
        if (
            not user
            or isinstance(user, AnonymousUser)
            or not getattr(user, "is_authenticated", False)
        ):
            await self.close(code=4401)
            return

        run_id = self.scope.get("url_route", {}).get("kwargs", {}).get("run_id")
        if not run_id:
            await self.close(code=4400)
            return

        run_id = str(run_id)
        if not await _user_owns_run(run_id=run_id, user_id=user.id):
            await self.close(code=4403)
            return

        query_params = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        requested_level = normalize_requested_event_level(
            next(iter(query_params.get("event_level", [])), None)
        )

        self.run_id = run_id
        self.group_names = [
            run_event_group_name(run_id=run_id, level=level)
            for level in event_levels_for_subscription(requested_level)
        ]

        for group_name in self.group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)
        await self.accept()

        await self.send_json(
            {
                "type": "connected",
                "run_id": self.run_id,
                "level": requested_level,
            }
        )

    async def disconnect(self, code: int) -> None:
        group_names = getattr(self, "group_names", None) or []
        for group_name in group_names:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def broadcast_message(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if message is None:
            return
        await self.send_json(message)
