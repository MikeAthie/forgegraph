from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import OperationalError, transaction
from django.db.models import Max
from django.utils import timezone

from application.services.metrics import record_service_metric_sample
from application.services.structured_logging import log_event
from infrastructure.orm.models import (
    Organization,
    OrganizationStateFeedEvent,
    OrganizationStateFeedSequence,
)

logger = logging.getLogger(__name__)

ORGANIZATION_STATE_EVENT_TYPES = {
    "overview.updated",
    "task.created",
    "task.updated",
    "decision.created",
    "decision.updated",
    "agent.updated",
    "memory.created",
    "accounting.updated",
    "dead_letter.created",
    "projection.stale",
    "projection.recovered",
}

_DEADLOCK_RETRY_ATTEMPTS = 3
_BROADCAST_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="org-state-feed")


@dataclass(frozen=True, slots=True)
class OrganizationStateFeedReplay:
    events: list[dict[str, Any]]
    latest_state_version: int
    full_resync_required: bool
    reason: str = ""


def organization_state_group_name(*, organization_id: str) -> str:
    return f"organization_state_{organization_id}"


def build_organization_state_message(
    *,
    organization_id: str,
    event_type: str,
    event_id: str,
    state_version: int,
    resource_type: str,
    resource_id: str,
    requires_refetch: bool,
    occurred_at: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "event_type": event_type,
        "event_id": event_id,
        "organization_id": organization_id,
        "state_version": state_version,
        "requires_refetch": requires_refetch,
        "resource": {
            "type": resource_type,
            "id": resource_id,
        },
        "occurred_at": occurred_at,
        "payload": payload or {},
    }


def record_organization_state_feed_event(
    *,
    organization: Organization,
    event_type: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
    event_id: str = "",
    requires_refetch: bool = True,
    occurred_at: Any | None = None,
) -> dict[str, Any]:
    message, _ = _record_organization_state_feed_event(
        organization=organization,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
        event_id=event_id,
        requires_refetch=requires_refetch,
        occurred_at=occurred_at,
    )
    return message


def _record_organization_state_feed_event(
    *,
    organization: Organization,
    event_type: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
    event_id: str = "",
    requires_refetch: bool = True,
    occurred_at: Any | None = None,
) -> tuple[dict[str, Any], bool]:
    for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
        try:
            return _record_organization_state_feed_event_once(
                organization=organization,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                event_id=event_id,
                requires_refetch=requires_refetch,
                occurred_at=occurred_at,
            )
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("unreachable organization state-feed retry state")


def _record_organization_state_feed_event_once(
    *,
    organization: Organization,
    event_type: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
    event_id: str = "",
    requires_refetch: bool = True,
    occurred_at: Any | None = None,
) -> tuple[dict[str, Any], bool]:
    normalized_type = str(event_type or "").strip()
    if not normalized_type:
        raise ValueError("Organization state feed event_type is required.")

    event_id_value = str(event_id or uuid4()).strip()
    resource_type_value = str(resource_type or "overview").strip()[:64]
    resource_id_value = str(resource_id or organization.id).strip()[:128]
    occurred_at_value = occurred_at or timezone.now()
    occurred_at_iso = (
        occurred_at_value.isoformat()
        if hasattr(occurred_at_value, "isoformat")
        else str(occurred_at_value)
    )

    organization_id = organization.id
    with transaction.atomic():
        duplicate = OrganizationStateFeedEvent.objects.filter(
            organization_id=organization_id,
            event_id=event_id_value,
        ).first()
        if duplicate is not None:
            return dict(duplicate.message), False

        sequence, _ = OrganizationStateFeedSequence.objects.select_for_update().get_or_create(
            organization_id=organization_id,
            defaults={"next_sequence": 1},
        )
        state_version = int(sequence.next_sequence)
        sequence.next_sequence = state_version + 1
        sequence.save(update_fields=["next_sequence", "updated_at"])

        message = build_organization_state_message(
            organization_id=str(organization_id),
            event_type=normalized_type,
            event_id=event_id_value,
            state_version=state_version,
            resource_type=resource_type_value,
            resource_id=resource_id_value,
            requires_refetch=requires_refetch,
            occurred_at=occurred_at_iso,
            payload=payload,
        )
        OrganizationStateFeedEvent.objects.create(
            organization_id=organization_id,
            event_id=event_id_value,
            state_version=state_version,
            type=normalized_type,
            resource_type=resource_type_value,
            resource_id=resource_id_value,
            requires_refetch=requires_refetch,
            message=message,
            occurred_at=occurred_at_value
            if hasattr(occurred_at_value, "tzinfo")
            else timezone.now(),
        )
        return message, True


