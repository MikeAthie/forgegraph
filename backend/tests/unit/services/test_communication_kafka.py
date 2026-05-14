from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import call_command
from django.test import override_settings

from application.services.communication_kafka import (
    KafkaOutboxPublisher,
    build_communication_kafka_payload,
)
from application.services.communications import create_message, create_thread
from application.services.domain_event_outbox import publish_outbox_event
from infrastructure.orm.models import (
    CommunicationMessage,
    CompanyAccessPolicy,
    CompanyAssignment,
    DomainEvent,
    DomainEventOutbox,
    Graph,
    Organization,
    OrganizationMembership,
    User,
)

pytestmark = pytest.mark.django_db


class FakeProducer:
    def __init__(self, config: dict[str, Any], *, fail: bool = False) -> None:
        self.config = config
        self.fail = fail
        self.messages: list[dict[str, Any]] = []

    def produce(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        callback: Any | None = None,
    ) -> None:
        self.messages.append({"topic": topic, "key": key, "value": value})
        if callback is not None:
            callback(RuntimeError("broker unavailable") if self.fail else None, None)

    def flush(self, timeout: float | None = None) -> int:
        _ = timeout
        return 0


def test_publish_command_exits_when_kafka_disabled() -> None:
    output = StringIO()

    with override_settings(COMMUNICATION_KAFKA_ENABLED=False):
        call_command("publish_communication_outbox", "--once", stdout=output)

    assert "COMMUNICATION_KAFKA_ENABLED is false; exiting." in output.getvalue()


@override_settings(
    COMMUNICATION_KAFKA_ENABLED=True,
    COMMUNICATION_KAFKA_TOPIC="forgegraph.communication.events.v1",
)
def test_communication_kafka_payload_is_metadata_only() -> None:
    _operator, _company, message = _create_message_with_body()
    event = DomainEvent.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )
    outbox = DomainEventOutbox.objects.get(domain_event=event)

    payload = build_communication_kafka_payload(outbox)
    payload_text = str(payload)

    assert payload["event_id"] == str(outbox.id)
    assert payload["domain_event_id"] == str(event.id)
    assert payload["event_type"] == "communication.message.created"
    assert payload["schema_version"] == "communication_event_v1"
    assert payload["thread_id"] == str(message.thread_id)
    assert payload["message_id"] == str(message.id)
    assert payload["visibility"] == "customer"
    assert payload["topic"] == "forgegraph.communication.events.v1"
    assert "Can you explain" not in payload_text
    assert "hidden" not in payload_text
    assert "private_config" not in payload_text
    assert "raw_prompt" not in payload_text
    assert "evidence_bundle" not in payload_text
    assert "debug_trace" not in payload_text


@override_settings(
    COMMUNICATION_KAFKA_ENABLED=True,
    COMMUNICATION_KAFKA_TOPIC="forgegraph.communication.events.v1",
)
def test_kafka_publisher_marks_outbox_published_with_fake_producer() -> None:
    _operator, _company, message = _create_message_with_body()
    event = DomainEvent.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )
    outbox = DomainEventOutbox.objects.get(domain_event=event)
    created: list[FakeProducer] = []

    def factory(config: dict[str, Any]) -> FakeProducer:
        producer = FakeProducer(config)
        created.append(producer)
        return producer

    publisher = KafkaOutboxPublisher(
        producer_factory=factory,
        config={"bootstrap.servers": "localhost:9092"},
        topic="forgegraph.communication.events.v1",
        flush_timeout_seconds=0.1,
    )

    result = publish_outbox_event(outbox.id, publisher=publisher)
    outbox.refresh_from_db()

    assert result.published is True
    assert outbox.status == "published"
    assert outbox.publish_attempts == 1
    assert created[0].messages[0]["topic"] == "forgegraph.communication.events.v1"
    kafka_payload = json.loads(created[0].messages[0]["value"].decode("utf-8"))
    assert kafka_payload["message_id"] == str(message.id)
    assert "Can you explain" not in str(kafka_payload)


@override_settings(
    COMMUNICATION_KAFKA_ENABLED=True,
    COMMUNICATION_KAFKA_TOPIC="forgegraph.communication.events.v1",
)
def test_kafka_publish_failure_keeps_committed_message_and_marks_outbox_failed() -> None:
    _operator, _company, message = _create_message_with_body()
    event = DomainEvent.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )
    outbox = DomainEventOutbox.objects.get(domain_event=event)

    publisher = KafkaOutboxPublisher(
        producer_factory=lambda config: FakeProducer(config, fail=True),
        config={"bootstrap.servers": "localhost:9092"},
        topic="forgegraph.communication.events.v1",
        flush_timeout_seconds=0.1,
    )

    result = publish_outbox_event(outbox.id, publisher=publisher)
    outbox.refresh_from_db()

    assert result.published is False
    assert CommunicationMessage.objects.filter(id=message.id).exists()
    assert DomainEvent.objects.filter(id=event.id).exists()
    assert outbox.status == "failed"
    assert outbox.publish_attempts == 1
    assert outbox.next_attempt_at is not None
    assert "broker unavailable" in outbox.last_error


def _create_message_with_body() -> tuple[User, Graph, CommunicationMessage]:
    organization = Organization.objects.create(name="ATLAS")
    operator = User.objects.create_user(
        email="operator@example.com",
        password="testpassword123",
    )
    operator.default_organization = organization
    operator.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=organization,
        user=operator,
        role="owner",
        is_default=True,
    )
    company = cast(
        Graph,
        Graph.objects.create(
            owner=operator,
            organization=organization,
            name="Legacy Eyewear",
            description="Test company",
        ),
    )
    CompanyAccessPolicy.objects.create(
        organization=organization,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    CompanyAssignment.objects.create(
        organization=organization,
        company=company,
        user=operator,
        role="member",
        status="active",
    )
    thread = create_thread(
        company=company,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    message = create_message(
        thread=thread,
        sender_user=operator,
        message_kind="request",
        body="Can you explain why WhatsApp is recommended if the connector is missing?",
        visibility="customer",
        idempotency_key="kafka-message",
        metadata={
            "private_config": {"token": "hidden"},
            "raw_prompt": "hidden",
            "evidence_bundle": ["hidden"],
            "debug_trace": "hidden",
        },
    )
    return operator, company, message
