"""Optional Kafka transport for committed communication outbox events."""

from __future__ import annotations

import json
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
from application.services.redaction import redact_payload
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    DomainEventOutbox,
    Graph,
    Organization,
)

DEFAULT_COMMUNICATION_KAFKA_TOPIC = "forgegraph.communication.events.v1"
DEFAULT_COMMUNICATION_KAFKA_CONSUMER_GROUP = "forgegraph-communication-events"
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
    empty_polls: int = 0


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
            key=communication_kafka_key(event),
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


def communication_kafka_consumer_config() -> dict[str, Any]:
    config = dict(communication_kafka_config())
    config.pop("enable.idempotence", None)
    config.update(
        {
            "group.id": communication_kafka_consumer_group(),
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
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
    empty_polls = 0
    for _ in range(max(int(limit or 0), 0)):
        message = consumer.poll(float(poll_timeout_seconds))
        if message is None:
            empty_polls += 1
            break
        if message.error() is not None:
            failed += 1
            _commit_if_supported(consumer, message)
            continue
        result = handle_communication_kafka_message(
            message.value(),
            consumer_group=group,
            topic=_message_topic(message),
            partition=_message_partition(message),
            offset=_message_offset(message),
        )
        if result.duplicate:
            duplicates += 1
        elif result.handled:
            handled += 1
        elif result.ignored:
            ignored += 1
        elif result.failed:
            failed += 1
        _commit_if_supported(consumer, message)
    return CommunicationKafkaConsumeResult(
        handled=handled,
        duplicates=duplicates,
        ignored=ignored,
        failed=failed,
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
    try:
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")
        decoded = json.loads(raw_value or "{}")
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _ = exc
        receipt = _record_communication_event_receipt(
            payload={},
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="failed",
            error_message="invalid_json",
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
    envelope["event_type"] = event.event_type
    envelope["schema_version"] = event.schema_version
    envelope["aggregate_type"] = event.aggregate_type
    envelope["aggregate_id"] = str(event.aggregate_id)
    envelope["organization_id"] = str(event.organization_id)
    envelope["company_id"] = str(event.company_id) if event.company_id else None
    envelope["visibility"] = event.visibility
    envelope["topic"] = event.topic
    envelope["created_at"] = event.created_at.isoformat()
    envelope["idempotency_key"] = event.idempotency_key
    return sanitize_outbox_payload(envelope)


def _setting_value(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


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
    return Graph.objects.filter(id=company_id, organization=organization).first()


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


def _commit_if_supported(consumer: KafkaConsumerLike, message: KafkaMessageLike) -> None:
    try:
        consumer.commit(message=message, asynchronous=False)
    except AttributeError:
        return


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
