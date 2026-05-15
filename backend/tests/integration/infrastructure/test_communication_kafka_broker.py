from __future__ import annotations

import os
from uuid import uuid4

import pytest

from application.services.communication_kafka import (
    KafkaOutboxPublisher,
    build_communication_kafka_payload,
)
from application.services.domain_event_outbox import publish_outbox_event
from application.services.domain_events import record_domain_event
from infrastructure.orm.models import DomainEventOutbox

pytestmark = pytest.mark.django_db


@pytest.mark.skipif(
    os.environ.get("RUN_KAFKA_INTEGRATION", "").lower() != "true"
    or not os.environ.get("KAFKA_BROKERS", "").strip(),
    reason="Kafka broker integration requires RUN_KAFKA_INTEGRATION=true and KAFKA_BROKERS.",
)
def test_optional_kafka_broker_publish_sanitized_communication_event(user) -> None:
    pytest.importorskip("confluent_kafka")
    organization = user.default_organization
    assert organization is not None
    brokers = os.environ["KAFKA_BROKERS"].strip()
    topic_prefix = os.environ.get("KAFKA_TEST_TOPIC_PREFIX", "forgegraph-test").strip()
    topic = f"{topic_prefix}.communication.events.v1"
    message_id = uuid4()

    event = record_domain_event(
        organization=organization,
        aggregate_type="communication_message",
        aggregate_id=message_id,
        event_type="communication.message.created",
        idempotency_key=f"kafka-integration:{message_id}",
        payload={"message_id": str(message_id)},
        outbox_topic=topic,
        outbox_schema_version="communication_event_v1",
        outbox_payload={
            "event_type": "communication.message.created",
            "message_id": str(message_id),
            "body": "must not be published",
            "private_config": {"token": "hidden"},
            "raw_prompt": "hidden",
            "evidence_bundle": ["hidden"],
            "debug_trace": "hidden",
        },
        outbox_visibility="customer",
    ).event
    outbox = DomainEventOutbox.objects.get(domain_event=event)
    payload = build_communication_kafka_payload(outbox)
    payload_text = str(payload)

    assert payload["event_type"] == "communication.message.created"
    assert payload["schema_version"] == "communication_event_v1"
    assert payload["message_id"] == str(message_id)
    assert "must not be published" not in payload_text
    assert "hidden" not in payload_text
    assert "private_config" not in payload_text
    assert "raw_prompt" not in payload_text
    assert "evidence_bundle" not in payload_text
    assert "debug_trace" not in payload_text

    publisher = KafkaOutboxPublisher(
        config={"bootstrap.servers": brokers},
        topic=topic,
        flush_timeout_seconds=5,
    )
    result = publish_outbox_event(outbox.id, publisher=publisher)
    outbox.refresh_from_db()

    assert result.published is True
    assert outbox.status == "published"
