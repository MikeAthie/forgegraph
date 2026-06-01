from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from application.services.domain_event_outbox import (
    publish_due_outbox_events,
    publish_outbox_event,
)
from application.services.domain_events import record_domain_event
from infrastructure.orm.models import DomainEvent, DomainEventOutbox

pytestmark = pytest.mark.django_db


class RecordingPublisher:
    def __init__(
        self,
        *,
        fail: bool = False,
        fail_message: str = "broker unavailable",
    ) -> None:
        self.fail = fail
        self.fail_message = fail_message
        self.events: list[DomainEventOutbox] = []

    def publish(self, event: DomainEventOutbox) -> None:
        self.events.append(event)
        if self.fail:
            raise RuntimeError(self.fail_message)


def test_record_domain_event_enqueues_generic_outbox_idempotently(user) -> None:
    organization = user.default_organization
    assert organization is not None
    aggregate_id = uuid4()

    first = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=aggregate_id,
        event_type="test.created",
        idempotency_key="outbox:test:created",
        payload={"value": 1},
        outbox_topic="forgegraph.test.events.v1",
        outbox_schema_version="test_event_v1",
        outbox_payload={
            "event_type": "test.created",
            "aggregate_id": str(aggregate_id),
            "safe": "ok",
            "secret": "hidden",
            "private_config": {"token": "hidden"},
            "raw_prompt": "hidden",
            "evidence_bundle": ["hidden"],
            "debug_trace": "hidden",
        },
        outbox_visibility="internal",
    )
    duplicate = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=aggregate_id,
        event_type="test.created",
        idempotency_key="outbox:test:created",
        payload={"value": 1},
        outbox_topic="forgegraph.test.events.v1",
        outbox_schema_version="test_event_v1",
        outbox_payload={"event_type": "test.created", "safe": "ok"},
        outbox_visibility="internal",
    )

    assert first.created is True
    assert duplicate.created is False
    assert DomainEventOutbox.objects.count() == 1
    outbox = DomainEventOutbox.objects.get(domain_event=first.event)
    assert outbox.topic == "forgegraph.test.events.v1"
    assert outbox.schema_version == "test_event_v1"
    assert outbox.status == "pending"
    assert outbox.visibility == "internal"
    assert outbox.payload_json["event_id"] == str(outbox.id)
    assert outbox.payload_json["event_type"] == "test.created"
    assert outbox.payload_json["schema_version"] == "test_event_v1"
    assert outbox.payload_json["organization_id"] == str(organization.id)
    assert outbox.payload_json["aggregate_type"] == "test"
    assert outbox.payload_json["aggregate_id"] == str(aggregate_id)
    assert outbox.payload_json["idempotency_key"] == ("domain-event-outbox:" + str(first.event.id))
    assert outbox.payload_json["safe"] == "ok"
    payload_text = str(outbox.payload_json)
    assert "hidden" not in payload_text
    assert "private_config" not in payload_text
    assert "raw_prompt" not in payload_text
    assert "evidence_bundle" not in payload_text
    assert "debug_trace" not in payload_text
    domain_payload_text = str(first.event.payload)
    assert "hidden" not in domain_payload_text
    assert "private_config" not in domain_payload_text
    assert "raw_prompt" not in domain_payload_text
    assert "evidence_bundle" not in domain_payload_text
    assert "debug_trace" not in domain_payload_text


