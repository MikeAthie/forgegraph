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
from application.services.state_feed import (
    StateFeedReplay,
    latest_state_feed_version,
    replay_state_feed_events,
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


def _query_int(query_params: dict[str, list[str]], name: str, default: int = 0) -> int:
    raw_value = next(iter(query_params.get(name, [])), "")
    try:
        return max(int(raw_value), 0)
    except (TypeError, ValueError):
        return default


def _message_state_version(message: dict[str, Any]) -> int:
    try:
        return max(int(message.get("state_version") or 0), 0)
    except (TypeError, ValueError):
        return 0


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
        last_seen_state_version = _query_int(query_params, "last_seen_state_version")
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
        self.last_seen_state_version = last_seen_state_version
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
            last_seen_state_version=last_seen_state_version,
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
        replay = await self._load_replay(
            last_seen_state_version=last_seen_state_version,
            last_seen_event_id=last_seen_event_id,
            event_level=requested_level,
        )
        await self._send_public_message(
            build_ws_public_message(
                "connection_established",
                run_id=self.run_id,
                tenant_id=self.organization_id,
                payload={
                    "event_level": requested_level,
                    "organization_id": self.organization_id,
                    "user_id": str(user.id),
                    "permissions": self.permissions,
                    "event_types": event_types,
                    "last_seen_event_id": last_seen_event_id,
                    "last_seen_state_version": last_seen_state_version,
                    "latest_state_version": replay.latest_state_version,
                    "resync_required": replay.full_resync_required,
                    "full_resync_required": replay.full_resync_required,
                    "replay_supported": True,
                    "replayed_count": len(replay.events),
                    "replay_reason": replay.reason,
                },
            )
        )
        for replay_message in replay.events:
            await self._send_public_message(replay_message)
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _load_replay(
        self,
        *,
        last_seen_state_version: int,
        last_seen_event_id: str = "",
        event_level: str = "default",
    ) -> StateFeedReplay:
        if last_seen_event_id and last_seen_state_version <= 0:
            latest_version = await sync_to_async(latest_state_feed_version, thread_sensitive=True)(
                run_id=self.run_id,
                organization_id=self.organization_id,
            )
            await self._record_replay_failure("state_version_required")
            return StateFeedReplay(
                events=[],
                latest_state_version=latest_version,
                full_resync_required=True,
                reason="state_version_required",
            )

        replay = await sync_to_async(replay_state_feed_events, thread_sensitive=True)(
            run_id=self.run_id,
            organization_id=self.organization_id,
            after_state_version=last_seen_state_version,
            event_types=cast(set[str], getattr(self, "event_types", set())),
            event_level=event_level,
        )
        if replay.full_resync_required:
            await self._record_replay_failure(replay.reason)
        return replay

    async def _record_replay_failure(self, reason: str) -> None:
        await sync_to_async(record_service_metric_sample, thread_sensitive=False)(
            metric_name="websocket_replay_failure",
            source="run_websocket_consumer",
            value=1,
            unit="count",
            organization_id=str(getattr(self, "organization_id", "") or "") or None,
            run_id=str(getattr(self, "run_id", "") or "") or None,
            dimensions={"reason": str(reason or "unknown")},
        )

    async def _heartbeat_loop(self) -> None:
        interval = int(getattr(settings, "RUN_WS_HEARTBEAT_INTERVAL_SECONDS", 12))
        try:
            while True:
                await asyncio.sleep(interval)
                await self._send_public_message(
                    build_ws_public_message(
                        "heartbeat",
                        run_id=self.run_id,
                        tenant_id=self.organization_id,
                        state_version=int(getattr(self, "last_seen_state_version", 0) or 0),
                    )
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
        state_version = _message_state_version(message)
        if state_version > int(getattr(self, "last_seen_state_version", 0) or 0):
            self.last_seen_state_version = state_version
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
                "state_version": state_version,
            },
        )
        await sync_to_async(
            update_run_websocket_subscriber_activity,
            thread_sensitive=False,
        )(
            connection_id=str(getattr(self, "connection_id", "") or ""),
            event_type=str(message.get("type") or ""),
            event_id=str(message.get("event_id") or ""),
            state_version=state_version,
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
            requested_state_version = content.get("last_seen_state_version")
            try:
                if requested_state_version is None:
                    raise TypeError("last_seen_state_version missing")
                last_seen_state_version = max(int(requested_state_version), 0)
            except (TypeError, ValueError):
                last_seen_state_version = int(getattr(self, "last_seen_state_version", 0) or 0)
            last_seen_event_id = str(
                content.get("last_event_id") or getattr(self, "last_seen_event_id", "") or ""
            )
            replay = await self._load_replay(
                last_seen_state_version=last_seen_state_version,
                last_seen_event_id=last_seen_event_id,
                event_level=normalize_requested_event_level(
                    str(content.get("event_level") or "default")
                ),
            )
            if not replay.full_resync_required:
                for replay_message in replay.events:
                    await self._send_public_message(replay_message)
            await self._send_public_message(
                build_ws_public_message(
                    "full_resync_required" if replay.full_resync_required else "replay_complete",
                    run_id=str(getattr(self, "run_id", "") or ""),
                    tenant_id=str(getattr(self, "organization_id", "") or ""),
                    payload={
                        "reason": "client_requested",
                        "replay_supported": True,
                        "full_resync_required": replay.full_resync_required,
                        "latest_state_version": replay.latest_state_version,
                        "replayed_count": len(replay.events),
                        "replay_reason": replay.reason,
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
