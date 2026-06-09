from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

import pytest
from django.core.cache import cache

from application.services.domain_event_outbox import publish_due_outbox_events
from application.services.whiteboard_board_kafka import (
    WhiteboardBoardKafkaOutboxPublisher,
    build_whiteboard_board_kafka_payload,
    build_whiteboard_board_kafka_readiness_payload,
    consume_whiteboard_board_kafka_events,
    handle_whiteboard_board_kafka_event,
    handle_whiteboard_board_kafka_message,
    whiteboard_board_kafka_config,
    whiteboard_board_kafka_key,
    whiteboard_board_kafka_transport_evidence,
)
from application.services.whiteboard_boards import (
    create_whiteboard_card,
    whiteboard_board_snapshot_key,
)
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    CompanyAccessPolicy,
    CompanyAssignment,
    DepartmentMembership,
    DepartmentRegistry,
    DomainEventOutbox,
    EventDeadLetterRecord,
    Graph,
    Organization,
    OrganizationMembership,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


class _Producer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    def produce(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
        callback: Any | None = None,
    ) -> None:
        if self.fail:
            raise RuntimeError("simulated publish failure")
        self.sent.append({"topic": topic, "key": key, "value": value, "headers": headers or []})
        if callback is not None:
            callback(None, None)

    def flush(self, timeout: float | None = None) -> int:
        _ = timeout
        return 0


class _Message:
    def __init__(
        self,
        value: bytes | str | None,
        *,
        topic: str = "forgegraph.whiteboard.board.events.v1",
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


class _Consumer:
    def __init__(self, messages: list[_Message], *, fail_commit: bool = False) -> None:
        self.messages = messages
        self.fail_commit = fail_commit
        self.committed = 0

    def poll(self, timeout: float | None = None) -> _Message | None:
        _ = timeout
        if not self.messages:
            return None
        return self.messages.pop(0)

    def commit(self, message: object | None = None, *, asynchronous: bool = False) -> None:
        _ = message, asynchronous
        if self.fail_commit:
            raise RuntimeError("commit unavailable")
        self.committed += 1

    def close(self) -> None:
        return


class _TopicMetadata:
    error = None


class _ClusterMetadata:
    def __init__(self, topic: str) -> None:
        self.topics = {topic: _TopicMetadata()}


class _AdminClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def list_topics(self, *, topic: str, timeout: float) -> _ClusterMetadata:
        _ = timeout
        return _ClusterMetadata(topic)


def _user(org: Organization, email: str, role: str = "member") -> User:
    local, _, domain = email.partition("@")
    user = User.objects.create_user(
        email=f"{local}-{uuid4().hex}@{domain or 'example.com'}",
        password="testpassword123",
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User) -> Graph:
    company = cast(
        Graph, Graph.objects.create(owner=owner, organization=org, name="Legacy Eyewear")
    )
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=owner,
        role="member",
        status="active",
    )
    return company


def _department(org: Organization, slug: str, department_type: str = "") -> DepartmentRegistry:
    return DepartmentRegistry.objects.create(
        organization=org,
        slug=slug,
        name=slug.title(),
        department_type=department_type,
    )


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_ONBOARDING,
        client_name=company.name,
        request_type="service_request",
        request_summary="Project command center",
        objective="Coordinate the work",
        created_by=owner,
    )


def _create_card_and_outbox() -> tuple[WorkWhiteboard, TaskRoutingRecord, DomainEventOutbox]:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-kafka-owner@example.com", "owner")
    company = _company(org, owner)
    routing = _department(org, "routing", "routing")
    strategy = _department(org, "strategy")
    DepartmentMembership.objects.create(
        organization=org,
        department=routing,
        user=owner,
        role="lead",
        status="active",
    )
    whiteboard = _whiteboard(company, owner)
    card = create_whiteboard_card(
        user=owner,
        whiteboard=whiteboard,
        department_id=strategy.id,
        title="Kafka card",
        reason="Internal reason must not be published.",
        idempotency_key="kafka-create",
    )
    outbox = DomainEventOutbox.objects.filter(
        event_type="whiteboard.card.created",
        topic="forgegraph.whiteboard.board.events.v1",
    ).latest("created_at")
    return whiteboard, card, outbox


def test_board_kafka_payload_is_versioned_sanitized_and_keyed_by_whiteboard_id() -> None:
    whiteboard, card, outbox = _create_card_and_outbox()

    payload = build_whiteboard_board_kafka_payload(outbox)

    assert whiteboard_board_kafka_key(outbox) == str(whiteboard.id)
    assert payload["schema_version"] == "whiteboard_board_event_v1"
    assert payload["event_type"] == "whiteboard.card.created"
    assert payload["whiteboard_id"] == str(whiteboard.id)
    assert payload["routing_record_id"] == str(card.id)
    payload_text = str(payload).lower()
    assert "internal reason" not in payload_text
    assert "raw_prompt" not in payload_text


def test_board_kafka_publisher_uses_whiteboard_id_partition_key() -> None:
    whiteboard, _card, outbox = _create_card_and_outbox()
    producer = _Producer()
    publisher = WhiteboardBoardKafkaOutboxPublisher(
        producer_factory=lambda _config: producer,
        config={},
        topic="forgegraph.whiteboard.board.events.v1",
    )

    publisher.publish(outbox)

    assert producer.sent[0]["key"] == str(whiteboard.id)
    sent_payload = json.loads(producer.sent[0]["value"].decode("utf-8"))
    assert sent_payload["event_id"] == str(outbox.id)


def test_board_kafka_config_supports_tls_sasl_settings(settings) -> None:
    settings.WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS = "managed.kafka:9092"
    settings.WHITEBOARD_BOARD_KAFKA_CLIENT_ID = "board-client"
    settings.WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    settings.WHITEBOARD_BOARD_KAFKA_SASL_MECHANISM = "PLAIN"
    settings.WHITEBOARD_BOARD_KAFKA_SASL_USERNAME = "atlas-user"
    settings.WHITEBOARD_BOARD_KAFKA_SASL_PASSWORD = "atlas-secret"

    config = whiteboard_board_kafka_config()

    assert config["bootstrap.servers"] == "managed.kafka:9092"
    assert config["client.id"] == "board-client"
    assert config["security.protocol"] == "SASL_SSL"
    assert config["sasl.mechanism"] == "PLAIN"
    assert config["sasl.username"] == "atlas-user"
    assert config["sasl.password"] == "atlas-secret"


def test_board_kafka_readiness_reports_admin_metadata_and_backlog(settings) -> None:
    settings.WHITEBOARD_BOARD_KAFKA_ENABLED = True
    settings.WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS = "managed.kafka:9092"
    settings.WHITEBOARD_BOARD_KAFKA_TOPIC = "forgegraph.whiteboard.board.events.v1"
    settings.WHITEBOARD_BOARD_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD = 1000
    _whiteboard, _card, _outbox = _create_card_and_outbox()

    payload = build_whiteboard_board_kafka_readiness_payload(admin_client_factory=_AdminClient)

    assert payload["ready"] is True
    assert payload["broker_ready"] is True
    assert payload["topic_ready"] is True
    assert payload["backlog"] == 1
    assert payload["backlog_ready"] is True


def test_board_kafka_consumer_records_receipts_and_refreshes_redis_without_mutating_db_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.clear()
    monkeypatch.setattr(
        "application.services.whiteboard_boards._use_cache_snapshot_store", lambda: True
    )
    whiteboard, card, outbox = _create_card_and_outbox()
    payload = build_whiteboard_board_kafka_payload(outbox)
    payload["new_status"] = "completed"

    result = handle_whiteboard_board_kafka_event(payload, consumer_group="board-test")
    duplicate = handle_whiteboard_board_kafka_event(payload, consumer_group="board-test")
    card.refresh_from_db()

    assert result.handled is True
    assert duplicate.duplicate is True
    assert CommunicationEventReceipt.objects.filter(consumer_group="board-test").count() == 1
    assert cache.get(whiteboard_board_snapshot_key(whiteboard))
    assert card.status == "queued"


def test_board_kafka_transport_evidence_is_observability_only(
    monkeypatch: pytest.MonkeyPatch,
    settings,
) -> None:
    cache.clear()
    settings.WHITEBOARD_BOARD_KAFKA_ENABLED = True
    settings.WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP = "board-evidence"
    monkeypatch.setattr(
        "application.services.whiteboard_boards._use_cache_snapshot_store", lambda: True
    )
    whiteboard, card, outbox = _create_card_and_outbox()
    payload = build_whiteboard_board_kafka_payload(outbox)
    payload["new_status"] = "completed"

    result = handle_whiteboard_board_kafka_event(payload, consumer_group="board-evidence")
    card.refresh_from_db()
    evidence = whiteboard_board_kafka_transport_evidence(
        organization=whiteboard.organization,
        whiteboard_id=str(whiteboard.id),
        company_id=str(whiteboard.company_id),
    )

    assert result.handled is True
    assert evidence["authoritative_state_source"] == "backend_db"
    assert evidence["outbox"]["pending"] == 1
    assert evidence["receipts"]["handled"] == 1
    assert evidence["dead_letters"]["active_count"] == 0
    assert card.status == "queued"


def test_board_kafka_commit_loss_retry_reuses_receipt_without_mutating_db_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.clear()
    monkeypatch.setattr(
        "application.services.whiteboard_boards._use_cache_snapshot_store", lambda: True
    )
    whiteboard, card, outbox = _create_card_and_outbox()
    payload = build_whiteboard_board_kafka_payload(outbox)
    payload["new_status"] = "completed"
    encoded = json.dumps(payload).encode("utf-8")
    first_consumer = _Consumer([_Message(encoded, partition=3, offset=14)], fail_commit=True)

    first = consume_whiteboard_board_kafka_events(
        consumer=first_consumer,
        consumer_group="board-commit-loss",
        limit=1,
        poll_timeout_seconds=0.1,
    )
    second_consumer = _Consumer([_Message(encoded, partition=3, offset=14)])
    second = consume_whiteboard_board_kafka_events(
        consumer=second_consumer,
        consumer_group="board-commit-loss",
        limit=1,
        poll_timeout_seconds=0.1,
    )
    card.refresh_from_db()

    assert first.handled == 1
    assert first.commit_failed == 1
    assert first_consumer.committed == 0
    assert second.duplicates == 1
    assert second_consumer.committed == 1
    assert CommunicationEventReceipt.objects.filter(consumer_group="board-commit-loss").count() == 1
    assert cache.get(whiteboard_board_snapshot_key(whiteboard))
    assert card.status == "queued"


def test_board_kafka_consumer_ignores_unknown_schema_or_event_and_fails_malformed_payloads() -> (
    None
):
    _whiteboard, _card, outbox = _create_card_and_outbox()
    payload = build_whiteboard_board_kafka_payload(outbox)
    bad_schema = dict(
        payload, event_id="11111111-1111-1111-1111-111111111111", schema_version="future_v9"
    )
    bad_event = dict(
        payload,
        event_id="22222222-2222-2222-2222-222222222222",
        event_type="whiteboard.card.future",
    )
    missing = dict(payload, event_id="33333333-3333-3333-3333-333333333333")
    missing.pop("whiteboard_id")

    ignored_schema = handle_whiteboard_board_kafka_event(bad_schema, consumer_group="board-schema")
    ignored_event = handle_whiteboard_board_kafka_event(bad_event, consumer_group="board-event")
    failed_missing = handle_whiteboard_board_kafka_event(missing, consumer_group="board-missing")
    failed_json = handle_whiteboard_board_kafka_message(
        "{bad json", consumer_group="board-json", topic="topic", partition=0, offset=1
    )

    assert ignored_schema.ignored is True
    assert ignored_event.ignored is True
    assert failed_missing.failed is True
    assert failed_json.failed is True
    assert (
        EventDeadLetterRecord.objects.filter(source="whiteboard_board_kafka_consumer").count() >= 2
    )


def test_board_kafka_publish_failure_does_not_rollback_card_or_outbox_state() -> None:
    _whiteboard, card, outbox = _create_card_and_outbox()
    producer = _Producer(fail=True)
    publisher = WhiteboardBoardKafkaOutboxPublisher(
        producer_factory=lambda _config: producer,
        config={},
        topic="forgegraph.whiteboard.board.events.v1",
    )

    result = publish_due_outbox_events(
        publisher=publisher,
        limit=10,
        topic="forgegraph.whiteboard.board.events.v1",
    )
    outbox.refresh_from_db()

    assert TaskRoutingRecord.objects.filter(id=card.id).exists()
    assert result.failed == 1
    assert outbox.status == "failed"
