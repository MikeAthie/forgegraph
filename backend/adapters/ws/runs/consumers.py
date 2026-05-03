"""
WebSocket consumer for live Run updates.

Clients subscribe to a specific run:
  ws://<backend>/ws/runs/<run_id>/?ticket=<single_use_ticket>
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, cast
from urllib.parse import parse_qs
from uuid import UUID, uuid4

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q

from application.services.metrics import (
    record_service_metric_sample,
    record_ws_connected,
    record_ws_connection_failure,
    record_ws_disconnected,
    record_ws_message_dropped,
    record_ws_message_filtered,
    record_ws_message_sent,
    record_ws_slow_client_disconnect,
)
from application.services.run_event_streaming import (
    event_levels_for_subscription,
    normalize_requested_event_level,
    run_event_group_name,
)
from application.services.run_ws_protocol import (
    build_ws_public_message,
    normalize_ws_public_message,
)
from application.services.structured_logging import log_event
from application.services.websocket_subscribers import (
    can_accept_run_websocket_subscriber,
    register_run_websocket_subscriber,
    unregister_run_websocket_subscriber,
    update_run_websocket_subscriber_activity,
)
from infrastructure.orm.models import Run

logger = logging.getLogger(__name__)


def _query_values(query_params: dict[str, list[str]], *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        for raw_value in query_params.get(name, []):
            values.extend(part.strip() for part in raw_value.split(",") if part.strip())
    return values


async def _user_can_access_run(*, run_id: str, user_id: UUID, organization_id: str) -> bool:
    org_uuid = UUID(organization_id)
    return bool(
        await database_sync_to_async(
            lambda: Run.objects.filter(
                id=run_id,
            )
            .filter(
                Q(organization_id=org_uuid, organization__memberships__user_id=user_id)
                | Q(
                    organization__isnull=True,
                    owner__default_organization_id=org_uuid,
                    owner__default_organization__memberships__user_id=user_id,
                )
            )
            .exists()
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

        query_params = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        requested_level = normalize_requested_event_level(
            next(iter(query_params.get("event_level", [])), None)
        )
        event_types = sorted(set(_query_values(query_params, "events", "event_types")))
        last_seen_event_id = str(
            next(iter(query_params.get("last_event_id", [])), "") or ""
        ).strip()
        accepted, limit_details = await sync_to_async(
            can_accept_run_websocket_subscriber,
            thread_sensitive=False,
        )(
            organization_id=organization_id,
            user_id=str(user.id),
        )
        if not accepted:
            record_ws_connection_failure()
            log_event(
                logger,
                logging.WARNING,
                "ws_connection_limit_rejected",
                user_id=str(user.id),
                run_id=run_id,
                tenant_id=organization_id,
                reason=str(limit_details.get("code") or "connection_limit"),
                counts=limit_details.get("counts"),
                limits=limit_details.get("limits"),
            )
            await self.close(code=4429)
            return

        self.run_id = run_id
        self.group_name = f"run_{run_id}"
        self.organization_id = organization_id
        self.user_id = str(user.id)
        self.permissions = permissions
        self.event_types = set(event_types)
        self.last_seen_event_id = last_seen_event_id
        self.connection_id = str(uuid4())
        self._ws_connected = False
        self.group_names = [
            run_event_group_name(run_id=run_id, level=level)
            for level in event_levels_for_subscription(requested_level)
        ]

        for group_name in self.group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)
        await self.accept()

        self._ws_connected = True
        await sync_to_async(register_run_websocket_subscriber, thread_sensitive=False)(
            connection_id=self.connection_id,
            run_id=self.run_id,
            organization_id=self.organization_id,
            user_id=self.user_id,
            event_level=requested_level,
            event_types=event_types,
            last_seen_event_id=last_seen_event_id,
        )
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
            event_types=event_types,
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
                    "event_types": event_types,
                    "last_seen_event_id": last_seen_event_id,
                    "resync_required": True,
                    "replay_supported": False,
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
                await sync_to_async(
                    update_run_websocket_subscriber_activity,
                    thread_sensitive=False,
                )(
                    connection_id=self.connection_id,
                    heartbeat=True,
                )
        except asyncio.CancelledError:
            return

    async def _send_public_message(self, message: dict[str, Any]) -> None:
        timeout_seconds = float(getattr(settings, "RUN_WS_SEND_TIMEOUT_SECONDS", 2.0))
        start = time.perf_counter()
        try:
            await asyncio.wait_for(self.send_json(message), timeout=timeout_seconds)
        except TimeoutError:
            record_ws_message_dropped("send_timeout")
            record_ws_slow_client_disconnect("send_timeout")
            await sync_to_async(
                update_run_websocket_subscriber_activity,
                thread_sensitive=False,
            )(
                connection_id=str(getattr(self, "connection_id", "") or ""),
                event_type=str(message.get("type") or ""),
                event_id=str(message.get("event_id") or ""),
                dropped=True,
                slow_disconnect=True,
                slow_disconnect_reason="send_timeout",
            )
            log_event(
                logger,
                logging.WARNING,
                "ws_slow_client_disconnect",
                run_id=str(getattr(self, "run_id", "") or ""),
                tenant_id=str(getattr(self, "organization_id", "") or ""),
                connection_id=str(getattr(self, "connection_id", "") or ""),
                reason="send_timeout",
                event_type=str(message.get("type") or ""),
            )
            await self.close(code=1013)
            return
        duration_ms = int((time.perf_counter() - start) * 1000)
        record_ws_message_sent(duration_ms=duration_ms)
        await sync_to_async(record_service_metric_sample, thread_sensitive=False)(
            metric_name="websocket_delivery_ms",
            source="run_websocket_consumer",
            value=duration_ms,
            unit="ms",
            organization_id=str(getattr(self, "organization_id", "") or "") or None,
            run_id=str(getattr(self, "run_id", "") or "") or None,
            dimensions={
                "event_type": str(message.get("type") or ""),
                "event_id": str(message.get("event_id") or ""),
            },
        )
        await sync_to_async(
            update_run_websocket_subscriber_activity,
            thread_sensitive=False,
        )(
            connection_id=str(getattr(self, "connection_id", "") or ""),
            event_type=str(message.get("type") or ""),
            event_id=str(message.get("event_id") or ""),
            sent=True,
        )

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        message_type = str(content.get("type") or "").strip().lower()
        if message_type == "pong":
            await sync_to_async(
                update_run_websocket_subscriber_activity,
                thread_sensitive=False,
            )(
                connection_id=str(getattr(self, "connection_id", "") or ""),
                heartbeat=True,
            )
            return
        if message_type == "resync":
            await self._send_public_message(
                build_ws_public_message(
                    "resync_required",
                    run_id=str(getattr(self, "run_id", "") or ""),
                    payload={
                        "reason": "client_requested",
                        "replay_supported": False,
                    },
                )
            )

    async def disconnect(self, code: int) -> None:
        heartbeat_task = getattr(self, "heartbeat_task", None)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        group_names = getattr(self, "group_names", None) or []
        for group_name in group_names:
            await self.channel_layer.group_discard(group_name, self.channel_name)
        if getattr(self, "_ws_connected", False):
            await sync_to_async(unregister_run_websocket_subscriber, thread_sensitive=False)(
                connection_id=str(getattr(self, "connection_id", "") or "")
            )
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
            record_ws_message_dropped("invalid_public_message")
            return
        event_types = cast(set[str], getattr(self, "event_types", set()))
        public_type = str(public_message.get("type") or "")
        if event_types and public_type not in event_types:
            record_ws_message_filtered()
            await sync_to_async(
                update_run_websocket_subscriber_activity,
                thread_sensitive=False,
            )(
                connection_id=str(getattr(self, "connection_id", "") or ""),
                event_type=public_type,
                event_id=str(public_message.get("event_id") or ""),
                filtered=True,
            )
            return
        await self._send_public_message(public_message)
