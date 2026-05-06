from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings
from django.db import OperationalError, transaction
from django.db.models import Max, Q

from application.services.run_event_streaming import (
    classify_transport_event_level,
    message_allowed_for_level,
    normalize_requested_event_level,
)
from application.services.run_ws_protocol import normalize_ws_public_message
from infrastructure.orm.models import Organization, Run, StateFeedEvent


@dataclass(frozen=True, slots=True)
class StateFeedReplay:
    events: list[dict[str, Any]]
    latest_state_version: int
    full_resync_required: bool
    reason: str = ""


_DEADLOCK_RETRY_ATTEMPTS = 3


def record_state_feed_event(
    *,
    run: Run,
    message: dict[str, Any],
    requires_refetch: bool = False,
) -> dict[str, Any]:
    """Persist a versioned public WS message and return the versioned message."""

    public_message = normalize_ws_public_message(message)
    if public_message is None:
        raise ValueError("Cannot persist an invalid state-feed message.")

    for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
        try:
            return _record_state_feed_event_once(
                run=run,
                message=message,
                public_message=public_message,
                requires_refetch=requires_refetch,
            )
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("unreachable state-feed retry state")


def _record_state_feed_event_once(
    *,
    run: Run,
    message: dict[str, Any],
    public_message: dict[str, Any],
    requires_refetch: bool,
) -> dict[str, Any]:
    with transaction.atomic():
        locked_run = (
            Run.objects.select_for_update(of=("self",))
            .select_related("organization", "owner__default_organization")
            .get(id=run.id)
        )
        organization = _organization_for_run(locked_run)
        event_id = str(public_message.get("event_id") or message.get("event_id") or uuid4())
        duplicate = StateFeedEvent.objects.filter(run=locked_run, event_id=event_id).first()
        if duplicate is not None:
            return dict(duplicate.message)

        latest_version = (
            StateFeedEvent.objects.filter(run=locked_run).aggregate(value=Max("state_version"))[
                "value"
            ]
            or 0
        )
        state_version = int(latest_version) + 1
        event_level = normalize_requested_event_level(
            str(
                message.get("level")
                or public_message.get("level")
                or classify_transport_event_level(
                    str(message.get("type") or public_message.get("type") or ""),
                    _payload_for_level(message),
                )
            )
        )
        versioned_message = {
            **public_message,
            "event_id": event_id,
            "tenant_id": str(organization.id),
            "state_version": state_version,
            "requires_refetch": requires_refetch,
            "level": event_level,
        }
        StateFeedEvent.objects.create(
            organization=organization,
            run=locked_run,
            event_id=event_id,
            state_version=state_version,
            type=str(versioned_message.get("type") or ""),
            level=event_level,
            requires_refetch=requires_refetch,
            message=versioned_message,
        )
        return versioned_message


def replay_state_feed_events(
    *,
    run_id: str,
    organization_id: str,
    after_state_version: int,
    event_types: set[str] | list[str] | tuple[str, ...] | None = None,
    event_level: str = "default",
    replay_limit: int | None = None,
) -> StateFeedReplay:
    org_uuid = UUID(str(organization_id))
    if not _run_visible_to_organization(run_id=run_id, organization_id=org_uuid):
        return StateFeedReplay(
            events=[],
            latest_state_version=0,
            full_resync_required=True,
            reason="run_not_visible",
        )

    latest_state_version = latest_state_feed_version(
        run_id=run_id,
        organization_id=str(org_uuid),
    )
    if after_state_version <= 0 or latest_state_version <= after_state_version:
        return StateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=False,
            reason="up_to_date" if latest_state_version <= after_state_version else "no_cursor",
        )

    max_events = _replay_limit(replay_limit)
    rows = list(
        StateFeedEvent.objects.filter(
            organization_id=org_uuid,
            run_id=run_id,
            state_version__gt=after_state_version,
        ).order_by("state_version")[: max_events + 1]
    )
    if not rows:
        return StateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_window_missing",
        )
    if len(rows) > max_events:
        return StateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_window_exceeded",
        )
    if int(rows[0].state_version) > after_state_version + 1:
        return StateFeedReplay(
            events=[],
            latest_state_version=latest_state_version,
            full_resync_required=True,
            reason="replay_gap",
        )

    allowed_types = {str(event_type) for event_type in event_types or [] if str(event_type)}
    replay_level = normalize_requested_event_level(event_level)
    messages: list[dict[str, Any]] = []
    for row in rows:
        message = dict(row.message)
        if allowed_types and str(message.get("type") or "") not in allowed_types:
            continue
        if not message_allowed_for_level({"level": row.level}, replay_level):
            continue
        messages.append(message)

    return StateFeedReplay(
        events=messages,
        latest_state_version=latest_state_version,
        full_resync_required=False,
        reason="replayed",
    )


def latest_state_feed_version(*, run_id: str, organization_id: str) -> int:
    value = (
        StateFeedEvent.objects.filter(
            organization_id=UUID(str(organization_id)),
            run_id=run_id,
        ).aggregate(value=Max("state_version"))["value"]
        or 0
    )
    return int(value)


def _run_visible_to_organization(*, run_id: str, organization_id: UUID) -> bool:
    return Run.objects.filter(id=run_id).filter(_run_scope_filter(organization_id)).exists()


def _run_scope_filter(organization_id: UUID) -> Q:
    return Q(organization_id=organization_id) | Q(
        organization__isnull=True,
        owner__default_organization_id=organization_id,
    )


def _organization_for_run(run: Run) -> Organization:
    organization = run.organization or run.owner.default_organization
    if organization is None:
        raise ValueError("Run does not have an organization for state-feed persistence.")
    return organization


def _payload_for_level(message: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("payload", "run", "node_run", "node_stream"):
        value = message.get(key)
        if isinstance(value, dict):
            return value
    return None


def _replay_limit(value: int | None) -> int:
    configured = value if value is not None else getattr(settings, "RUN_WS_REPLAY_LIMIT", 200)
    try:
        return max(int(configured), 1)
    except (TypeError, ValueError):
        return 200


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()
