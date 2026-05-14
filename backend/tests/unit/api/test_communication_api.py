from __future__ import annotations

from typing import cast

import pytest
from django.test import override_settings

from application.services.communications import create_message, create_thread
from infrastructure.orm.models import (
    Asset,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanySignal,
    Graph,
    Organization,
    OrganizationMembership,
    User,
)

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


def _setup():
    org = Organization.objects.create(name="ATLAS")
    operator = _user(org, "atlas-api@example.com", "owner")
    legacy_owner = _user(org, "legacy-api@example.com", "viewer")
    other_user = _user(org, "other-api@example.com", "viewer")
    legacy = _company(org, operator, "Legacy Eyewear")
    other = _company(org, operator, "Other Client")
    _assign(org, legacy, operator, "member")
    _assign(org, legacy, legacy_owner, "viewer")
    _assign(org, other, other_user, "viewer")
    return operator, legacy_owner, other_user, legacy, other


def test_communication_routes_can_be_disabled(api_client) -> None:
    operator, _legacy_owner, _other_user, legacy, _other = _setup()
    api_client.force_authenticate(user=operator)

    with override_settings(COMMUNICATION_ENABLED=False):
        response = api_client.get(
            "/api/communication/threads",
            data={"company_id": str(legacy.id)},
        )

    assert response.status_code == 404


def test_messages_are_filtered_by_visibility_and_company(api_client) -> None:
    operator, legacy_owner, other_user, legacy, _other = _setup()
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
    create_message(
        thread=thread,
        sender_user=legacy_owner,
        message_kind="request",
        body="Can you explain why WhatsApp is recommended if the connector is missing?",
        visibility="customer",
        idempotency_key="legacy-question-api",
    )
    create_message(
        thread=thread,
        sender_user=operator,
        message_kind="agent_observation",
        body="Execution remains blocked until WhatsApp provider is configured.",
        visibility="internal",
        idempotency_key="legacy-internal-api",
    )

    api_client.force_authenticate(user=legacy_owner)
    customer_response = api_client.get(f"/api/communication/threads/{thread.id}/messages")
    api_client.force_authenticate(user=operator)
    operator_response = api_client.get(f"/api/communication/threads/{thread.id}/messages")
    api_client.force_authenticate(user=other_user)
    other_response = api_client.get(f"/api/communication/threads/{thread.id}")

    assert customer_response.status_code == 200
    customer_messages = customer_response.json()["data"]["messages"]
    assert [message["visibility"] for message in customer_messages] == ["customer"]
    assert "WhatsApp" in customer_messages[0]["body"]

    assert operator_response.status_code == 200
    operator_messages = operator_response.json()["data"]["messages"]
    assert [message["visibility"] for message in operator_messages] == ["customer", "internal"]

    assert other_response.status_code == 404


