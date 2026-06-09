"""Optional Kafka transport for WorkWhiteboard board outbox events."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from application.services.domain_event_outbox import (
    DomainEventOutboxPublisher,
    sanitize_outbox_payload,
)
from application.services.event_dead_letters import record_event_dead_letter
from application.services.whiteboard_boards import (
    WHITEBOARD_BOARD_EVENT_SCHEMA_VERSION,
    WHITEBOARD_BOARD_EVENT_TYPES,
    WHITEBOARD_BOARD_OUTBOX_TOPIC,
    refresh_whiteboard_board_redis_snapshot,
)
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    DomainEventOutbox,
    EventDeadLetterRecord,
    Graph,
    Organization,
    WorkWhiteboard,
)

DEFAULT_WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP = "forgegraph-whiteboard-board-events"
DEFAULT_WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES = 64 * 1024
_REQUIRED_FIELDS = {
    "event_id",
    "event_type",
    "schema_version",
    "organization_id",
    "company_id",
    "whiteboard_id",
    "created_at",
    "idempotency_key",
}
_UUID_FIELDS = {"event_id", "organization_id", "company_id", "whiteboard_id"}


class WhiteboardBoardKafkaConfigurationError(RuntimeError):
    """Raised when board Kafka is enabled but not configured."""


class WhiteboardBoardKafkaDeliveryError(RuntimeError):
    """Raised when board Kafka delivery fails."""


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
        """Flush producer messages."""


class KafkaConsumerLike(Protocol):
    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to topics."""

    def poll(self, timeout: float | None = None) -> KafkaMessageLike | None:
        """Poll one message."""

    def commit(self, message: KafkaMessageLike | None = None, *, asynchronous: bool = False) -> Any:
        """Commit a message offset."""

    def close(self) -> None:
        """Close the consumer."""


class KafkaMessageLike(Protocol):
    def error(self) -> Any | None:
        """Return transport error."""

    def value(self) -> bytes | str | None:
        """Return raw message value."""

    def topic(self) -> str:
        """Return topic."""

    def partition(self) -> int:
        """Return partition."""

    def offset(self) -> int:
        """Return offset."""


@dataclass(frozen=True, slots=True)
class WhiteboardBoardKafkaHandleResult:
    status: str
    receipt: CommunicationEventReceipt | None = None
    handled: bool = False
    duplicate: bool = False
    ignored: bool = False
    failed: bool = False


@dataclass(frozen=True, slots=True)
class WhiteboardBoardKafkaConsumeResult:
    handled: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0
    commit_failed: int = 0
    empty_polls: int = 0


class WhiteboardBoardKafkaOutboxPublisher(DomainEventOutboxPublisher):
    """Publish sanitized board outbox metadata keyed by whiteboard_id."""

    def __init__(
        self,
        *,
        producer_factory: Any | None = None,
        config: dict[str, Any] | None = None,
        topic: str = "",
        flush_timeout_seconds: float | None = None,
    ) -> None:
        self.topic = topic or whiteboard_board_kafka_topic()
        self.flush_timeout_seconds = (
            float(flush_timeout_seconds)
            if flush_timeout_seconds is not None
            else float(getattr(settings, "WHITEBOARD_BOARD_KAFKA_FLUSH_TIMEOUT_SECONDS", 5))
        )
        factory = producer_factory or _load_confluent_kafka_producer()
        producer_config = config if config is not None else whiteboard_board_kafka_config()
        self.producer = cast(KafkaProducerLike, factory(producer_config))

    def publish(self, event: DomainEventOutbox) -> None:
        payload = build_whiteboard_board_kafka_payload(event)
        encoded = _encode_payload(payload)
        delivery_errors: list[str] = []

        def _delivery_callback(error: Any, _message: Any) -> None:
            if error is not None:
                delivery_errors.append(str(error))

        self.producer.produce(
            self.topic,
            key=whiteboard_board_kafka_key(event),
            value=encoded,
            headers=_headers(payload),
            callback=_delivery_callback,
        )
        undelivered = self.producer.flush(self.flush_timeout_seconds)
        if delivery_errors:
            raise WhiteboardBoardKafkaDeliveryError(delivery_errors[0])
        if undelivered:
            raise WhiteboardBoardKafkaDeliveryError(
                f"Kafka producer flush timed out with {undelivered} undelivered messages."
            )


