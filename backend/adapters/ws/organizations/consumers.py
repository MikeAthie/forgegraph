"""
WebSocket consumer for organization-level Command Ops state.

Clients subscribe to the current organization:
  ws://<backend>/ws/organizations/<organization_id>/state/?ticket=<single_use_ticket>
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
from django.utils import timezone

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
from application.services.organization_state_feed import (
    OrganizationStateFeedReplay,
    latest_organization_state_feed_version,
    organization_state_group_name,
    replay_organization_state_feed_events,
)
from application.services.structured_logging import log_event
from application.services.websocket_subscribers import (
    can_accept_run_websocket_subscriber,
    register_run_websocket_subscriber,
    unregister_run_websocket_subscriber,
    update_run_websocket_subscriber_activity,
)
from infrastructure.orm.models import OrganizationMembership

logger = logging.getLogger(__name__)
SUBSCRIBER_ACTIVITY_FLUSH_INTERVAL_SECONDS = 5.0


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


def _message_type(message: dict[str, Any]) -> str:
    return str(message.get("type") or message.get("event_type") or "").strip()


def _has_state_permission(permissions: list[str]) -> bool:
    return "organizations:state:view" in permissions or "runs:view" in permissions


async def _user_can_access_organization(*, organization_id: str, user_id: UUID) -> bool:
    return bool(
        await database_sync_to_async(
            lambda: OrganizationMembership.objects.filter(
                organization_id=UUID(str(organization_id)),
                user_id=user_id,
            ).exists()
        )()
    )


class OrganizationStateConsumer(AsyncJsonWebsocketConsumer):  # type: ignore[misc]
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

        organization_id = str(
            self.scope.get("url_route", {}).get("kwargs", {}).get("organization_id") or ""
        )
        ticket_organization_id = str(self.scope.get("organization_id") or "")
        permissions = list(self.scope.get("permissions") or [])
        if (
            not organization_id
            or organization_id != ticket_organization_id
            or not _has_state_permission(permissions)
        ):
            record_ws_connection_failure()
            await self.close(code=4403)
            return

        if not await _user_can_access_organization(
            organization_id=organization_id,
            user_id=user.id,
        ):
            record_ws_connection_failure()
            await self.close(code=4403)
            return

        query_params = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
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
                "organization_ws_connection_limit_rejected",
                user_id=str(user.id),
                tenant_id=organization_id,
                reason=str(limit_details.get("code") or "connection_limit"),
                counts=limit_details.get("counts"),
                limits=limit_details.get("limits"),
            )
            await self.close(code=4429)
            return

        self.organization_id = organization_id
        self.user_id = str(user.id)
        self.permissions = permissions
        self.event_types = set(event_types)
        self.last_seen_event_id = last_seen_event_id
        self.last_seen_state_version = last_seen_state_version
        self.connection_id = str(uuid4())
        self.group_name = organization_state_group_name(organization_id=organization_id)
        self._ws_connected = False
        self._subscriber_activity_pending: dict[str, Any] = {}

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        self._ws_connected = True
        await sync_to_async(register_run_websocket_subscriber, thread_sensitive=False)(
            connection_id=self.connection_id,
            run_id="",
            organization_id=self.organization_id,
            user_id=self.user_id,
            event_level="organization",
            event_types=event_types,
            last_seen_event_id=last_seen_event_id,
            last_seen_state_version=last_seen_state_version,
        )
        self.subscriber_activity_task = asyncio.create_task(self._subscriber_activity_loop())
        record_ws_connected()
        log_event(
            logger,
            logging.INFO,
            "organization_ws_connected",
            user_id=str(user.id),
            tenant_id=self.organization_id,
            connection_id=self.connection_id,
            event_types=event_types,
        )

        replay = await self._load_replay(
            last_seen_state_version=last_seen_state_version,
            last_seen_event_id=last_seen_event_id,
        )
        await self._send_public_message(
            self._control_message(
                "connection_established",
                state_version=replay.latest_state_version,
                payload={
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
    ) -> OrganizationStateFeedReplay:
        if last_seen_event_id and last_seen_state_version <= 0:
            latest_version = await sync_to_async(
                latest_organization_state_feed_version,
                thread_sensitive=True,
            )(organization_id=self.organization_id)
            await self._record_replay_failure("state_version_required")
            return OrganizationStateFeedReplay(
                events=[],
                latest_state_version=latest_version,
                full_resync_required=True,
                reason="state_version_required",
            )

        replay = await sync_to_async(
            replay_organization_state_feed_events,
            thread_sensitive=True,
        )(
            organization_id=self.organization_id,
            after_state_version=last_seen_state_version,
            event_types=cast(set[str], getattr(self, "event_types", set())),
        )
        if replay.full_resync_required:
            await self._record_replay_failure(replay.reason)
        return replay

    async def _record_replay_failure(self, reason: str) -> None:
        await sync_to_async(record_service_metric_sample, thread_sensitive=False)(
            metric_name="websocket_replay_failure",
            source="organization_state_websocket_consumer",
            value=1,
            unit="count",
            organization_id=str(getattr(self, "organization_id", "") or "") or None,
            dimensions={"reason": str(reason or "unknown")},
        )

    async def _heartbeat_loop(self) -> None:
        interval = int(
            getattr(
                settings,
                "ORG_WS_HEARTBEAT_INTERVAL_SECONDS",
                getattr(settings, "RUN_WS_HEARTBEAT_INTERVAL_SECONDS", 12),
            )
        )
        try:
            while True:
                await asyncio.sleep(interval)
                await self._send_public_message(
                    self._control_message(
                        "heartbeat",
                        state_version=int(getattr(self, "last_seen_state_version", 0) or 0),
                    )
                )
                self._queue_subscriber_activity(heartbeat=True)
        except asyncio.CancelledError:
            return

    def _control_message(
        self,
        message_type: str,
        *,
        state_version: int,
        payload: dict[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "type": message_type,
            "event_type": message_type,
            "event_id": "",
            "organization_id": str(getattr(self, "organization_id", "") or ""),
            "state_version": state_version,
            "requires_refetch": message_type == "full_resync_required",
            "resource": {
                "type": "organization",
                "id": str(getattr(self, "organization_id", "") or ""),
            },
            "occurred_at": timezone.now().isoformat(),
            "payload": payload or {},
        }
        if reason:
            message["reason"] = reason
            message["payload"] = {**message["payload"], "reason": reason}
        return message

    async def _send_public_message(self, message: dict[str, Any]) -> None:
        timeout_seconds = float(
            getattr(
                settings,
                "ORG_WS_SEND_TIMEOUT_SECONDS",
                getattr(settings, "RUN_WS_SEND_TIMEOUT_SECONDS", 2.0),
            )
        )
        start = time.perf_counter()
        try:
            await asyncio.wait_for(self.send_json(message), timeout=timeout_seconds)
        except TimeoutError:
            record_ws_message_dropped("send_timeout")
            record_ws_slow_client_disconnect("send_timeout")
            self._queue_subscriber_activity(
                event_type=_message_type(message),
                event_id=str(message.get("event_id") or ""),
                dropped=True,
                slow_disconnect=True,
                slow_disconnect_reason="send_timeout",
            )
            await self._flush_subscriber_activity()
            log_event(
                logger,
                logging.WARNING,
                "organization_ws_slow_client_disconnect",
                tenant_id=str(getattr(self, "organization_id", "") or ""),
                connection_id=str(getattr(self, "connection_id", "") or ""),
                reason="send_timeout",
                event_type=_message_type(message),
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
            source="organization_state_websocket_consumer",
            value=duration_ms,
            unit="ms",
            organization_id=str(getattr(self, "organization_id", "") or "") or None,
            dimensions={
                "event_type": _message_type(message),
                "event_id": str(message.get("event_id") or ""),
                "state_version": state_version,
            },
        )
        self._queue_subscriber_activity(
            event_type=_message_type(message),
            event_id=str(message.get("event_id") or ""),
            state_version=state_version,
            sent=True,
        )

    def _queue_subscriber_activity(self, **kwargs: Any) -> None:
        pending = getattr(self, "_subscriber_activity_pending", {})
        for counter_key in ("sent", "dropped", "filtered", "heartbeat"):
            if kwargs.pop(counter_key, False):
                count_key = f"{counter_key}_count"
                pending[count_key] = int(pending.get(count_key) or 0) + 1
        state_version = kwargs.pop("state_version", None)
        if state_version is not None:
            pending["state_version"] = max(
                int(pending.get("state_version") or 0),
                int(state_version),
            )
        for key, value in kwargs.items():
            if value is not None and value != "" and value is not False:
                pending[key] = value
        self._subscriber_activity_pending = pending

    async def _subscriber_activity_loop(self) -> None:
        try:
            interval = float(
                getattr(
                    settings,
                    "WS_SUBSCRIBER_ACTIVITY_FLUSH_INTERVAL_SECONDS",
                    SUBSCRIBER_ACTIVITY_FLUSH_INTERVAL_SECONDS,
                )
            )
        except (TypeError, ValueError):
            interval = SUBSCRIBER_ACTIVITY_FLUSH_INTERVAL_SECONDS
        interval = max(interval, 1.0)
        try:
            while True:
                await asyncio.sleep(interval)
                await self._flush_subscriber_activity()
        except asyncio.CancelledError:
            return

    async def _flush_subscriber_activity(self) -> None:
        pending = dict(getattr(self, "_subscriber_activity_pending", {}) or {})
        if not pending:
            return
        self._subscriber_activity_pending = {}
        await sync_to_async(update_run_websocket_subscriber_activity, thread_sensitive=False)(
            connection_id=str(getattr(self, "connection_id", "") or ""),
            **pending,
        )

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        message_type = str(content.get("type") or "").strip().lower()
        if message_type == "pong":
            self._queue_subscriber_activity(heartbeat=True)
            return
        if message_type in {"resume", "resync"}:
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
            )
            if not replay.full_resync_required:
                for replay_message in replay.events:
                    await self._send_public_message(replay_message)
            await self._send_public_message(
                self._control_message(
                    "full_resync_required" if replay.full_resync_required else "replay_complete",
                    state_version=replay.latest_state_version,
                    reason=replay.reason if replay.full_resync_required else "",
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
        subscriber_activity_task = getattr(self, "subscriber_activity_task", None)
        if subscriber_activity_task is not None:
            subscriber_activity_task.cancel()
        await self._flush_subscriber_activity()
        group_name = str(getattr(self, "group_name", "") or "")
        if group_name:
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
                "organization_ws_disconnected",
                user_id=str(getattr(user, "id", "") or ""),
                tenant_id=str(getattr(self, "organization_id", "") or ""),
                connection_id=str(getattr(self, "connection_id", "") or ""),
                status=str(code),
            )

    async def broadcast_message(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if not isinstance(message, dict):
            return
        event_types = cast(set[str], getattr(self, "event_types", set()))
        public_type = _message_type(message)
        if event_types and public_type not in event_types:
            record_ws_message_filtered()
            self._queue_subscriber_activity(
                event_type=public_type,
                event_id=str(message.get("event_id") or ""),
                filtered=True,
            )
            return
        await self._send_public_message(message)
