"""
WebSocket consumer for live Run updates.

Clients subscribe to a specific run:
  ws://<backend>/ws/runs/<run_id>/?token=<access_jwt>
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID
from uuid import uuid4

from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

<<<<<<< Updated upstream
=======
from application.services.metrics import (
    record_ws_connected,
    record_ws_connection_failure,
    record_ws_disconnected,
    record_ws_message_dropped,
    record_ws_message_sent,
)
from application.services.run_event_streaming import (
    event_levels_for_subscription,
    normalize_requested_event_level,
    run_event_group_name,
)
from application.services.run_ws_protocol import build_ws_public_message, normalize_ws_public_message
from application.services.structured_logging import log_event
>>>>>>> Stashed changes
from infrastructure.orm.models import Run

logger = logging.getLogger(__name__)


async def _user_can_access_run(*, run_id: str, user_id: UUID, organization_id: str) -> bool:
    return bool(
        await database_sync_to_async(
            lambda: Run.objects.filter(
                id=run_id,
                owner__default_organization_id=organization_id,
                owner__default_organization__memberships__user_id=user_id,
            ).exists()
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
            record_ws_connection_failure()
            await self.close(code=4401)
            return

        run_id = self.scope.get("url_route", {}).get("kwargs", {}).get("run_id")
        if not run_id:
            record_ws_connection_failure()
            await self.close(code=4400)
            return

        run_id = str(run_id)
        organization_id = str(self.scope.get("organization_id") or "")
        permissions = list(self.scope.get("permissions") or [])
        if not organization_id or "runs:view" not in permissions:
            record_ws_connection_failure()
            await self.close(code=4403)
            return

        if not await _user_can_access_run(
            run_id=run_id,
            user_id=user.id,
            organization_id=organization_id,
        ):
            record_ws_connection_failure()
            await self.close(code=4403)
            return

        self.run_id = run_id
<<<<<<< Updated upstream
        self.group_name = f"run_{run_id}"
=======
        self.organization_id = organization_id
        self.permissions = permissions
        self.connection_id = str(uuid4())
        self._ws_connected = False
        self.group_names = [
            run_event_group_name(run_id=run_id, level=level)
            for level in event_levels_for_subscription(requested_level)
        ]
>>>>>>> Stashed changes

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
<<<<<<< Updated upstream

        await self.send_json(
            {
                "type": "connected",
                "run_id": self.run_id,
            }
=======
        self._ws_connected = True
        record_ws_connected()
        log_event(
            logger,
            logging.INFO,
            "ws_connected",
            user_id=str(user.id),
            run_id=self.run_id,
            tenant_id=self.organization_id,
            connection_id=self.connection_id,
            event_level=requested_level,
>>>>>>> Stashed changes
        )
        await self._send_public_message(
            build_ws_public_message(
                "connection_established",
                run_id=self.run_id,
                payload={
                    "event_level": requested_level,
                    "organization_id": self.organization_id,
                    "user_id": str(user.id),
                    "permissions": self.permissions,
                },
            )
        )
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        interval = int(getattr(settings, "RUN_WS_HEARTBEAT_INTERVAL_SECONDS", 12))
        try:
            while True:
                await asyncio.sleep(interval)
                await self._send_public_message(
                    build_ws_public_message("heartbeat", run_id=self.run_id)
                )
        except asyncio.CancelledError:
            return

    async def _send_public_message(self, message: dict[str, Any]) -> None:
        await self.send_json(message)
        record_ws_message_sent()

    async def disconnect(self, code: int) -> None:
<<<<<<< Updated upstream
        group_name = getattr(self, "group_name", None)
        if group_name:
=======
        heartbeat_task = getattr(self, "heartbeat_task", None)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        group_names = getattr(self, "group_names", None) or []
        for group_name in group_names:
>>>>>>> Stashed changes
            await self.channel_layer.group_discard(group_name, self.channel_name)
        if getattr(self, "_ws_connected", False):
            record_ws_disconnected()
            user = self.scope.get("user")
            log_event(
                logger,
                logging.INFO,
                "ws_disconnected",
                user_id=str(getattr(user, "id", "") or ""),
                run_id=str(getattr(self, "run_id", "") or ""),
                tenant_id=str(getattr(self, "organization_id", "") or ""),
                connection_id=str(getattr(self, "connection_id", "") or ""),
                status=str(code),
            )

    async def broadcast_message(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if message is None:
            return
        public_message = normalize_ws_public_message(message)
        if public_message is None:
            record_ws_message_dropped()
            return
        await self._send_public_message(public_message)