def whiteboard_board_kafka_enabled() -> bool:
    return bool(getattr(settings, "WHITEBOARD_BOARD_KAFKA_ENABLED", False))


def whiteboard_board_kafka_topic() -> str:
    return (
        _setting_value("WHITEBOARD_BOARD_KAFKA_TOPIC")
        or _setting_value("KAFKA_WHITEBOARD_BOARD_TOPIC")
        or WHITEBOARD_BOARD_OUTBOX_TOPIC
    )


def whiteboard_board_kafka_consumer_group() -> str:
    return (
        _setting_value("WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP")
        or _setting_value("KAFKA_WHITEBOARD_BOARD_CONSUMER_GROUP")
        or DEFAULT_WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP
    )


def build_configured_whiteboard_board_kafka_publisher() -> WhiteboardBoardKafkaOutboxPublisher:
    if not whiteboard_board_kafka_enabled():
        raise WhiteboardBoardKafkaConfigurationError("WHITEBOARD_BOARD_KAFKA_ENABLED is false.")
    return WhiteboardBoardKafkaOutboxPublisher()


def build_configured_whiteboard_board_kafka_consumer(
    *,
    consumer_factory: Any | None = None,
) -> KafkaConsumerLike:
    if not whiteboard_board_kafka_enabled():
        raise WhiteboardBoardKafkaConfigurationError("WHITEBOARD_BOARD_KAFKA_ENABLED is false.")
    factory = consumer_factory or _load_confluent_kafka_consumer()
    consumer = cast(KafkaConsumerLike, factory(whiteboard_board_kafka_consumer_config()))
    consumer.subscribe([whiteboard_board_kafka_topic()])
    return consumer


def whiteboard_board_kafka_config() -> dict[str, Any]:
    config = _common_config()
    config.update(
        {
            "enable.idempotence": True,
            "acks": "all",
            "retries": _setting_int("WHITEBOARD_BOARD_KAFKA_RETRIES", 5),
            "retry.backoff.ms": _setting_int("WHITEBOARD_BOARD_KAFKA_RETRY_BACKOFF_MS", 250),
            "delivery.timeout.ms": _setting_int(
                "WHITEBOARD_BOARD_KAFKA_DELIVERY_TIMEOUT_MS", 30000
            ),
            "request.timeout.ms": _setting_int("WHITEBOARD_BOARD_KAFKA_REQUEST_TIMEOUT_MS", 10000),
            "linger.ms": _setting_int("WHITEBOARD_BOARD_KAFKA_LINGER_MS", 5),
        }
    )
    compression_type = _setting_value("WHITEBOARD_BOARD_KAFKA_COMPRESSION_TYPE") or "lz4"
    if compression_type:
        config["compression.type"] = compression_type
    return config


def whiteboard_board_kafka_consumer_config() -> dict[str, Any]:
    config = _common_config()
    config.update(
        {
            "group.id": whiteboard_board_kafka_consumer_group(),
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": _setting_value("WHITEBOARD_BOARD_KAFKA_AUTO_OFFSET_RESET")
            or "earliest",
            "isolation.level": _setting_value("WHITEBOARD_BOARD_KAFKA_ISOLATION_LEVEL")
            or "read_committed",
        }
    )
    return config


def whiteboard_board_kafka_key(event: DomainEventOutbox) -> str:
    payload = sanitize_outbox_payload(event.payload_json)
    whiteboard_id = str(payload.get("whiteboard_id") or "").strip()
    return whiteboard_id or str(event.aggregate_id)


