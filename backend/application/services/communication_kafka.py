"""Optional Kafka transport for committed communication outbox events."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from application.services.domain_event_outbox import (
    DomainEventOutboxPublisher,
    sanitize_outbox_payload,
)
from infrastructure.orm.models import DomainEventOutbox

DEFAULT_COMMUNICATION_KAFKA_TOPIC = "forgegraph.communication.events.v1"


class KafkaConfigurationError(RuntimeError):
    """Raised when Kafka publishing is enabled but not configured."""


class KafkaDeliveryError(RuntimeError):
    """Raised when Kafka delivery fails or times out."""


class KafkaProducerLike(Protocol):
    def produce(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        callback: Any | None = None,
    ) -> None:
        """Produce one Kafka message."""

    def flush(self, timeout: float | None = None) -> int:
        """Flush pending producer messages and return undelivered count."""


class KafkaOutboxPublisher(DomainEventOutboxPublisher):
    """Publish sanitized outbox event metadata to one communication Kafka topic."""

    def __init__(
        self,
        *,
        producer_factory: Any | None = None,
        config: dict[str, Any] | None = None,
        topic: str = "",
        flush_timeout_seconds: float | None = None,
    ) -> None:
        self.topic = str(topic or communication_kafka_topic())
        self.flush_timeout_seconds = (
            float(flush_timeout_seconds)
            if flush_timeout_seconds is not None
            else float(getattr(settings, "COMMUNICATION_KAFKA_FLUSH_TIMEOUT_SECONDS", 5))
        )
        factory = producer_factory or _load_confluent_kafka_producer()
        producer_config = config if config is not None else communication_kafka_config()
        self.producer = cast(KafkaProducerLike, factory(producer_config))

    def publish(self, event: DomainEventOutbox) -> None:
        payload = build_communication_kafka_payload(event)
        encoded = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":")).encode(
            "utf-8"
        )
        delivery_errors: list[str] = []

        def _delivery_callback(error: Any, _message: Any) -> None:
            if error is not None:
                delivery_errors.append(str(error))

        self.producer.produce(
            self.topic,
            key=event.idempotency_key,
            value=encoded,
            callback=_delivery_callback,
        )
        undelivered_count = self.producer.flush(self.flush_timeout_seconds)
        if delivery_errors:
            raise KafkaDeliveryError(delivery_errors[0])
        if undelivered_count:
            raise KafkaDeliveryError(
                f"Kafka producer flush timed out with {undelivered_count} undelivered messages."
            )


def communication_kafka_enabled() -> bool:
    return bool(getattr(settings, "COMMUNICATION_KAFKA_ENABLED", False))


def communication_kafka_topic() -> str:
    return str(
        getattr(settings, "COMMUNICATION_KAFKA_TOPIC", DEFAULT_COMMUNICATION_KAFKA_TOPIC)
        or DEFAULT_COMMUNICATION_KAFKA_TOPIC
    )


def build_configured_communication_kafka_publisher() -> KafkaOutboxPublisher:
    if not communication_kafka_enabled():
        raise KafkaConfigurationError("COMMUNICATION_KAFKA_ENABLED is false.")
    return KafkaOutboxPublisher()


def communication_kafka_config() -> dict[str, Any]:
    bootstrap_servers = str(
        getattr(settings, "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS", "") or ""
    ).strip()
    if not bootstrap_servers:
        raise KafkaConfigurationError(
            "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS is required when Kafka is enabled."
        )
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": str(
            getattr(settings, "COMMUNICATION_KAFKA_CLIENT_ID", "")
            or "forgegraph-communication-outbox"
        ),
        "enable.idempotence": True,
    }
    security_protocol = str(
        getattr(settings, "COMMUNICATION_KAFKA_SECURITY_PROTOCOL", "") or ""
    ).strip()
    if security_protocol:
        config["security.protocol"] = security_protocol
    sasl_mechanism = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_MECHANISM", "") or "").strip()
    if sasl_mechanism:
        config["sasl.mechanism"] = sasl_mechanism
    sasl_username = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_USERNAME", "") or "").strip()
    if sasl_username:
        config["sasl.username"] = sasl_username
    sasl_password = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_PASSWORD", "") or "").strip()
    if sasl_password:
        config["sasl.password"] = sasl_password
    return config


def build_communication_kafka_payload(event: DomainEventOutbox) -> dict[str, Any]:
    """Build metadata-only event payload; consumers must fetch details through backend APIs."""

    payload = sanitize_outbox_payload(event.payload_json)
    envelope = {
        "event_id": str(event.id),
        "domain_event_id": str(event.domain_event_id) if event.domain_event_id else None,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "organization_id": str(event.organization_id),
        "company_id": str(event.company_id) if event.company_id else None,
        "visibility": event.visibility,
        "topic": event.topic,
        "created_at": event.created_at.isoformat(),
        "idempotency_key": event.idempotency_key,
    }
    envelope.update(payload)
    envelope["event_id"] = str(event.id)
    envelope["domain_event_id"] = str(event.domain_event_id) if event.domain_event_id else None
    return sanitize_outbox_payload(envelope)


def _load_confluent_kafka_producer() -> Any:
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise KafkaConfigurationError(
            "confluent-kafka is required when COMMUNICATION_KAFKA_ENABLED=true."
        ) from exc
    return Producer
