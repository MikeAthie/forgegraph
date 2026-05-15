from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.test import override_settings

from application.services.communication_kafka import (
    KafkaOutboxPublisher,
    build_communication_kafka_payload,
    communication_kafka_config,
    communication_kafka_key,
    communication_kafka_topic,
)
from application.services.communications import create_message, create_thread
from application.services.domain_event_outbox import publish_outbox_event
from application.services.domain_events import record_domain_event
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
    assert payload["aggregate_type"] == "communication_message"
    assert payload["aggregate_id"] == str(message.id)
    assert payload["organization_id"] == str(message.organization_id)
    assert payload["company_id"] == str(message.company_id)
    assert payload["thread_id"] == str(message.thread_id)
    assert payload["message_id"] == str(message.id)
    assert payload["visibility"] == "customer"
    assert payload["topic"] == "forgegraph.communication.events.v1"
    assert payload["idempotency_key"] == outbox.idempotency_key
    assert outbox.payload_json["event_id"] == str(outbox.id)
    assert outbox.payload_json["aggregate_type"] == "communication_message"
    assert outbox.payload_json["aggregate_id"] == str(message.id)
    assert outbox.payload_json["idempotency_key"] == outbox.idempotency_key
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
    _operator, company, message = _create_message_with_body()
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
    assert created[0].messages[0]["key"] == str(company.id)
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


@override_settings(
    COMMUNICATION_KAFKA_TOPIC="",
    KAFKA_COMMUNICATION_TOPIC="forgegraph.alias.communication.v1",
    COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS="",
    KAFKA_BROKERS="redpanda:9092",
    COMMUNICATION_KAFKA_CLIENT_ID="",
    KAFKA_CLIENT_ID="alias-client",
)
def test_kafka_config_accepts_standard_aliases() -> None:
    assert communication_kafka_topic() == "forgegraph.alias.communication.v1"
    config = communication_kafka_config()
    assert config["bootstrap.servers"] == "redpanda:9092"
    assert config["client.id"] == "alias-client"


def test_communication_kafka_key_falls_back_to_thread_id(user) -> None:
    organization = user.default_organization
    assert organization is not None
    thread_id = str(uuid4())
    event = record_domain_event(
        organization=organization,
        aggregate_type="communication_thread",
        aggregate_id=uuid4(),
        event_type="communication.thread.created",
        idempotency_key="kafka-key-thread",
        payload={"thread_id": thread_id},
        outbox_topic="forgegraph.communication.events.v1",
        outbox_schema_version="communication_event_v1",
        outbox_payload={
            "event_type": "communication.thread.created",
            "thread_id": thread_id,
        },
    ).event
    outbox = DomainEventOutbox.objects.get(domain_event=event)

    assert communication_kafka_key(outbox) == thread_id


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