def build_whiteboard_board_kafka_payload(event: DomainEventOutbox) -> dict[str, Any]:
    payload = sanitize_outbox_payload(event.payload_json)
    envelope = {
        "event_id": str(event.id),
        "domain_event_id": str(event.domain_event_id) if event.domain_event_id else None,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "organization_id": str(event.organization_id),
        "company_id": str(event.company_id) if event.company_id else payload.get("company_id"),
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "visibility": event.visibility,
        "topic": event.topic,
        "created_at": event.created_at.isoformat(),
        "idempotency_key": event.idempotency_key,
    }
    envelope.update(payload)
    for key, value in {
        "event_id": str(event.id),
        "domain_event_id": str(event.domain_event_id) if event.domain_event_id else None,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "organization_id": str(event.organization_id),
        "company_id": str(event.company_id) if event.company_id else payload.get("company_id"),
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "visibility": event.visibility,
        "topic": event.topic,
        "idempotency_key": event.idempotency_key,
    }.items():
        envelope[key] = value
    return sanitize_outbox_payload(envelope)


def handle_whiteboard_board_kafka_message(
    raw_value: bytes | str | None,
    *,
    consumer_group: str = "",
    topic: str = "",
    partition: int | None = None,
    offset: int | None = None,
) -> WhiteboardBoardKafkaHandleResult:
    if _raw_size(raw_value) > whiteboard_board_kafka_max_payload_bytes():
        receipt = _record_failed_transport_receipt(
            reason="payload_too_large",
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
        _dead_letter(payload=receipt.payload_json, reason="payload_too_large", receipt=receipt)
        return WhiteboardBoardKafkaHandleResult(status="failed", receipt=receipt, failed=True)
    try:
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")
        decoded = json.loads(raw_value or "{}")
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        receipt = _record_failed_transport_receipt(
            reason="invalid_json",
            consumer_group=consumer_group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
        _dead_letter(payload=receipt.payload_json, reason="invalid_json", receipt=receipt)
        return WhiteboardBoardKafkaHandleResult(status="failed", receipt=receipt, failed=True)
    return handle_whiteboard_board_kafka_event(
        decoded,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
    )


def handle_whiteboard_board_kafka_event(
    payload: dict[str, Any] | Any,
    *,
    consumer_group: str = "",
    topic: str = "",
    partition: int | None = None,
    offset: int | None = None,
) -> WhiteboardBoardKafkaHandleResult:
    safe_payload = sanitize_outbox_payload(payload if isinstance(payload, dict) else {})
    group = _compact_consumer_group(consumer_group or whiteboard_board_kafka_consumer_group())
    event_id = _payload_text(safe_payload, "event_id")
    idempotency_key = _payload_text(safe_payload, "idempotency_key")
    existing = _find_existing_receipt(group, event_id=event_id, idempotency_key=idempotency_key)
    if existing is not None:
        return WhiteboardBoardKafkaHandleResult(
            status="duplicate", receipt=existing, duplicate=True
        )

    schema_version = _payload_text(safe_payload, "schema_version")
    event_type = _payload_text(safe_payload, "event_type")
    if schema_version != WHITEBOARD_BOARD_EVENT_SCHEMA_VERSION:
        receipt = _record_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="ignored",
            error_message="unsupported_schema_version",
        )
        return WhiteboardBoardKafkaHandleResult(status="ignored", receipt=receipt, ignored=True)
    if event_type not in WHITEBOARD_BOARD_EVENT_TYPES:
        receipt = _record_receipt(
            payload=safe_payload,
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            status="ignored",
            error_message="unsupported_event_type",
        )
        return WhiteboardBoardKafkaHandleResult(status="ignored", receipt=receipt, ignored=True)

    missing = _missing_required_fields(safe_payload, event_type=event_type)
    if missing:
        return _failed_event(
            safe_payload,
            reason=f"missing_required_metadata:{','.join(missing)}",
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
    invalid = _invalid_uuid_fields(safe_payload)
    if invalid:
        return _failed_event(
            safe_payload,
            reason=f"invalid_uuid_metadata:{','.join(invalid)}",
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
        )

    organization = Organization.objects.filter(id=safe_payload["organization_id"]).first()
    if organization is None:
        return _failed_event(
            safe_payload,
            reason="organization_not_found",
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
        )
    company = Graph.objects.filter(
        id=safe_payload["company_id"],
        organization=organization,
    ).first()
    if company is None:
        return _failed_event(
            safe_payload,
            reason="company_not_found",
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            organization=organization,
        )
    whiteboard = WorkWhiteboard.objects.filter(
        id=safe_payload["whiteboard_id"],
        organization=organization,
        company=company,
    ).first()
    if whiteboard is None:
        return _failed_event(
            safe_payload,
            reason="whiteboard_not_found",
            consumer_group=group,
            topic=topic,
            partition=partition,
            offset=offset,
            organization=organization,
            company=company,
        )

    refresh_whiteboard_board_redis_snapshot(whiteboard.id)
    receipt = _record_receipt(
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
        return WhiteboardBoardKafkaHandleResult(status="duplicate", receipt=receipt, duplicate=True)
    return WhiteboardBoardKafkaHandleResult(status="handled", receipt=receipt, handled=True)


def consume_whiteboard_board_kafka_events(
    *,
    consumer: KafkaConsumerLike,
    consumer_group: str = "",
    limit: int = 100,
    poll_timeout_seconds: float = 1.0,
) -> WhiteboardBoardKafkaConsumeResult:
    group = _compact_consumer_group(consumer_group or whiteboard_board_kafka_consumer_group())
    handled = duplicates = ignored = failed = commit_failed = empty_polls = 0
    for _ in range(max(int(limit or 0), 0)):
        message = consumer.poll(float(poll_timeout_seconds))
        if message is None:
            empty_polls += 1
            break
        if message.error() is not None:
            failed += 1
            _record_transport_error(
                error=message.error(),
                consumer_group=group,
                topic=_message_topic(message),
                partition=_message_partition(message),
                offset=_message_offset(message),
            )
            continue
        result = handle_whiteboard_board_kafka_message(
            message.value(),
            consumer_group=group,
            topic=_message_topic(message),
            partition=_message_partition(message),
            offset=_message_offset(message),
        )
        handled += 1 if result.handled else 0
        duplicates += 1 if result.duplicate else 0
        ignored += 1 if result.ignored else 0
        failed += 1 if result.failed else 0
        if not _commit_if_supported(consumer, message):
            commit_failed += 1
    return WhiteboardBoardKafkaConsumeResult(
        handled=handled,
        duplicates=duplicates,
        ignored=ignored,
        failed=failed,
        commit_failed=commit_failed,
        empty_polls=empty_polls,
    )


def whiteboard_board_kafka_max_payload_bytes() -> int:
    return max(
        _setting_int(
            "WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES",
            DEFAULT_WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES,
        ),
        1024,
    )


def build_whiteboard_board_kafka_readiness_payload(
    *,
    admin_client_factory: Any | None = None,
) -> dict[str, Any]:
    """Check whiteboard board Kafka reachability and backend-owned outbox backlog."""

    started_at = time.perf_counter()
    topic = whiteboard_board_kafka_topic()
    backlog_threshold = max(
        _setting_int("WHITEBOARD_BOARD_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD", 1000),
        0,
    )
    backlog = whiteboard_board_kafka_outbox_backlog(topic=topic)
    backlog_ready = backlog_threshold <= 0 or backlog <= backlog_threshold
    if not whiteboard_board_kafka_enabled():
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
            "error": "WHITEBOARD_BOARD_KAFKA_ENABLED is false.",
        }

    broker_ready = False
    topic_ready = False
    error_message = ""
    try:
        factory = admin_client_factory or _load_confluent_kafka_admin_client()
        admin_client = factory(_common_config())
        metadata_timeout = float(
            getattr(settings, "WHITEBOARD_BOARD_KAFKA_METADATA_TIMEOUT_SECONDS", 5)
        )
        metadata = admin_client.list_topics(topic=topic, timeout=metadata_timeout)
        topics = getattr(metadata, "topics", {}) or {}
        topic_metadata = topics.get(topic)
        topic_error = getattr(topic_metadata, "error", None) if topic_metadata else None
        broker_ready = True
        topic_ready = topic_metadata is not None and not topic_error
        if topic_error:
            error_message = str(topic_error)[:1000]
    except Exception as exc:  # noqa: BLE001 - readiness reports failures as data.
        error_message = str(exc)[:1000]

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


def whiteboard_board_kafka_outbox_backlog(*, topic: str | None = None) -> int:
    return int(
        DomainEventOutbox.objects.filter(
            topic=topic or whiteboard_board_kafka_topic(),
            status__in=["pending", "failed", "deferred"],
        ).count()
    )


def whiteboard_board_kafka_transport_evidence(
    *,
    organization: Organization,
    whiteboard_id: str = "",
    company_id: str = "",
) -> dict[str, Any]:
    """Return observability-only transport evidence scoped to backend-owned records."""

    topic = whiteboard_board_kafka_topic()
    group = whiteboard_board_kafka_consumer_group()
    whiteboard_id = str(whiteboard_id or "").strip()
    company_id = str(company_id or "").strip()

    organization_id = str(organization.id)
    outbox_query = DomainEventOutbox.objects.filter(organization=organization, topic=topic)
    receipt_query = CommunicationEventReceipt.objects.filter(
        consumer_group=group,
        topic=topic,
    ).filter(
        Q(organization=organization)
        | Q(organization__isnull=True, payload_json__organization_id=organization_id)
    )
    dead_letter_query = EventDeadLetterRecord.objects.filter(
        source="whiteboard_board_kafka_consumer",
    ).filter(
        Q(organization=organization)
        | Q(organization__isnull=True, payload__organization_id=organization_id)
    )

    if whiteboard_id:
        outbox_query = outbox_query.filter(payload_json__whiteboard_id=whiteboard_id)
        receipt_query = receipt_query.filter(payload_json__whiteboard_id=whiteboard_id)
        dead_letter_query = dead_letter_query.filter(payload__whiteboard_id=whiteboard_id)
    if company_id:
        outbox_query = outbox_query.filter(
            Q(company_id=company_id) | Q(company__isnull=True, payload_json__company_id=company_id)
        )
        receipt_query = receipt_query.filter(
            Q(company_id=company_id) | Q(company__isnull=True, payload_json__company_id=company_id)
        )
        dead_letter_query = dead_letter_query.filter(payload__company_id=company_id)

    outbox_counts = _counts_by_status(
        outbox_query,
        statuses=["pending", "published", "failed", "deferred"],
    )
    receipt_counts = _counts_by_status(
        receipt_query,
        statuses=["handled", "ignored", "failed"],
    )
    active_dead_letters = dead_letter_query.filter(status__in=["active", "replay_requested"])
    return {
        "transport": "whiteboard_board_kafka",
        "authoritative_state_source": "backend_db",
        "enabled": whiteboard_board_kafka_enabled(),
        "topic": topic,
        "consumer_group": group,
        "organization_id": str(organization.id),
        "company_id": company_id,
        "whiteboard_id": whiteboard_id,
        "outbox": {
            **outbox_counts,
            "total": outbox_query.count(),
            "backlog": outbox_query.filter(status__in=["pending", "failed", "deferred"]).count(),
        },
        "receipts": {
            **receipt_counts,
            "total": receipt_query.count(),
            "idempotent_duplicate_policy": "existing_receipt_reused",
        },
        "dead_letters": {
            "active_count": active_dead_letters.count(),
            "total": dead_letter_query.count(),
            "recent": [
                {
                    "id": str(item.id),
                    "status": item.status,
                    "reason": item.reason,
                    "event_id": item.event_id,
                    "event_type": item.event_type,
                    "last_seen_at": item.last_seen_at.isoformat(),
                }
                for item in dead_letter_query.order_by("-last_seen_at")[:10]
            ],
        },
        "recent_receipts": [
            {
                "id": str(item.id),
                "status": item.status,
                "event_id": item.event_id,
                "idempotency_key": item.idempotency_key,
                "topic": item.topic,
                "partition": item.partition,
                "offset": item.offset,
                "event_type": item.event_type,
                "received_at": item.received_at.isoformat(),
            }
            for item in receipt_query.order_by("-received_at")[:10]
        ],
        "generated_at": timezone.now().isoformat(),
    }


def _failed_event(
    payload: dict[str, Any],
    *,
    reason: str,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
    organization: Organization | None = None,
    company: Graph | None = None,
) -> WhiteboardBoardKafkaHandleResult:
    receipt = _record_receipt(
        payload=payload,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
        status="failed",
        error_message=reason,
        organization=organization,
        company=company,
    )
    _dead_letter(payload=payload, reason=reason, receipt=receipt)
    return WhiteboardBoardKafkaHandleResult(status="failed", receipt=receipt, failed=True)


def _record_receipt(
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
    group = _compact_consumer_group(consumer_group or whiteboard_board_kafka_consumer_group())
    event_id = _payload_text(safe_payload, "event_id")
    idempotency_key = _payload_text(safe_payload, "idempotency_key")
    existing = _find_existing_receipt(group, event_id=event_id, idempotency_key=idempotency_key)
    if existing is not None:
        return existing
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
                outbox_event=_resolve_outbox_event(event_id),
                event_type=_payload_text(safe_payload, "event_type")[:128],
                schema_version=_payload_text(safe_payload, "schema_version")[:64],
                aggregate_type=_payload_text(safe_payload, "aggregate_type")[:64],
                aggregate_id=_payload_text(safe_payload, "aggregate_id")[:64],
                status=status,
                error_message=str(error_message or "")[:1000],
                payload_json=safe_payload,
                handled_at=now,
            )
    except IntegrityError:
        duplicate = _find_existing_receipt(
            group, event_id=event_id, idempotency_key=idempotency_key
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
        "idempotency_key": (
            f"whiteboard-board-kafka-transport:{_compact_consumer_group(consumer_group)}:"
            f"{topic}:{partition}:{offset}:{reason}"
        )[:255],
        "topic": topic,
        "kafka_partition": partition,
        "kafka_offset": offset,
        "failure_reason": reason,
    }
    return _record_receipt(
        payload=payload,
        consumer_group=consumer_group,
        topic=topic,
        partition=partition,
        offset=offset,
        status="failed",
        error_message=reason,
    )


def _dead_letter(
    *, payload: dict[str, Any], reason: str, receipt: CommunicationEventReceipt
) -> None:
    record_event_dead_letter(
        source="whiteboard_board_kafka_consumer",
        reason=reason,
        payload=payload,
        organization=receipt.organization,
        event_id=receipt.event_id,
        idempotency_key=receipt.idempotency_key,
        event_type=receipt.event_type,
        error_class="WhiteboardBoardKafkaValidationError",
    )


def _record_transport_error(
    *,
    error: Any,
    consumer_group: str,
    topic: str,
    partition: int | None,
    offset: int | None,
) -> None:
    record_event_dead_letter(
        source="whiteboard_board_kafka_consumer",
        reason="kafka_transport_error",
        payload={
            "topic": topic,
            "kafka_partition": partition,
            "kafka_offset": offset,
            "consumer_group": _compact_consumer_group(consumer_group),
            "error": str(error)[:1000],
        },
        event_type="whiteboard.board.kafka.transport_error",
        error_class=error.__class__.__name__,
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
    required = set(_REQUIRED_FIELDS)
    if event_type.startswith("whiteboard.card."):
        required.add("routing_record_id")
    return sorted(field for field in required if not _payload_text(payload, field))


def _invalid_uuid_fields(payload: dict[str, Any]) -> list[str]:
    fields = set(_UUID_FIELDS)
    if _payload_text(payload, "routing_record_id"):
        fields.add("routing_record_id")
    return [field for field in sorted(fields) if not _is_uuid(_payload_text(payload, field))]


def _resolve_outbox_event(event_id: str) -> DomainEventOutbox | None:
    if not _is_uuid(event_id):
        return None
    return DomainEventOutbox.objects.filter(id=event_id).first()


def _common_config() -> dict[str, Any]:
    bootstrap_servers = _setting_value(
        "WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS"
    ) or _setting_value("KAFKA_BROKERS")
    if not bootstrap_servers:
        raise WhiteboardBoardKafkaConfigurationError(
            "WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS or KAFKA_BROKERS is required when board Kafka is enabled."
        )
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": _setting_value("WHITEBOARD_BOARD_KAFKA_CLIENT_ID")
        or _setting_value("KAFKA_CLIENT_ID")
        or "forgegraph-whiteboard-board-outbox",
    }
    security_protocol = _setting_value("WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL")
    if security_protocol:
        config["security.protocol"] = security_protocol
    sasl_mechanism = _setting_value("WHITEBOARD_BOARD_KAFKA_SASL_MECHANISM")
    if sasl_mechanism:
        config["sasl.mechanism"] = sasl_mechanism
    sasl_username = _setting_value("WHITEBOARD_BOARD_KAFKA_SASL_USERNAME")
    if sasl_username:
        config["sasl.username"] = sasl_username
    sasl_password = _setting_value("WHITEBOARD_BOARD_KAFKA_SASL_PASSWORD")
    if sasl_password:
        config["sasl.password"] = sasl_password
    return config


def _load_confluent_kafka_producer() -> Any:
    try:
        from confluent_kafka import Producer
    except ImportError as exc:  # pragma: no cover - exercised only when Kafka is installed.
        raise WhiteboardBoardKafkaConfigurationError(
            "confluent-kafka is required for board Kafka publishing."
        ) from exc
    return Producer


def _load_confluent_kafka_consumer() -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:  # pragma: no cover - exercised only when Kafka is installed.
        raise WhiteboardBoardKafkaConfigurationError(
            "confluent-kafka is required for board Kafka consuming."
        ) from exc
    return Consumer


def _load_confluent_kafka_admin_client() -> Any:
    try:
        from confluent_kafka.admin import AdminClient
    except ImportError as exc:  # pragma: no cover - exercised only when Kafka is installed.
        raise WhiteboardBoardKafkaConfigurationError(
            "confluent-kafka is required for board Kafka readiness."
        ) from exc
    return AdminClient


def _counts_by_status(queryset: Any, *, statuses: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(statuses, 0)
    for row in queryset.values("status").annotate(count=Count("id")):
        status = str(row["status"])
        if status in counts:
            counts[status] = int(row["count"])
    return counts


def _encode_payload(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":")).encode("utf-8")
    max_payload_bytes = whiteboard_board_kafka_max_payload_bytes()
    if len(encoded) > max_payload_bytes:
        raise WhiteboardBoardKafkaDeliveryError(
            f"Kafka payload exceeds WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES ({max_payload_bytes})."
        )
    return encoded


def _headers(payload: dict[str, Any]) -> list[tuple[str, bytes]]:
    return [
        (field, str(payload[field]).encode("utf-8"))
        for field in (
            "event_id",
            "idempotency_key",
            "event_type",
            "schema_version",
            "organization_id",
            "whiteboard_id",
        )
        if payload.get(field) is not None
    ]


def _setting_value(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _setting_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


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


def _raw_size(raw_value: bytes | str | None) -> int:
    if isinstance(raw_value, bytes):
        return len(raw_value)
    if isinstance(raw_value, str):
        return len(raw_value.encode("utf-8"))
    return 0


def _commit_if_supported(consumer: KafkaConsumerLike, message: KafkaMessageLike) -> bool:
    try:
        consumer.commit(message=message, asynchronous=False)
    except AttributeError:
        return True
    except Exception:
        return False
    return True


def _message_topic(message: KafkaMessageLike) -> str:
    try:
        return str(message.topic() or "")
    except Exception:
        return ""


def _message_partition(message: KafkaMessageLike) -> int | None:
    try:
        return int(message.partition())
    except Exception:
        return None


def _message_offset(message: KafkaMessageLike) -> int | None:
    try:
        return int(message.offset())
    except Exception:
        return None


def _compact_consumer_group(value: str) -> str:
    return str(value or "").strip()[:128] or DEFAULT_WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP
