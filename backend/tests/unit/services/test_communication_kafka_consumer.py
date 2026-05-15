from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import call_command
from django.test import override_settings

from application.services.communication_kafka import (
    build_communication_kafka_payload,
    communication_kafka_consumer_config,
    communication_kafka_consumer_group,
    consume_communication_kafka_events,
    handle_communication_kafka_event,
)
from application.services.communications import create_message, create_thread
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    CommunicationMessage,
    CommunicationThread,
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


class FakeMessage:
    def __init__(
        self,
        value: bytes | str | None,
        *,
        topic: str = "forgegraph.communication.events.v1",
        partition: int = 0,
        offset: int = 1,
        error: Any | None = None,
    ) -> None:
        self._value = value
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._error = error

    def error(self) -> Any | None:
        return self._error

    def value(self) -> bytes | str | None:
        return self._value

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset


class FakeConsumer:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages
        self.committed = 0

    def subscribe(self, topics: list[str]) -> None:
        _ = topics

    def poll(self, timeout: float | None = None) -> FakeMessage | None:
        _ = timeout
        if not self.messages:
            return None
        return self.messages.pop(0)

    def commit(self, message: FakeMessage | None = None, *, asynchronous: bool = False) -> None:
        _ = message, asynchronous
        self.committed += 1

    def close(self) -> None:
        return


def test_consume_command_exits_when_kafka_disabled() -> None:
    output = StringIO()

    with override_settings(COMMUNICATION_KAFKA_ENABLED=False):
        call_command("consume_communication_kafka", "--once", stdout=output)

    assert "COMMUNICATION_KAFKA_ENABLED is false; exiting." in output.getvalue()


@override_settings(
    COMMUNICATION_KAFKA_CONSUMER_GROUP="",
    KAFKA_COMMUNICATION_CONSUMER_GROUP="alias-communication-consumers",
    COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS="",
    KAFKA_BROKERS="redpanda:9092",
)
def test_consumer_group_config_accepts_alias() -> None:
    assert communication_kafka_consumer_group() == "alias-communication-consumers"
    config = communication_kafka_consumer_config()
    assert config["bootstrap.servers"] == "redpanda:9092"
    assert config["group.id"] == "alias-communication-consumers"
    assert config["enable.auto.commit"] is False


def test_valid_communication_event_is_handled_once() -> None:
    _operator, _company, _message, payload = _message_payload()

    first = handle_communication_kafka_event(payload, consumer_group="consumer-a")
    second = handle_communication_kafka_event(payload, consumer_group="consumer-a")

    assert first.handled is True
    assert first.receipt is not None
    assert first.receipt.status == "handled"
    assert first.receipt.event_id == payload["event_id"]
    assert str(first.receipt.outbox_event_id) == payload["event_id"]
    assert second.duplicate is True
    assert CommunicationEventReceipt.objects.filter(consumer_group="consumer-a").count() == 1


def test_unknown_event_type_is_ignored_safely() -> None:
    _operator, _company, _message, payload = _message_payload()
    payload["event_type"] = "communication.unknown"

    result = handle_communication_kafka_event(payload, consumer_group="consumer-a")

    assert result.ignored is True
    assert result.receipt is not None
    assert result.receipt.status == "ignored"
    assert result.receipt.error_message == "unsupported_event_type"


def test_malformed_event_does_not_crash_consume_loop() -> None:
    consumer = FakeConsumer([FakeMessage(b"{not-json", offset=14)])

    result = consume_communication_kafka_events(
        consumer=consumer,
        consumer_group="consumer-a",
        limit=1,
        poll_timeout_seconds=0.1,
    )

    assert result.failed == 1
    assert consumer.committed == 1
    receipt = CommunicationEventReceipt.objects.get(consumer_group="consumer-a")
    assert receipt.status == "failed"
    assert receipt.offset == 14
    assert "not-json" not in receipt.error_message


def test_consumer_receipt_drops_body_and_private_fields() -> None:
    _operator, _company, _message, payload = _message_payload()
    payload.update(
        {
            "body": "must not persist",
            "private_config": {"token": "hidden"},
            "raw_prompt": "hidden",
            "evidence_bundle": ["hidden"],
            "debug_trace": "hidden",
        }
    )

    result = handle_communication_kafka_event(payload, consumer_group="consumer-a")

    assert result.handled is True
    assert result.receipt is not None
    receipt_text = str(result.receipt.payload_json)
    assert "must not persist" not in receipt_text
    assert "hidden" not in receipt_text
    assert "private_config" not in receipt_text
    assert "raw_prompt" not in receipt_text
    assert "evidence_bundle" not in receipt_text
    assert "debug_trace" not in receipt_text


def test_consumer_does_not_mutate_communication_state() -> None:
    _operator, _company, message, payload = _message_payload()
    thread = message.thread
    before_message_count = CommunicationMessage.objects.count()
    before_thread_count = CommunicationThread.objects.count()
    before_body = message.body
    before_thread_status = thread.status

    result = handle_communication_kafka_event(payload, consumer_group="consumer-a")
    message.refresh_from_db()
    thread.refresh_from_db()

    assert result.handled is True
    assert CommunicationMessage.objects.count() == before_message_count
    assert CommunicationThread.objects.count() == before_thread_count
    assert message.body == before_body
    assert thread.status == before_thread_status


def test_valid_event_from_polling_consumer_is_committed_once() -> None:
    _operator, _company, _message, payload = _message_payload()
    consumer = FakeConsumer(
        [
            FakeMessage(
                json.dumps(payload).encode("utf-8"),
                partition=2,
                offset=12,
            )
        ]
    )

    result = consume_communication_kafka_events(
        consumer=consumer,
        consumer_group="consumer-a",
        limit=1,
        poll_timeout_seconds=0.1,
    )

    assert result.handled == 1
    assert consumer.committed == 1
    receipt = CommunicationEventReceipt.objects.get(consumer_group="consumer-a")
    assert receipt.partition == 2
    assert receipt.offset == 12


def _message_payload() -> tuple[User, Graph, CommunicationMessage, dict[str, Any]]:
    operator, company, message = _create_message_with_body()
    event = DomainEvent.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )
    outbox = DomainEventOutbox.objects.get(domain_event=event)
    return operator, company, message, build_communication_kafka_payload(outbox)


def _create_message_with_body() -> tuple[User, Graph, CommunicationMessage]:
    organization = Organization.objects.create(name="ATLAS")
    operator = User.objects.create_user(
        email="operator-consumer@example.com",
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
        idempotency_key="kafka-consumer-message",
        metadata={"safe": "ok"},
    )
    return operator, company, message