def test_domain_event_payload_is_sanitized_before_durable_persistence(user) -> None:
    organization = user.default_organization
    assert organization is not None

    event = record_domain_event(
        organization=organization,
        aggregate_type="approval",
        aggregate_id=uuid4(),
        event_type="decision.approval_created",
        idempotency_key="domain-event:sanitized-payload",
        payload={
            "approval_task_id": str(uuid4()),
            "safe_reference": "approval:123",
            "payload": {
                "prompt_message": "Do not persist this prompt.",
                "required_fields": ["approved"],
            },
            "result": {
                "evidence": "Do not persist raw evidence.",
                "approved": True,
            },
            "tool_output": {"secret": "hidden"},
            "metadata": {"api_key": "sk-hidden", "safe": "ok"},
        },
    ).event

    payload_text = str(event.payload)
    assert event.payload["safe_reference"] == "approval:123"
    assert event.payload["metadata"]["api_key"] == "***REDACTED***"
    assert event.payload["metadata"]["safe"] == "ok"
    assert "Do not persist" not in payload_text
    assert "prompt_message" not in payload_text
    assert "evidence" not in payload_text
    assert "tool_output" not in payload_text
    assert "hidden" not in payload_text


def test_outbox_rolls_back_with_domain_event_transaction(user) -> None:
    organization = user.default_organization
    assert organization is not None

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            record_domain_event(
                organization=organization,
                aggregate_type="test",
                aggregate_id=uuid4(),
                event_type="test.created",
                idempotency_key="outbox:rollback",
                payload={"value": 1},
                outbox_topic="forgegraph.test.events.v1",
                outbox_payload={"event_type": "test.created"},
            )
            raise RuntimeError("rollback")

    assert DomainEvent.objects.filter(idempotency_key="outbox:rollback").count() == 0
    assert DomainEventOutbox.objects.count() == 0


def test_publish_outbox_event_marks_published(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="test.created",
        idempotency_key="outbox:publish",
        payload={"value": 1},
        outbox_topic="forgegraph.test.events.v1",
        outbox_payload={"event_type": "test.created"},
    ).event
    outbox = DomainEventOutbox.objects.get(domain_event=event)
    publisher = RecordingPublisher()

    result = publish_outbox_event(outbox.id, publisher=publisher)
    outbox.refresh_from_db()

    assert result.published is True
    assert outbox.status == "published"
    assert outbox.publish_attempts == 1
    assert outbox.published_at is not None
    assert publisher.events[0].id == outbox.id


def test_publish_due_outbox_events_persists_failures_and_retries_due_rows(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="test.created",
        idempotency_key="outbox:retry",
        payload={"value": 1},
        outbox_topic="forgegraph.test.events.v1",
        outbox_payload={"event_type": "test.created"},
    ).event
    outbox = DomainEventOutbox.objects.get(domain_event=event)

    failed = publish_due_outbox_events(publisher=RecordingPublisher(fail=True), limit=10)
    outbox.refresh_from_db()
    assert failed.failed == 1
    assert outbox.status == "failed"
    assert outbox.publish_attempts == 1
    assert outbox.next_attempt_at is not None
    assert "broker unavailable" in outbox.last_error

    skipped = publish_due_outbox_events(publisher=RecordingPublisher(), limit=10)
    assert skipped.skipped == 0
    assert skipped.published == 0

    outbox.next_attempt_at = timezone.now()
    outbox.save(update_fields=["next_attempt_at", "updated_at"])

    retried = publish_due_outbox_events(publisher=RecordingPublisher(), limit=10)
    outbox.refresh_from_db()
    assert retried.published == 1
    assert outbox.status == "published"
    assert outbox.publish_attempts == 2


def test_publish_failure_last_error_is_bounded_and_sanitized(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="test.created",
        idempotency_key="outbox:sensitive-error",
        payload={"value": 1},
        outbox_topic="forgegraph.test.events.v1",
        outbox_payload={"event_type": "test.created"},
    ).event
    outbox = DomainEventOutbox.objects.get(domain_event=event)

    publish_outbox_event(
        outbox.id,
        publisher=RecordingPublisher(
            fail=True,
            fail_message="private_config raw_prompt evidence_bundle debug_trace token=hidden",
        ),
    )
    outbox.refresh_from_db()

    assert outbox.status == "failed"
    assert len(outbox.last_error) <= 4000
    assert outbox.last_error == "RuntimeError"
