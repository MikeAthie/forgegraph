"""Optional Kafka transport for committed communication outbox events."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from application.services.domain_event_outbox import (
    DomainEventOutboxPublisher,
    sanitize_outbox_payload,
)
from application.services.event_dead_letters import record_event_dead_letter
from application.services.metrics import record_service_metric_sample
from application.services.redaction import redact_payload
from application.services.structured_logging import log_event
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    DomainEventOutbox,
    Graph,
    Organization,
)

logger = logging.getLogger(__name__)

DEFAULT_COMMUNICATION_KAFKA_TOPIC = "forgegraph.communication.events.v1"
DEFAULT_COMMUNICATION_KAFKA_CONSUMER_GROUP = "forgegraph-communication-events"
DEFAULT_COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES = 64 * 1024
COMMUNICATION_KAFKA_SCHEMA_VERSION = "communication_event_v1"
COMMUNICATION_KAFKA_EVENT_TYPES = {
    "communication.thread.created",
    "communication.message.created",
    "communication.message.redacted",
    "communication.attachment.created",
}
_REQUIRED_COMMUNICATION_EVENT_FIELDS = {
    "event_id",
    "event_type",
    "schema_version",
    "organization_id",
    "aggregate_type",
    "aggregate_id",
    "created_at",
    "idempotency_key",
}
_EVENT_SPECIFIC_REQUIRED_FIELDS = {
    "communication.thread.created": {"thread_id"},
    "communication.message.created": {"thread_id", "message_id"},
    "communication.message.redacted": {"thread_id", "message_id"},
    "communication.attachment.created": {"thread_id", "message_id", "attachment_id"},
}
_MAX_CONSUMER_ERROR_LENGTH = 1000
_AUTHORITATIVE_ENVELOPE_FIELDS = (
    "event_id",
    "domain_event_id",
    "event_type",
    "schema_version",
    "aggregate_type",
    "aggregate_id",
    "organization_id",
    "company_id",
    "visibility",
    "topic",
    "created_at",
    "idempotency_key",
)
_KAFKA_HEADER_FIELDS = (
    "event_id",
    "idempotency_key",
    "event_type",
    "schema_version",
    "organization_id",
)


class KafkaConfigurationError(RuntimeError):
    """Raised when Kafka publishing is enabled but not configured."""


class KafkaDeliveryError(RuntimeError):
    """Raised when Kafka delivery fails or times out."""


class KafkaMessageLike(Protocol):
    def error(self) -> Any | None:
        """Return transport error for this polled item."""

    def value(self) -> bytes | str | None:
        """Return raw Kafka message value."""

    def topic(self) -> str:
        """Return Kafka topic."""

    def partition(self) -> int:
        """Return partition number."""

    def offset(self) -> int:
        """Return message offset."""


class KafkaProducerLike(Protocol):
    def produce(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
        callback: Any | None = None,
    ) -> None:
        """Produce one Kafka message."""

    def flush(self, timeout: float | None = None) -> int:
        """Flush pending producer messages and return undelivered count."""


class KafkaConsumerLike(Protocol):
    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to Kafka topics."""

    def poll(self, timeout: float | None = None) -> KafkaMessageLike | None:
        """Poll one Kafka message."""

    def commit(self, message: KafkaMessageLike | None = None, *, asynchronous: bool = False) -> Any:
        """Commit a consumed message offset."""

    def close(self) -> None:
        """Close the consumer."""


@dataclass(frozen=True, slots=True)
class CommunicationKafkaEnvelope:
    """Metadata-only wire envelope for communication Kafka events."""

    event_id: str
    domain_event_id: str | None
    event_type: str
    schema_version: str
    aggregate_type: str
    aggregate_id: str
    organization_id: str
    company_id: str | None
    visibility: str
    topic: str
    created_at: str
    idempotency_key: str
    payload: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        envelope = {
            "event_id": self.event_id,
            "domain_event_id": self.domain_event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "organization_id": self.organization_id,
            "company_id": self.company_id,
            "visibility": self.visibility,
            "topic": self.topic,
            "created_at": self.created_at,
            "idempotency_key": self.idempotency_key,
        }
        envelope.update(sanitize_outbox_payload(self.payload))
        for field_name in _AUTHORITATIVE_ENVELOPE_FIELDS:
            envelope[field_name] = getattr(self, field_name)
        return sanitize_outbox_payload(envelope)

    def headers(self) -> list[tuple[str, bytes]]:
        payload = self.as_payload()
        return [
            (field_name, str(payload[field_name]).encode("utf-8"))
            for field_name in _KAFKA_HEADER_FIELDS
            if payload.get(field_name) is not None
        ]


