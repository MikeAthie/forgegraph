from __future__ import annotations

from typing import cast

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from application.services.communications import (
    CommunicationError,
    assert_interaction_event_record_not_suitable,
    create_message,
    create_thread,
    get_thread_for_user,
    message_payload,
    redact_message,
)
from infrastructure.orm.models import (
    AgentRegistryEntry,
    Asset,
    CommunicationMessage,
    CommunicationThread,
    CompanyAccessPolicy,
    CompanyAssignment,
    DomainEvent,
    DomainEventOutbox,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    Run,
    ToolExecution,
    User,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str) -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, name: str) -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    return company


def _assign(org: Organization, company: Graph, user: User, role: str) -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _run_for_company(user: User, company: Graph) -> Run:
    version_number = (
        GraphVersion.objects.filter(graph=company).aggregate(max_version=Max("version"))[
            "max_version"
        ]
        or 0
    ) + 1
    version = GraphVersion.objects.create(
        graph=company,
        version=version_number,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        organization=required_company_organization(company),
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )


def _agent_for_company(company: Graph, slug: str) -> AgentRegistryEntry:
    return AgentRegistryEntry.objects.create(
        organization=required_company_organization(company),
        slug=slug,
        display_name=f"{slug} agent",
        source_workflow=company,
        source_node_id=slug,
    )


def _setup():
    org = Organization.objects.create(name="ATLAS")
    operator = _user(org, "atlas@example.com", "owner")
    customer = _user(org, "legacy@example.com", "viewer")
    other_user = _user(org, "other@example.com", "viewer")
    legacy = _company(org, operator, "Legacy Eyewear")
    other = _company(org, operator, "Other Client")
    _assign(org, legacy, customer, "viewer")
    _assign(org, legacy, operator, "member")
    _assign(org, other, other_user, "viewer")
    return org, operator, customer, other_user, legacy, other


def test_interaction_event_record_is_not_a_communication_thread() -> None:
    note = assert_interaction_event_record_not_suitable()

    assert "operating-brief mutation history" in note
    assert "visibility" in note
    assert "attachments" in note


def test_thread_source_key_and_message_idempotency_constraints() -> None:
    _org, operator, _customer, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={
            "title": "Legacy consult",
            "thread_type": "service_engagement",
            "visibility_mode": "mixed",
            "source_key": "service_engagement:legacy:primary",
        },
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        CommunicationThread.objects.create(
            organization=legacy.organization,
            company=legacy,
            title="Duplicate",
            thread_type="service_engagement",
            visibility_mode="mixed",
            source_key="service_engagement:legacy:primary",
            created_by_user=operator,
        )

    create_message(
        thread=thread,
        sender_user=operator,
        message_kind="note",
        body="First",
        visibility="customer",
        idempotency_key="same-message",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CommunicationMessage.objects.create(
            thread=thread,
            organization=legacy.organization,
            company=legacy,
            sender_kind="user",
            sender_user=operator,
            message_kind="note",
            body="Duplicate",
            visibility="customer",
            idempotency_key="same-message",
        )


def test_message_visibility_filters_customer_operator_and_other_client() -> None:
    _org, operator, customer, other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    create_message(
        thread=thread,
        sender_user=customer,
        message_kind="request",
        body="Can you explain why WhatsApp is recommended if the connector is missing?",
        body_format="markdown",
        visibility="customer",
        idempotency_key="legacy-question",
    )
    create_message(
        thread=thread,
        sender_user=operator,
        message_kind="agent_observation",
        body="Execution remains blocked until WhatsApp provider is configured.",
        visibility="internal",
        idempotency_key="operator-internal",
    )

    customer_payloads = [
        message_payload(message, user=customer)
        for message in thread.messages.order_by("created_at")
    ]
    operator_payloads = [
        message_payload(message, user=operator)
        for message in thread.messages.order_by("created_at")
    ]
    visible_to_customer = [item for item in customer_payloads if item["visibility"] == "customer"]

    assert len(visible_to_customer) == 1
    assert len(operator_payloads) == 2
    assert get_thread_for_user(user=other_user, thread_id=thread.id) is None


def test_service_sender_messages_require_scoped_backend_context() -> None:
    _org, operator, _customer, _other_user, legacy, other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    legacy_agent = _agent_for_company(legacy, "legacy-consult")
    other_agent = _agent_for_company(other, "other-client")
    wrong_org = Organization.objects.create(name="Unrelated Operator")

    with pytest.raises(CommunicationError, match="sender_organization"):
        create_message(
            thread=thread,
            sender_kind="system",
            message_kind="agent_observation",
            body="Missing provider.",
            visibility="internal",
            idempotency_key="system-missing-org",
        )

    with pytest.raises(CommunicationError, match="matching the thread organization"):
        create_message(
            thread=thread,
            sender_kind="system",
            sender_organization=wrong_org,
            message_kind="agent_observation",
            body="Wrong org.",
            visibility="internal",
            idempotency_key="system-wrong-org",
        )

    system_message = create_message(
        thread=thread,
        sender_kind="system",
        sender_organization=legacy.organization,
        message_kind="agent_observation",
        body="Execution remains blocked until WhatsApp provider is configured.",
        visibility="internal",
        idempotency_key="system-scoped",
    )

    with pytest.raises(CommunicationError, match="thread company"):
        create_message(
            thread=thread,
            sender_kind="agent",
            sender_agent=other_agent,
            message_kind="agent_observation",
            body="Wrong company agent.",
            visibility="internal",
            idempotency_key="agent-wrong-company",
        )

    agent_message = create_message(
        thread=thread,
        sender_kind="agent",
        sender_agent=legacy_agent,
        message_kind="agent_observation",
        body="Agent-scoped note.",
        visibility="internal",
        idempotency_key="agent-scoped",
    )

    assert system_message.sender_organization_id == legacy.organization_id
    assert agent_message.sender_agent_id == legacy_agent.id


def test_visible_message_does_not_leak_internal_attachment_to_customer() -> None:
    _org, operator, customer, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    run = _run_for_company(operator, legacy)
    tool_execution = ToolExecution.objects.create(
        run=run,
        node_id="notify",
        attempt_id="attempt-1",
        tool_name="whatsapp",
        idempotency_key="tool-whatsapp",
        status="succeeded",
    )
    message = create_message(
        thread=thread,
        sender_user=operator,
        message_kind="tool_result_summary",
        body="Tool result is attached.",
        visibility="customer",
        idempotency_key="tool-message",
        attachments=[{"type": "tool_execution", "id": tool_execution.id}],
    )

    customer_payload = message_payload(message, user=customer)
    operator_payload = message_payload(message, user=operator)

    assert customer_payload["attachments"] == []
    assert operator_payload["attachments"][0]["type"] == "tool_execution"
    assert "tool_name" not in operator_payload["attachments"][0]


def test_domain_event_payload_is_body_free_and_sanitized() -> None:
    _org, operator, _customer, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )

    message = create_message(
        thread=thread,
        sender_user=operator,
        message_kind="note",
        body="Sensitive body must not be in events.",
        visibility="customer",
        idempotency_key="event-safe-message",
        metadata={
            "private_config": {"provider": "hidden"},
            "raw_prompt": "hidden prompt",
            "evidence_bundle": ["hidden"],
            "debug_trace": "hidden",
            "safe": "ok",
        },
    )

    event = DomainEvent.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )

    payload_text = str(event.payload)
    assert "Sensitive body" not in payload_text
    assert "hidden prompt" not in payload_text
    assert "private_config" not in payload_text
    assert "evidence_bundle" not in payload_text
    assert "debug_trace" not in payload_text
    assert event.payload["message_id"] == str(message.id)
    assert event.payload["visibility"] == "customer"

    outbox = DomainEventOutbox.objects.get(domain_event=event)
    outbox_payload_text = str(outbox.payload_json)
    assert outbox.topic == "forgegraph.communication.events.v1"
    assert outbox.status == "pending"
    assert "Sensitive body" not in outbox_payload_text
    assert "hidden prompt" not in outbox_payload_text
    assert "private_config" not in outbox_payload_text
    assert "evidence_bundle" not in outbox_payload_text
    assert "debug_trace" not in outbox_payload_text
    assert outbox.payload_json["message_id"] == str(message.id)


