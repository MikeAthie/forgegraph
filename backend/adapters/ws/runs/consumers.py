"""
WebSocket consumer for live Run updates.

Clients subscribe to a specific run:
  ws://<backend>/ws/runs/<run_id>/?token=<access_jwt>
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

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

        self.run_id = run_id
        self.group_name = f"run_{run_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_json(
            {
                "type": "connected",
                "run_id": self.run_id,
            }
        )

    async def disconnect(self, code: int) -> None:
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def broadcast_message(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if message is None:
            return
        await self.send_json(message)