@dataclass(frozen=True, slots=True)
class CommunicationKafkaHandleResult:
    status: str
    receipt: CommunicationEventReceipt | None = None
    handled: bool = False
    duplicate: bool = False
    ignored: bool = False
    failed: bool = False


@dataclass(frozen=True, slots=True)
class CommunicationKafkaConsumeResult:
    handled: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0
    commit_failed: int = 0
    empty_polls: int = 0


@dataclass(frozen=True, slots=True)
class _ConsumeStatusDelta:
    handled: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0


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
        started_at = time.perf_counter()
        envelope = build_communication_kafka_envelope(event)
        payload = envelope.as_payload()
        encoded = _encode_communication_kafka_payload(payload)
        delivery_errors: list[str] = []

        def _delivery_callback(error: Any, _message: Any) -> None:
            if error is not None:
                delivery_errors.append(str(error))

        try:
            self._produce(
                key=communication_kafka_key(event),
                value=encoded,
                headers=envelope.headers(),
                callback=_delivery_callback,
            )
            undelivered_count = self.producer.flush(self.flush_timeout_seconds)
            if delivery_errors:
                raise KafkaDeliveryError(delivery_errors[0])
            if undelivered_count:
                raise KafkaDeliveryError(
                    f"Kafka producer flush timed out with {undelivered_count} undelivered messages."
                )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            _record_communication_kafka_metric(
                "communication_kafka_publish_failure",
                value=1,
                unit="count",
                dimensions={
                    "topic": self.topic,
                    "event_type": event.event_type,
                    "error_class": exc.__class__.__name__,
                },
                organization_id=event.organization_id,
            )
            log_event(
                logger,
                logging.WARNING,
                "communication_kafka_publish_failed",
                topic=self.topic,
                event_id=str(event.id),
                organization_id=str(event.organization_id),
                outbox_event_id=str(event.id),
                duration_ms=duration_ms,
                payload_size_bytes=len(encoded),
                error_class=exc.__class__.__name__,
                error_message=_sanitize_consumer_error(exc),
            )
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _record_communication_kafka_metric(
            "communication_kafka_publish_latency_ms",
            value=duration_ms,
            unit="ms",
            dimensions={"topic": self.topic, "event_type": event.event_type},
            organization_id=event.organization_id,
        )
        log_event(
            logger,
            logging.INFO,
            "communication_kafka_publish_succeeded",
            topic=self.topic,
            event_id=str(event.id),
            organization_id=str(event.organization_id),
            outbox_event_id=str(event.id),
            duration_ms=duration_ms,
            payload_size_bytes=len(encoded),
        )

    def _produce(
        self,
        *,
        key: str,
        value: bytes,
        headers: list[tuple[str, bytes]],
        callback: Any,
    ) -> None:
        try:
            self.producer.produce(
                self.topic,
                key=key,
                value=value,
                headers=headers,
                callback=callback,
            )
        except BufferError:
            _poll_producer_if_supported(
                self.producer,
                float(getattr(settings, "COMMUNICATION_KAFKA_PRODUCE_POLL_TIMEOUT_SECONDS", 1)),
            )
            self.producer.produce(
                self.topic,
                key=key,
                value=value,
                headers=headers,
                callback=callback,
            )


def communication_kafka_enabled() -> bool:
    return bool(getattr(settings, "COMMUNICATION_KAFKA_ENABLED", False))


def communication_kafka_topic() -> str:
    return str(
        _setting_value("COMMUNICATION_KAFKA_TOPIC")
        or _setting_value("KAFKA_COMMUNICATION_TOPIC")
        or DEFAULT_COMMUNICATION_KAFKA_TOPIC
    )


def communication_kafka_consumer_group() -> str:
    return str(
        _setting_value("COMMUNICATION_KAFKA_CONSUMER_GROUP")
        or _setting_value("KAFKA_COMMUNICATION_CONSUMER_GROUP")
        or DEFAULT_COMMUNICATION_KAFKA_CONSUMER_GROUP
    )


def build_configured_communication_kafka_publisher() -> KafkaOutboxPublisher:
    if not communication_kafka_enabled():
        raise KafkaConfigurationError("COMMUNICATION_KAFKA_ENABLED is false.")
    return KafkaOutboxPublisher()


def build_configured_communication_kafka_consumer(
    *,
    consumer_factory: Any | None = None,
) -> KafkaConsumerLike:
    if not communication_kafka_enabled():
        raise KafkaConfigurationError("COMMUNICATION_KAFKA_ENABLED is false.")
    factory = consumer_factory or _load_confluent_kafka_consumer()
    consumer = cast(KafkaConsumerLike, factory(communication_kafka_consumer_config()))
    consumer.subscribe([communication_kafka_topic()])
    return consumer


def communication_kafka_config() -> dict[str, Any]:
    config = _communication_kafka_common_config()
    config.update(
        {
            "enable.idempotence": True,
            "acks": "all",
            "retries": _setting_int("COMMUNICATION_KAFKA_RETRIES", 5),
            "retry.backoff.ms": _setting_int("COMMUNICATION_KAFKA_RETRY_BACKOFF_MS", 250),
            "delivery.timeout.ms": _setting_int("COMMUNICATION_KAFKA_DELIVERY_TIMEOUT_MS", 30000),
            "request.timeout.ms": _setting_int("COMMUNICATION_KAFKA_REQUEST_TIMEOUT_MS", 10000),
            "linger.ms": _setting_int("COMMUNICATION_KAFKA_LINGER_MS", 5),
        }
    )
    compression_type = _setting_value("COMMUNICATION_KAFKA_COMPRESSION_TYPE") or "lz4"
    if compression_type:
        config["compression.type"] = compression_type
    return config


def communication_kafka_consumer_config() -> dict[str, Any]:
    config = _communication_kafka_common_config()
    config.update(
        {
            "group.id": communication_kafka_consumer_group(),
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": _setting_value("COMMUNICATION_KAFKA_AUTO_OFFSET_RESET")
            or "earliest",
            "isolation.level": _setting_value("COMMUNICATION_KAFKA_ISOLATION_LEVEL")
            or "read_committed",
            "session.timeout.ms": _setting_int("COMMUNICATION_KAFKA_SESSION_TIMEOUT_MS", 45000),
            "max.poll.interval.ms": _setting_int(
                "COMMUNICATION_KAFKA_MAX_POLL_INTERVAL_MS", 300000
            ),
        }
    )
    return config


def _communication_kafka_common_config() -> dict[str, Any]:
    bootstrap_servers = str(
        _setting_value("COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS")
        or _setting_value("KAFKA_BROKERS")
        or ""
    ).strip()
    if not bootstrap_servers:
        raise KafkaConfigurationError(
            "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS or KAFKA_BROKERS is required "
            "when Kafka is enabled."
        )
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": str(
            _setting_value("COMMUNICATION_KAFKA_CLIENT_ID")
            or _setting_value("KAFKA_CLIENT_ID")
            or "forgegraph-communication-outbox"
        ),
    }
    statistics_interval_ms = _setting_int("COMMUNICATION_KAFKA_STATISTICS_INTERVAL_MS", 0)
    if statistics_interval_ms > 0:
        config["statistics.interval.ms"] = statistics_interval_ms
        config["stats_cb"] = _kafka_stats_callback
    config["error_cb"] = _kafka_error_callback
    config["throttle_cb"] = _kafka_throttle_callback
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


def communication_kafka_key(event: DomainEventOutbox) -> str:
    payload = sanitize_outbox_payload(event.payload_json)
    company_id = str(event.company_id or payload.get("company_id") or "").strip()
    if company_id:
        return company_id
    thread_id = str(payload.get("thread_id") or "").strip()
    if thread_id:
        return thread_id
    return event.idempotency_key