def test_communication_outbox_rolls_back_with_message_transaction() -> None:
    _org, operator, _customer, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    message_id = None

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            message = create_message(
                thread=thread,
                sender_user=operator,
                message_kind="note",
                body="This committed state should roll back.",
                visibility="customer",
                idempotency_key="rollback-message",
            )
            message_id = message.id
            assert DomainEventOutbox.objects.filter(
                payload_json__message_id=str(message.id)
            ).exists()
            raise RuntimeError("rollback")

    assert message_id is not None
    assert not CommunicationMessage.objects.filter(id=message_id).exists()
    assert not DomainEvent.objects.filter(
        idempotency_key=f"communication-message:{message_id}:created",
    ).exists()
    assert not DomainEventOutbox.objects.filter(payload_json__message_id=str(message_id)).exists()


def test_redact_message_preserves_row_and_hides_body() -> None:
    _org, operator, _customer, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    message = create_message(
        thread=thread,
        sender_user=operator,
        message_kind="note",
        body="Remove this body.",
        visibility="customer",
        idempotency_key="redact-me",
    )

    redacted = redact_message(user=operator, message=message, reason="contains sensitive data")
    payload = message_payload(redacted, user=operator)

    assert redacted.id == message.id
    assert redacted.redacted_at is not None
    assert payload["body"] == ""
    assert payload["redacted"] is True
    assert DomainEvent.objects.filter(
        event_type="communication.message.redacted",
        aggregate_id=message.id,
    ).exists()


def test_wrong_company_attachment_scope_is_rejected() -> None:
    _org, operator, _customer, _other_user, legacy, other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    create_message(
        thread=thread,
        sender_user=operator,
        message_kind="note",
        body="Attach report.",
        visibility="customer",
        idempotency_key="attach-message",
    )
    wrong_asset = Asset.objects.create(
        organization=other.organization,
        company=other,
        title="Other client asset",
        asset_type="document",
        created_by_type="system",
    )

    with pytest.raises(CommunicationError, match="different company"):
        create_message(
            thread=thread,
            sender_user=operator,
            message_kind="note",
            body="Wrong attachment.",
            visibility="customer",
            idempotency_key="wrong-attachment",
            attachments=[{"type": "artifact", "id": wrong_asset.id}],
        )
