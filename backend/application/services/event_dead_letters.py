from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from application.services.redaction import redact_payload
from infrastructure.orm.models import EventDeadLetterRecord, Organization, Run, User


def record_event_dead_letter(
    *,
    source: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    organization: Organization | None = None,
    run: Run | None = None,
    event_id: str = "",
    idempotency_key: str = "",
    event_type: str = "",
    error_class: str = "",
) -> EventDeadLetterRecord:
    """Record an unapplied backend event so operators can reconcile it."""

    safe_payload = _json_safe_payload(redact_payload(payload or {}))
    if not isinstance(safe_payload, dict):
        safe_payload = {"value": safe_payload}

    source_value = str(source or "unknown")[:64]
    event_id_value = str(event_id or "").strip()[:128]
    idempotency_key_value = str(idempotency_key or "").strip()[:255]
    event_type_value = str(event_type or "").strip()[:96]
    reason_value = str(reason or "event ingestion failed").strip() or "event ingestion failed"
    error_class_value = str(error_class or "").strip()[:128]

    with transaction.atomic():
        existing = _find_existing_dead_letter(
            source=source_value,
            organization=organization,
            run=run,
            event_id=event_id_value,
            idempotency_key=idempotency_key_value,
            event_type=event_type_value,
            reason=reason_value,
        )
        if existing is not None:
            existing.retry_count += 1
            existing.payload = safe_payload
            existing.reason = reason_value
            existing.error_class = error_class_value
            existing.event_type = event_type_value or existing.event_type
            existing.idempotency_key = idempotency_key_value or existing.idempotency_key
            existing.save(
                update_fields=[
                    "retry_count",
                    "payload",
                    "reason",
                    "error_class",
                    "event_type",
                    "idempotency_key",
                    "last_seen_at",
                ]
            )
            return existing

        return EventDeadLetterRecord.objects.create(
            organization=organization,
            run=run,
            event_id=event_id_value,
            idempotency_key=idempotency_key_value,
            event_type=event_type_value,
            source=source_value,
            reason=reason_value,
            error_class=error_class_value,
            payload=safe_payload,
        )


def acknowledge_event_dead_letter(
    *,
    dead_letter_id: UUID,
    actor: User,
    reason: str,
) -> EventDeadLetterRecord | None:
    reason_value = str(reason or "").strip()
    if not reason_value:
        raise ValueError("A reason is required.")
    with transaction.atomic():
        dead_letter = (
            EventDeadLetterRecord.objects.select_for_update().filter(id=dead_letter_id).first()
        )
        if dead_letter is None:
            return None
        now = timezone.now()
        dead_letter.status = "acknowledged"
        dead_letter.acknowledged_at = now
        dead_letter.acknowledged_by = actor
        dead_letter.acknowledgement_reason = reason_value[:1000]
        dead_letter.save(
            update_fields=[
                "status",
                "acknowledged_at",
                "acknowledged_by",
                "acknowledgement_reason",
                "last_seen_at",
            ]
        )
        return dead_letter


def request_event_dead_letter_replay(
    *,
    dead_letter_id: UUID,
    actor: User,
    reason: str,
) -> EventDeadLetterRecord | None:
    reason_value = str(reason or "").strip()
    if not reason_value:
        raise ValueError("A reason is required.")
    with transaction.atomic():
        dead_letter = (
            EventDeadLetterRecord.objects.select_for_update().filter(id=dead_letter_id).first()
        )
        if dead_letter is None:
            return None
        now = timezone.now()
        dead_letter.status = "replay_requested"
        dead_letter.replay_requested_at = now
        dead_letter.replay_requested_by = actor
        dead_letter.last_replay_action = reason_value[:1000]
        dead_letter.save(
            update_fields=[
                "status",
                "replay_requested_at",
                "replay_requested_by",
                "last_replay_action",
                "last_seen_at",
            ]
        )
        return dead_letter


def _find_existing_dead_letter(
    *,
    source: str,
    organization: Organization | None,
    run: Run | None,
    event_id: str,
    idempotency_key: str,
    event_type: str,
    reason: str,
) -> EventDeadLetterRecord | None:
    query = EventDeadLetterRecord.objects.select_for_update().filter(
        source=source,
        status__in={"active", "replay_requested"},
    )
    if organization is not None:
        query = query.filter(organization=organization)
    else:
        query = query.filter(organization__isnull=True)
    if run is not None:
        query = query.filter(run=run)
    else:
        query = query.filter(run__isnull=True)
    if event_id:
        return query.filter(event_id=event_id).order_by("-last_seen_at").first()
    if idempotency_key:
        return query.filter(idempotency_key=idempotency_key).order_by("-last_seen_at").first()
    return query.filter(event_type=event_type, reason=reason).order_by("-last_seen_at").first()


def _json_safe_payload(payload: Any) -> Any:
    try:
        return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    except TypeError:
        return {"value": str(payload)}