def consume_communication_kafka_events(
    *,
    consumer: KafkaConsumerLike,
    consumer_group: str = "",
    limit: int = 100,
    poll_timeout_seconds: float = 1.0,
) -> CommunicationKafkaConsumeResult:
    group = _compact_consumer_group(consumer_group or communication_kafka_consumer_group())
    handled = 0
    duplicates = 0
    ignored = 0
    failed = 0
    commit_failed = 0
    empty_polls = 0
    for _ in range(max(int(limit or 0), 0)):
        message = consumer.poll(float(poll_timeout_seconds))
        if message is None:
            empty_polls += 1
            break
        message_error = message.error()
        if message_error is not None:
            delta = _handle_kafka_poll_error(
                error=message_error,
                consumer_group=group,
                topic=_message_topic(message),
                partition=_message_partition(message),
                offset=_message_offset(message),
            )
            ignored += delta.ignored
            failed += delta.failed
            continue
        topic = _message_topic(message)
        partition = _message_partition(message)
        offset = _message_offset(message)
        started_at = time.perf_counter()
        try:
            result = handle_communication_kafka_message(
                message.value(),
                consumer_group=group,
                topic=topic,
                partition=partition,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001 - preserve offset for retry on persistence errors.
            failed += 1
            _record_consumer_handler_exception(
                exc,
                topic=topic,
                partition=partition,
                offset=offset,
                consumer_group=group,
            )
            break
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _record_communication_kafka_metric(
            "communication_kafka_consumer_handle_latency_ms",
            value=duration_ms,
            unit="ms",
            dimensions={"topic": topic, "consumer_group": group, "status": result.status},
            organization_id=result.receipt.organization_id if result.receipt else None,
        )
        delta = _consume_status_delta(result)
        handled += delta.handled
        duplicates += delta.duplicates
        ignored += delta.ignored
        failed += delta.failed
        if not _commit_if_supported(
            consumer,
            message,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
        ):
            commit_failed += 1
    return CommunicationKafkaConsumeResult(
        handled=handled,
        duplicates=duplicates,
        ignored=ignored,
        failed=failed,
        commit_failed=commit_failed,
        empty_polls=empty_polls,
    )


def handle_communication_kafka_message(
    raw_value: bytes | str | None,
    *,
    consumer_group: str = "",
    topic: str = "",
    partition: int | None = None,
    offset: int | None = None,
) -> CommunicationKafkaHandleResult:
    raw_size = _raw_kafka_value_size(raw_value)
    max_payload_bytes = communication_kafka_max_payload_bytes()
    if raw_size > max_payload_bytes:
        receipt = _record_failed_transport_receipt(
            reason="payload_too_large",
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
        _record_communication_event_dead_letter(
            payload=receipt.payload_json,
            reason="payload_too_large",
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(status="failed", receipt=receipt, failed=True)

    try:
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")
        decoded = json.loads(raw_value or "{}")
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _ = exc
        receipt = _record_failed_transport_receipt(
            reason="invalid_json",
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
        _record_communication_event_dead_letter(
            payload=receipt.payload_json,
            reason="invalid_json",
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(
            status="failed",
            receipt=receipt,
            failed=True,
        )
    return handle_communication_kafka_event(
        decoded,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
    )


def handle_communication_kafka_event(
    payload: dict[str, Any] | Any,
    *,
    consumer_group: str = "",
    topic: str = "",
    partition: int | None = None,
    offset: int | None = None,
) -> CommunicationKafkaHandleResult:
    safe_payload = sanitize_outbox_payload(payload if isinstance(payload, dict) else {})
    group = _compact_consumer_group(consumer_group or communication_kafka_consumer_group())
    event_id = _payload_text(safe_payload, "event_id")
    idempotency_key = _payload_text(safe_payload, "idempotency_key")
    existing = _find_existing_receipt(group, event_id=event_id, idempotency_key=idempotency_key)
    if existing is not None:
        return CommunicationKafkaHandleResult(
            status="duplicate",
            receipt=existing,
            duplicate=True,
        )

    event_type = _payload_text(safe_payload, "event_type")
    schema_version = _payload_text(safe_payload, "schema_version")
    if schema_version != COMMUNICATION_KAFKA_SCHEMA_VERSION:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="ignored",
            error_message="unsupported_schema_version",
        )
        return CommunicationKafkaHandleResult(status="ignored", receipt=receipt, ignored=True)
    if event_type not in COMMUNICATION_KAFKA_EVENT_TYPES:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="ignored",
            error_message="unsupported_event_type",
        )
        return CommunicationKafkaHandleResult(status="ignored", receipt=receipt, ignored=True)

    missing_fields = _missing_required_fields(safe_payload, event_type=event_type)
    if missing_fields:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="failed",
            error_message=f"missing_required_metadata:{','.join(missing_fields)}",
        )
        _record_communication_event_dead_letter(
            payload=safe_payload,
            reason=receipt.error_message,
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(status="failed", receipt=receipt, failed=True)

    invalid_fields = _invalid_uuid_fields(safe_payload)
    if invalid_fields:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="failed",
            error_message=f"invalid_uuid_metadata:{','.join(invalid_fields)}",
        )
        _record_communication_event_dead_letter(
            payload=safe_payload,
            reason=receipt.error_message,
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(status="failed", receipt=receipt, failed=True)

    organization = Organization.objects.filter(id=safe_payload["organization_id"]).first()
    if organization is None:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="failed",
            error_message="organization_not_found",
        )
        _record_communication_event_dead_letter(
            payload=safe_payload,
            reason=receipt.error_message,
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(status="failed", receipt=receipt, failed=True)

    company = _resolve_receipt_company(safe_payload, organization=organization)
    if _payload_text(safe_payload, "company_id") and company is None:
        receipt = _record_communication_event_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="failed",
            error_message="company_not_found",
        )
        _record_communication_event_dead_letter(
            payload=safe_payload,
            reason=receipt.error_message,
            receipt=receipt,
        )
        return CommunicationKafkaHandleResult(status="failed", receipt=receipt, failed=True)

    receipt = _record_communication_event_receipt(
        payload=safe_payload,
        consumer_group=group,
        topic=topic,
        partition=partition,
        offset=offset,
        status="handled",
        organization=organization,
        company=company,
    )
    if receipt.status != "handled":
        return CommunicationKafkaHandleResult(
            status="duplicate",
            receipt=receipt,
            duplicate=True,
        )
    return CommunicationKafkaHandleResult(status="handled", receipt=receipt, handled=True)


def build_communication_kafka_payload(event: DomainEventOutbox) -> dict[str, Any]:
    """Build metadata-only event payload; consumers must fetch details through backend APIs."""

    return build_communication_kafka_envelope(event).as_payload()


def build_communication_kafka_envelope(event: DomainEventOutbox) -> CommunicationKafkaEnvelope:
    """Build the authoritative metadata envelope for one outbox event."""

    payload = sanitize_outbox_payload(event.payload_json)
    return CommunicationKafkaEnvelope(
        event_id=str(event.id),
        domain_event_id=str(event.domain_event_id) if event.domain_event_id else None,
        event_type=event.event_type,
        schema_version=event.schema_version,
        aggregate_type=event.aggregate_type,
        aggregate_id=str(event.aggregate_id),
        organization_id=str(event.organization_id),
        company_id=str(event.company_id) if event.company_id else None,
        visibility=event.visibility,
        topic=event.topic,
        created_at=event.created_at.isoformat(),
        idempotency_key=event.idempotency_key,
        payload=payload,
    )


def _setting_value(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _setting_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def communication_kafka_max_payload_bytes() -> int:
    return max(
        _setting_int(
            "COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES",
            DEFAULT_COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES,
        ),
        1024,
    )


def _encode_communication_kafka_payload(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":")).encode("utf-8")
    max_payload_bytes = communication_kafka_max_payload_bytes()
    if len(encoded) > max_payload_bytes:
        raise KafkaDeliveryError(
            f"Kafka payload exceeds COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES ({max_payload_bytes})."
        )
    return encoded


def _record_communication_event_receipt(
    *,
    payload: dict[str, Any],
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
    status: str,
    error_message: str = "",
    organization: Organization | None = None,
    company: Graph | None = None,
) -> CommunicationEventReceipt:
    safe_payload = sanitize_outbox_payload(payload)
    group = _compact_consumer_group(consumer_group or communication_kafka_consumer_group())
    event_id = _payload_text(safe_payload, "event_id")
    idempotency_key = _payload_text(safe_payload, "idempotency_key")
    existing = _find_existing_receipt(group, event_id=event_id, idempotency_key=idempotency_key)
    if existing is not None:
        return existing
    outbox_event = _resolve_receipt_outbox_event(event_id)
    now = timezone.now()
    try:
        with transaction.atomic():
            return CommunicationEventReceipt.objects.create(
                consumer_group=group,
                event_id=event_id,
                idempotency_key=idempotency_key,
                topic=str(topic or safe_payload.get("topic") or "")[:255],
                partition=partition,
                offset=offset,
                organization=organization,
                company=company,
                outbox_event=outbox_event,
                event_type=_payload_text(safe_payload, "event_type")[:128],
                schema_version=_payload_text(safe_payload, "schema_version")[:64],
                aggregate_type=_payload_text(safe_payload, "aggregate_type")[:64],
                aggregate_id=_payload_text(safe_payload, "aggregate_id")[:64],
                status=status,
                error_message=_sanitize_consumer_error(error_message),
                payload_json=safe_payload,
                handled_at=now,
            )
    except IntegrityError:
        duplicate = _find_existing_receipt(
            group,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )
        if duplicate is not None:
            return duplicate
        raise


def _record_failed_transport_receipt(
    *,
    reason: str,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> CommunicationEventReceipt:
    payload = {
        "idempotency_key": _transport_receipt_idempotency_key(
            reason=reason,
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
        ),
        "topic": topic,
        "kafka_partition": partition,
        "kafka_offset": offset,
        "failure_reason": reason,
    }
    return _record_communication_event_receipt(
        payload=payload,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
        status="failed",
        error_message=reason,
    )


def _transport_receipt_idempotency_key(
    *,
    reason: str,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> str:
    return (
        "communication-kafka-transport:"
        f"{_compact_consumer_group(consumer_group)}:{topic}:{partition}:{offset}:{reason}"
    )[:255]


def _record_communication_event_dead_letter(
    *,
    payload: dict[str, Any],
    reason: str,
    receipt: CommunicationEventReceipt,
) -> None:
    _record_communication_kafka_metric(
        "communication_kafka_consumer_failure",
        value=1,
        unit="count",
        dimensions={
            "topic": receipt.topic,
            "consumer_group": receipt.consumer_group,
            "reason": reason,
        },
        organization_id=receipt.organization_id,
    )
    record_event_dead_letter(
        source="communication_kafka_consumer",
        reason=reason,
        payload=payload,
        organization=receipt.organization,
        event_id=receipt.event_id,
        idempotency_key=receipt.idempotency_key,
        event_type=receipt.event_type,
        error_class="KafkaIngressValidationError",
    )


def _find_existing_receipt(
    consumer_group: str,
    *,
    event_id: str,
    idempotency_key: str,
) -> CommunicationEventReceipt | None:
    if not event_id and not idempotency_key:
        return None
    query = CommunicationEventReceipt.objects.filter(consumer_group=consumer_group)
    filters = Q()
    if event_id:
        filters |= Q(event_id=event_id)
    if idempotency_key:
        filters |= Q(idempotency_key=idempotency_key)
    return query.filter(filters).order_by("-received_at").first()


def _missing_required_fields(payload: dict[str, Any], *, event_type: str) -> list[str]:
    required = set(_REQUIRED_COMMUNICATION_EVENT_FIELDS)
    required.update(_EVENT_SPECIFIC_REQUIRED_FIELDS.get(event_type, set()))
    return sorted(field for field in required if not _payload_text(payload, field))


def _invalid_uuid_fields(payload: dict[str, Any]) -> list[str]:
    uuid_fields = ["event_id", "organization_id", "aggregate_id"]
    if _payload_text(payload, "company_id"):
        uuid_fields.append("company_id")
    return [field for field in uuid_fields if not _is_uuid(_payload_text(payload, field))]


def _resolve_receipt_company(
    payload: dict[str, Any],
    *,
    organization: Organization,
) -> Graph | None:
    company_id = _payload_text(payload, "company_id")
    if not company_id:
        return None
    return cast(
        Graph | None, Graph.objects.filter(id=company_id, organization=organization).first()
    )


def _resolve_receipt_outbox_event(event_id: str) -> DomainEventOutbox | None:
    if not _is_uuid(event_id):
        return None
    return DomainEventOutbox.objects.filter(id=event_id).first()


def _payload_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None:
        return ""
    return str(value).strip()


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _sanitize_consumer_error(value: object) -> str:
    message = redact_payload(str(value or ""))
    if not isinstance(message, str) or not message:
        return "communication_kafka_consumer_error"
    lowered = message.lower()
    if any(
        term in lowered
        for term in (
            "secret",
            "credential",
            "private_config",
            "raw_prompt",
            "prompt",
            "evidence_bundle",
            "debug_trace",
            "token",
            "pack_manifest",
        )
    ):
        return "communication_kafka_consumer_error"
    return message[:_MAX_CONSUMER_ERROR_LENGTH]


def _record_communication_kafka_metric(
    metric_name: str,
    *,
    value: float,
    unit: str,
    dimensions: dict[str, Any] | None = None,
    organization_id: UUID | str | None = None,
) -> None:
    record_service_metric_sample(
        metric_name=metric_name,
        source="communication_kafka",
        value=value,
        unit=unit,
        dimensions=dimensions or {},
        organization_id=organization_id,
    )


def _kafka_error_callback(error: Any) -> None:
    log_event(
        logger,
        logging.WARNING,
        "communication_kafka_client_error",
        error_message=_sanitize_consumer_error(error),
    )
    _record_communication_kafka_metric(
        "communication_kafka_client_error",
        value=1,
        unit="count",
        dimensions={"error": _sanitize_consumer_error(error)},
    )


def _kafka_throttle_callback(event: Any) -> None:
    throttle_time_ms = 0.0
    try:
        throttle_time_ms = float(getattr(event, "throttle_time", 0) or 0)
    except (TypeError, ValueError):
        throttle_time_ms = 0.0
    _record_communication_kafka_metric(
        "communication_kafka_client_throttle_ms",
        value=throttle_time_ms,
        unit="ms",
        dimensions={"broker": str(getattr(event, "broker_name", "") or "")},
    )


def _kafka_stats_callback(stats_json: str) -> None:
    try:
        stats = json.loads(stats_json or "{}")
    except json.JSONDecodeError:
        return
    for metric_name, key in (
        ("communication_kafka_client_reply_queue", "replyq"),
        ("communication_kafka_client_message_queue", "msg_cnt"),
    ):
        value = stats.get(key)
        if value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        _record_communication_kafka_metric(
            metric_name,
            value=numeric_value,
            unit="count",
            dimensions={"client_id": str(stats.get("name") or "")},
        )


def _poll_producer_if_supported(producer: KafkaProducerLike, timeout_seconds: float) -> None:
    poll = getattr(producer, "poll", None)
    if callable(poll):
        poll(timeout_seconds)


def _compact_consumer_group(value: str) -> str:
    group = str(value or "").strip()[:128]
    return group or DEFAULT_COMMUNICATION_KAFKA_CONSUMER_GROUP


def _message_topic(message: KafkaMessageLike) -> str:
    try:
        return str(message.topic() or "")
    except Exception:  # noqa: BLE001 - transport adapters should not break receipt handling.
        return ""


def _message_partition(message: KafkaMessageLike) -> int | None:
    try:
        return int(message.partition())
    except Exception:  # noqa: BLE001 - transport adapters should not break receipt handling.
        return None


def _message_offset(message: KafkaMessageLike) -> int | None:
    try:
        return int(message.offset())
    except Exception:  # noqa: BLE001 - transport adapters should not break receipt handling.
        return None


def _raw_kafka_value_size(raw_value: bytes | str | None) -> int:
    if isinstance(raw_value, bytes):
        return len(raw_value)
    if isinstance(raw_value, str):
        return len(raw_value.encode("utf-8"))
    return 0


def _is_partition_eof_error(error: Any) -> bool:
    code = getattr(error, "code", None)
    error_code: Any = None
    if callable(code):
        try:
            error_code = code()
        except Exception:  # noqa: BLE001 - best-effort transport classification.
            error_code = None
    if str(error_code) in {"_PARTITION_EOF", "-191"}:
        return True
    name = str(getattr(error, "name", "") or getattr(error, "__class__", "")).lower()
    message = str(error).lower()
    return "partition_eof" in name or "_partition_eof" in message or "partition eof" in message


def _handle_kafka_poll_error(
    *,
    error: Any,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> _ConsumeStatusDelta:
    if _is_partition_eof_error(error):
        return _ConsumeStatusDelta(ignored=1)
    _record_kafka_transport_error(
        error=error,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
    )
    return _ConsumeStatusDelta(failed=1)


def _consume_status_delta(result: CommunicationKafkaHandleResult) -> _ConsumeStatusDelta:
    if result.duplicate:
        return _ConsumeStatusDelta(duplicates=1)
    if result.handled:
        return _ConsumeStatusDelta(handled=1)
    if result.ignored:
        return _ConsumeStatusDelta(ignored=1)
    if result.failed:
        return _ConsumeStatusDelta(failed=1)
    return _ConsumeStatusDelta()


def _record_consumer_handler_exception(
    exc: Exception,
    *,
    topic: str,
    partition: int | None,
    offset: int | None,
    consumer_group: str,
) -> None:
    _record_communication_kafka_metric(
        "communication_kafka_consumer_failure",
        value=1,
        unit="count",
        dimensions={
            "topic": topic,
            "consumer_group": consumer_group,
            "error_class": exc.__class__.__name__,
        },
    )
    log_event(
        logger,
        logging.ERROR,
        "communication_kafka_consumer_handler_failed",
        topic=topic,
        partition=partition,
        offset=offset,
        consumer_group=consumer_group,
        error_class=exc.__class__.__name__,
        error_message=_sanitize_consumer_error(exc),
    )


def _record_kafka_transport_error(
    *,
    error: Any,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> None:
    reason = _sanitize_consumer_error(error)
    payload = {
        "topic": topic,
        "kafka_partition": partition,
        "kafka_offset": offset,
        "consumer_group": _compact_consumer_group(consumer_group),
        "error": reason,
    }
    record_event_dead_letter(
        source="communication_kafka_consumer",
        reason="kafka_transport_error",
        payload=payload,
        event_type="communication.kafka.transport_error",
        error_class=error.__class__.__name__,
    )
    log_event(
        logger,
        logging.WARNING,
        "communication_kafka_transport_error",
        topic=topic,
        partition=partition,
        offset=offset,
        consumer_group=consumer_group,
        error_class=error.__class__.__name__,
        error_message=reason,
    )
    _record_communication_kafka_metric(
        "communication_kafka_transport_error",
        value=1,
        unit="count",
        dimensions={"topic": topic, "consumer_group": consumer_group},
    )


def _commit_if_supported(
    consumer: KafkaConsumerLike,
    message: KafkaMessageLike,
    *,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> bool:
    try:
        consumer.commit(message=message, asynchronous=False)
    except AttributeError:
        return True
    except Exception as exc:  # noqa: BLE001 - duplicate-safe retry will reprocess the receipt.
        log_event(
            logger,
            logging.ERROR,
            "communication_kafka_commit_failed",
            topic=topic,
            partition=partition,
            offset=offset,
            consumer_group=consumer_group,
            error_class=exc.__class__.__name__,
            error_message=_sanitize_consumer_error(exc),
        )
        _record_communication_kafka_metric(
            "communication_kafka_commit_failure",
            value=1,
            unit="count",
            dimensions={"topic": topic, "consumer_group": consumer_group},
        )
        return False
    return True


def build_communication_kafka_readiness_payload(
    *,
    admin_client_factory: Any | None = None,
) -> dict[str, Any]:
    """Check managed Kafka reachability and backend-owned outbox backlog."""

    started_at = time.perf_counter()
    topic = communication_kafka_topic()
    backlog_threshold = max(
        _setting_int("COMMUNICATION_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD", 1000),
        0,
    )
    backlog = _communication_kafka_outbox_backlog(topic=topic)
    backlog_ready = backlog_threshold <= 0 or backlog <= backlog_threshold
    if not communication_kafka_enabled():
        return {
            "ready": False,
            "enabled": False,
            "topic": topic,
            "broker_ready": False,
            "topic_ready": False,
            "backlog": backlog,
            "backlog_threshold": backlog_threshold,
            "backlog_ready": backlog_ready,
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
            "error": "COMMUNICATION_KAFKA_ENABLED is false.",
        }

    broker_ready = False
    topic_ready = False
    error_message = ""
    try:
        factory = admin_client_factory or _load_confluent_kafka_admin_client()
        admin_client = factory(_communication_kafka_common_config())
        metadata_timeout = float(
            getattr(settings, "COMMUNICATION_KAFKA_METADATA_TIMEOUT_SECONDS", 5)
        )
        metadata = admin_client.list_topics(topic=topic, timeout=metadata_timeout)
        topics = getattr(metadata, "topics", {}) or {}
        topic_metadata = topics.get(topic)
        topic_error = getattr(topic_metadata, "error", None) if topic_metadata else None
        broker_ready = True
        topic_ready = topic_metadata is not None and not topic_error
        if topic_error:
            error_message = _sanitize_consumer_error(topic_error)
    except Exception as exc:  # noqa: BLE001 - readiness must report failures as data.
        error_message = _sanitize_consumer_error(exc)

    ready = bool(broker_ready and topic_ready and backlog_ready)
    return {
        "ready": ready,
        "enabled": True,
        "topic": topic,
        "broker_ready": broker_ready,
        "topic_ready": topic_ready,
        "backlog": backlog,
        "backlog_threshold": backlog_threshold,
        "backlog_ready": backlog_ready,
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
        "error": error_message,
    }


def _communication_kafka_outbox_backlog(*, topic: str) -> int:
    return int(
        DomainEventOutbox.objects.filter(
            topic=topic,
            status__in=["pending", "failed", "deferred"],
        ).count()
    )


def _load_confluent_kafka_producer() -> Any:
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise KafkaConfigurationError(
            "confluent-kafka is required when COMMUNICATION_KAFKA_ENABLED=true."
        ) from exc
    return Producer


def _load_confluent_kafka_consumer() -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:
        raise KafkaConfigurationError(
            "confluent-kafka is required when COMMUNICATION_KAFKA_ENABLED=true."
        ) from exc
    return Consumer


def _load_confluent_kafka_admin_client() -> Any:
    try:
        from confluent_kafka.admin import AdminClient
    except ImportError as exc:
        raise KafkaConfigurationError(
            "confluent-kafka is required when COMMUNICATION_KAFKA_ENABLED=true."
        ) from exc
    return AdminClient