def test_atlas_legacy_canonical_communication_visibility(api_client) -> None:
    operator, legacy_owner, other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={
            "title": "Legacy consult",
            "thread_type": "service_engagement",
            "visibility_mode": "mixed",
            "source_key": "service_engagement:legacy:communication",
        },
    )
    missing_capability_signal = CompanySignal.objects.create(
        organization=legacy.organization,
        company=legacy,
        created_by=operator,
        signal_type="manual",
        status="new",
        source="communication",
        external_key="legacy-whatsapp-provider-missing",
        title="WhatsApp provider capability missing",
        summary="Execution remains blocked until WhatsApp/Twilio/Brevo provider capability is configured.",
        channel="whatsapp",
    )

    api_client.force_authenticate(user=legacy_owner)
    question = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={
            "message_kind": "request",
            "body": "Can you explain why WhatsApp is recommended if the connector is missing?",
            "visibility": "customer",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="legacy-whatsapp-question",
    )
    assert question.status_code == 201

    api_client.force_authenticate(user=operator)
    reply = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={
            "message_kind": "response",
            "body": (
                "WhatsApp is recommended as a manual first step. Automation requires "
                "connecting a WhatsApp/Twilio/Brevo capability."
            ),
            "visibility": "customer",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-whatsapp-reply",
    )
    assert reply.status_code == 201

    internal_message = create_message(
        thread=thread,
        sender_kind="system",
        sender_organization=legacy.organization,
        message_kind="agent_observation",
        body=(
            "Execution remains blocked until WhatsApp provider is configured. "
            "Keep missing-capability recommendation open."
        ),
        visibility="internal",
        idempotency_key="atlas-system-missing-capability-note",
        attachments=[{"type": "company_signal", "id": str(missing_capability_signal.id)}],
    )

    api_client.force_authenticate(user=legacy_owner)
    legacy_messages_response = api_client.get(f"/api/communication/threads/{thread.id}/messages")
    api_client.force_authenticate(user=operator)
    atlas_messages_response = api_client.get(f"/api/communication/threads/{thread.id}/messages")
    api_client.force_authenticate(user=other_user)
    other_thread_response = api_client.get(f"/api/communication/threads/{thread.id}")
    other_threads_response = api_client.get(
        "/api/communication/threads",
        data={"company_id": str(legacy.id)},
    )

    assert legacy_messages_response.status_code == 200
    legacy_messages = legacy_messages_response.json()["data"]["messages"]
    assert [message["id"] for message in legacy_messages] == [
        question.json()["data"]["message"]["id"],
        reply.json()["data"]["message"]["id"],
    ]
    assert all(message["visibility"] == "customer" for message in legacy_messages)
    assert "Execution remains blocked" not in str(legacy_messages)

    assert atlas_messages_response.status_code == 200
    atlas_messages = atlas_messages_response.json()["data"]["messages"]
    assert [message["visibility"] for message in atlas_messages] == [
        "customer",
        "customer",
        "internal",
    ]
    internal_payload = next(message for message in atlas_messages if message["id"] == str(internal_message.id))
    assert "Execution remains blocked" in internal_payload["body"]
    assert internal_payload["attachments"] == [
        {
            "id": internal_payload["attachments"][0]["id"],
            "message_id": str(internal_message.id),
            "type": "company_signal",
            "target_id": str(missing_capability_signal.id),
            "metadata": {},
            "created_at": internal_payload["attachments"][0]["created_at"],
        }
    ]

    assert other_thread_response.status_code == 404
    assert other_threads_response.status_code == 200
    assert other_threads_response.json()["data"]["threads"] == []


def test_customer_cannot_create_internal_message_but_operator_can(api_client) -> None:
    operator, legacy_owner, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )

    api_client.force_authenticate(user=legacy_owner)
    denied = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={
            "message_kind": "note",
            "body": "Internal escalation",
            "visibility": "internal",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="customer-internal-denied",
    )

    api_client.force_authenticate(user=operator)
    allowed = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={
            "message_kind": "agent_observation",
            "body": "Execution remains blocked until WhatsApp provider is configured.",
            "visibility": "internal",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="operator-internal-allowed",
    )

    assert denied.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["data"]["message"]["visibility"] == "internal"


def test_message_create_idempotency_and_conflict(api_client) -> None:
    operator, legacy_owner, _other_user, legacy, _other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    api_client.force_authenticate(user=legacy_owner)

    first = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={"message_kind": "request", "body": "Question", "visibility": "customer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="same-message-key",
    )
    replay = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={"message_kind": "request", "body": "Question", "visibility": "customer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="same-message-key",
    )
    conflict = api_client.post(
        f"/api/communication/threads/{thread.id}/messages",
        data={"message_kind": "request", "body": "Changed question", "visibility": "customer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="same-message-key",
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["data"]["message"]["id"] == first.json()["data"]["message"]["id"]
    assert replay.json()["data"]["already_applied"] is True
    assert conflict.status_code == 409


def test_wrong_company_attachment_is_not_found(api_client) -> None:
    operator, _legacy_owner, _other_user, legacy, other = _setup()
    thread = create_thread(
        company=legacy,
        user=operator,
        data={"title": "Legacy consult", "visibility_mode": "mixed"},
    )
    message = create_message(
        thread=thread,
        sender_user=operator,
        message_kind="note",
        body="Attach a customer-visible output.",
        visibility="customer",
        idempotency_key="attachment-api-message",
    )
    wrong_asset = Asset.objects.create(
        organization=other.organization,
        company=other,
        title="Other client artifact",
        asset_type="document",
        created_by_type="system",
    )

    api_client.force_authenticate(user=operator)
    response = api_client.post(
        f"/api/communication/messages/{message.id}/attachments",
        data={"attachments": [{"type": "artifact", "id": str(wrong_asset.id)}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="wrong-company-attachment",
    )

    assert response.status_code == 404
