"""Generic durable outbox for backend-authored domain events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol, cast
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from application.services.redaction import redact_payload
from infrastructure.orm.models import DomainEvent, DomainEventOutbox, Graph

DEFAULT_DOMAIN_EVENT_TOPIC = "forgegraph.domain.events.v1"
_MAX_LAST_ERROR_LENGTH = 4000

_DROPPED_OUTBOX_KEYS = {
    "secret",
    "secrets",
    "credential",
    "credentials",
    "provider_credentials",
    "body",
    "message_body",
    "private_config",
    "raw_private_config",
    "raw_prompt",
    "prompt",
    "prompts",
    "chain_of_thought",
    "cot",
    "reasoning_trace",
    "raw_evidence",
    "evidence_bundle",
    "evidence_bundles",
    "debug",
    "debug_trace",
    "debug_traces",
    "trace",
    "traces",
    "pack_manifest",
    "manifest",
    "namespace_claim",
    "namespace_claims",
    "smtp_config",
    "provider_config",
    "token",
    "tokens",
}


class DomainEventOutboxPublisher(Protocol):
    """Publisher interface for tests and future transports."""

    def publish(self, event: DomainEventOutbox) -> None:
        """Publish one durable outbox event."""


class NoopDomainEventOutboxPublisher:
    """Default publisher used before a real transport is configured."""

    def publish(self, event: DomainEventOutbox) -> None:
        _ = event


@dataclass(frozen=True, slots=True)
class OutboxPublishResult:
    event: DomainEventOutbox
    published: bool


@dataclass(frozen=True, slots=True)
class OutboxPublishBatchResult:
    published: int
    failed: int
    skipped: int


def enqueue_domain_event_outbox(
    *,
    domain_event: DomainEvent,
    topic: str = DEFAULT_DOMAIN_EVENT_TOPIC,
    schema_version: str = "domain_event_v1",
    payload_json: dict[str, Any] | None = None,
    visibility: str = "",
    company: Graph | None = None,
    idempotency_key: str = "",
) -> DomainEventOutbox:
    """Create an outbox row for a committed backend domain event in the caller transaction."""

    key = _compact_key(idempotency_key or f"domain-event-outbox:{domain_event.id}")
    safe_payload = sanitize_outbox_payload(payload_json or domain_event.payload)
    try:
        outbox, created = DomainEventOutbox.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "domain_event": domain_event,
                "organization": domain_event.organization,
                "company": company,
                "event_type": domain_event.event_type,
                "schema_version": str(schema_version or "domain_event_v1")[:64],
                "aggregate_type": domain_event.aggregate_type,
                "aggregate_id": domain_event.aggregate_id,
                "visibility": str(visibility or "")[:32],
                "topic": str(topic or DEFAULT_DOMAIN_EVENT_TOPIC)[:255],
                "payload_json": safe_payload,
                "status": "pending",
            },
        )
    except IntegrityError:
        outbox = DomainEventOutbox.objects.get(idempotency_key=key)
        created = False

    if not created and outbox.domain_event_id is None:
        outbox.domain_event = domain_event
        outbox.save(update_fields=["domain_event", "updated_at"])
    _ensure_outbox_payload_envelope(
        outbox=outbox,
        domain_event=domain_event,
        base_payload=outbox.payload_json or safe_payload,
        schema_version=str(schema_version or "domain_event_v1")[:64],
        visibility=str(visibility or "")[:32],
        company=company,
        idempotency_key=key,
    )
    return outbox


def publish_outbox_event(
    outbox_event_id: UUID | str,
    *,
    publisher: DomainEventOutboxPublisher | None = None,
    now: Any = None,
) -> OutboxPublishResult:
    """Publish one due outbox row and persist retry state."""

    publisher = publisher or NoopDomainEventOutboxPublisher()
    timestamp = now or timezone.now()
    with transaction.atomic():
        event = DomainEventOutbox.objects.select_for_update().get(id=outbox_event_id)
        if event.status == "published" or not _is_due(event, now=timestamp):
            return OutboxPublishResult(event=event, published=False)

        event.publish_attempts += 1
        try:
            publisher.publish(event)
        except Exception as exc:  # noqa: BLE001 - persistence must capture publisher failures.
            event.status = "failed"
            event.last_error = _sanitize_last_error(exc)
            event.next_attempt_at = timestamp + _retry_delay(event.publish_attempts)
            event.save(
                update_fields=[
                    "publish_attempts",
                    "status",
                    "last_error",
                    "next_attempt_at",
                    "updated_at",
                ]
            )
            return OutboxPublishResult(event=event, published=False)

        event.status = "published"
        event.last_error = ""
        event.next_attempt_at = None
        event.published_at = timestamp
        event.save(
            update_fields=[
                "publish_attempts",
                "status",
                "last_error",
                "next_attempt_at",
                "published_at",
                "updated_at",
            ]
        )
        return OutboxPublishResult(event=event, published=True)


def publish_due_outbox_events(
    *,
    publisher: DomainEventOutboxPublisher | None = None,
    limit: int = 100,
    now: Any = None,
    topic: str = "",
) -> OutboxPublishBatchResult:
    """Publish currently due events using a retry-safe durable cursor over outbox rows."""

    timestamp = now or timezone.now()
    queryset = DomainEventOutbox.objects.filter(
        status__in=["pending", "failed", "deferred"],
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timestamp))
    if topic:
        queryset = queryset.filter(topic=topic)
    ids = list(
        queryset.order_by("created_at").values_list("id", flat=True)[
            : max(int(limit or 0), 0)
        ]
    )
    published = 0
    failed = 0
    skipped = 0
    for event_id in ids:
        result = publish_outbox_event(event_id, publisher=publisher, now=timestamp)
        if result.published:
            published += 1
        elif result.event.status == "failed":
            failed += 1
        else:
            skipped += 1
    return OutboxPublishBatchResult(published=published, failed=failed, skipped=skipped)


def sanitize_outbox_payload(value: Any) -> dict[str, Any]:
    redacted = redact_payload(value or {})
    if not isinstance(redacted, dict):
        return {}
    cleaned = _drop_sensitive_outbox_metadata(redacted)
    if not isinstance(cleaned, dict):
        return {}
    return cast(dict[str, Any], json.loads(json.dumps(cleaned, cls=DjangoJSONEncoder)))


def _ensure_outbox_payload_envelope(
    *,
    outbox: DomainEventOutbox,
    domain_event: DomainEvent,
    base_payload: dict[str, Any],
    schema_version: str,
    visibility: str,
    company: Graph | None,
    idempotency_key: str,
) -> None:
    payload = _outbox_envelope_payload(
        outbox=outbox,
        domain_event=domain_event,
        base_payload=base_payload,
        schema_version=schema_version,
        visibility=visibility,
        company=company,
        idempotency_key=idempotency_key,
    )
    if payload == outbox.payload_json:
        return
    outbox.payload_json = payload
    outbox.save(update_fields=["payload_json", "updated_at"])


def _outbox_envelope_payload(
    *,
    outbox: DomainEventOutbox,
    domain_event: DomainEvent,
    base_payload: dict[str, Any],
    schema_version: str,
    visibility: str,
    company: Graph | None,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = sanitize_outbox_payload(base_payload)
    company_id = str(company.id) if company else payload.get("company_id")
    created_at = payload.get("created_at") or domain_event.occurred_at.isoformat()
    envelope = {
        "event_id": str(outbox.id),
        "event_type": domain_event.event_type,
        "schema_version": str(schema_version or "domain_event_v1")[:64],
        "organization_id": str(domain_event.organization_id),
        "company_id": company_id,
        "aggregate_type": domain_event.aggregate_type,
        "aggregate_id": str(domain_event.aggregate_id),
        "visibility": visibility,
        "created_at": created_at,
        "idempotency_key": idempotency_key,
    }
    envelope.update(payload)
    envelope["event_id"] = str(outbox.id)
    envelope["event_type"] = domain_event.event_type
    envelope["schema_version"] = str(schema_version or "domain_event_v1")[:64]
    envelope["organization_id"] = str(domain_event.organization_id)
    envelope["company_id"] = company_id
    envelope["aggregate_type"] = domain_event.aggregate_type
    envelope["aggregate_id"] = str(domain_event.aggregate_id)
    envelope["visibility"] = visibility
    envelope["idempotency_key"] = idempotency_key
    return sanitize_outbox_payload(envelope)


def _sanitize_last_error(exc: Exception) -> str:
    message = redact_payload(str(exc))
    if not isinstance(message, str) or not message:
        message = exc.__class__.__name__
    lowered = message.lower()
    if any(term in lowered for term in _DROPPED_OUTBOX_KEYS):
        message = exc.__class__.__name__
    return message[:_MAX_LAST_ERROR_LENGTH]


def _is_due(event: DomainEventOutbox, *, now: Any) -> bool:
    return event.status in {"pending", "failed", "deferred"} and (
        event.next_attempt_at is None or event.next_attempt_at <= now
    )


def _retry_delay(attempts: int) -> timedelta:
    seconds = min(300, 2 ** min(max(attempts, 1), 8))
    return timedelta(seconds=seconds)


def _compact_key(value: str) -> str:
    key = str(value or "").strip()[:255]
    if not key:
        raise ValueError("Outbox events require an idempotency key.")
    return key


def _drop_sensitive_outbox_metadata(value: Any, *, field_name: str = "") -> Any:
    if field_name.strip().lower() in _DROPPED_OUTBOX_KEYS:
        return None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _drop_sensitive_outbox_metadata(item, field_name=str(key))
            if cleaned is not None:
                result[str(key)] = cleaned
        return result
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _drop_sensitive_outbox_metadata(item, field_name=field_name))
            is not None
        ]
    return value