def publish_organization_state_feed_event(
    *,
    organization: Organization,
    event_type: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
    event_id: str = "",
    requires_refetch: bool = True,
    occurred_at: Any | None = None,
    async_broadcast: bool = False,
) -> dict[str, Any]:
    message, created = _record_organization_state_feed_event(
        organization=organization,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
        event_id=event_id,
        requires_refetch=requires_refetch,
        occurred_at=occurred_at,
    )
    if created:
        if async_broadcast:
            transaction.on_commit(
                lambda: _BROADCAST_EXECUTOR.submit(
                    broadcast_organization_state_message,
                    message,
                )
            )
        else:
            transaction.on_commit(lambda: broadcast_organization_state_message(message))
    return message


def broadcast_organization_state_message(message: dict[str, Any]) -> None:
    organization_id = str(message.get("organization_id") or "").strip()
    if not organization_id:
        return
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            organization_state_group_name(organization_id=organization_id),
            {
                "type": "broadcast.message",
                "message": message,
            },
        )
    except Exception as exc:
        record_service_metric_sample(
            metric_name="organization_state_feed_broadcast_failed_total",
            source="organization_state_feed",
            value=1,
            unit="count",
            organization_id=organization_id,
            dimensions={
                "event_type": str(message.get("type") or message.get("event_type") or ""),
                "reason": exc.__class__.__name__,
            },
        )
        log_event(
            logger,
            logging.WARNING,
            "organization_state_feed_broadcast_failed",
            tenant_id=organization_id,
            event_id=str(message.get("event_id") or ""),
            reason=exc.__class__.__name__,
        )


def replay_organization_state_feed_events(
    *,
    organization_id: str | UUID,
    after_state_version: int,
    event_types: set[str] | list[str] | tuple[str, ...] | None = None,
    replay_limit: int | None = None,
) -> OrganizationStateFeedReplay:
    org_uuid = UUID(str(organization_id))
    latest_state_version = latest_organization_state_feed_version(organization_id=org_uuid)
    if after_state_version <= 0 or latest_state_version <= after_state_version:
        return OrganizationStateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=False,
            reason="up_to_date" if latest_state_version <= after_state_version else "no_cursor",
        )

    max_events = _replay_limit(replay_limit)
    rows = list(
        OrganizationStateFeedEvent.objects.filter(
            organization_id=org_uuid,
            state_version__gt=after_state_version,
        ).order_by("state_version")[: max_events + 1]
    )
    if not rows:
        return OrganizationStateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_window_expired",
        )
    if len(rows) > max_events:
        return OrganizationStateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_window_exceeded",
        )
    if int(rows[0].state_version) > after_state_version + 1:
        return OrganizationStateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_window_expired",
        )

    allowed_types = {str(event_type) for event_type in event_types or [] if str(event_type)}
    messages: list[dict[str, Any]] = []
    for row in rows:
        if allowed_types and row.type not in allowed_types:
            continue
        messages.append(dict(row.message))

    return OrganizationStateFeedReplay(
        events=messages,
        latest_state_version=latest_state_version,
        full_resync_required=False,
        reason="replayed",
    )


def latest_organization_state_feed_version(*, organization_id: str | UUID) -> int:
    value = (
        OrganizationStateFeedEvent.objects.filter(
            organization_id=UUID(str(organization_id)),
        ).aggregate(value=Max("state_version"))["value"]
        or 0
    )
    return int(value)


def _replay_limit(value: int | None) -> int:
    configured = value if value is not None else getattr(settings, "ORG_WS_REPLAY_LIMIT", 500)
    try:
        return max(int(configured), 1)
    except (TypeError, ValueError):
        return 500


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()
