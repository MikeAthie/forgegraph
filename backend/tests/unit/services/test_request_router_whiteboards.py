from __future__ import annotations

from typing import cast

import pytest
from django.core.cache import cache

from application.services.communications import create_message, create_thread
from application.services.request_router import classify_and_route_request, classify_request
from application.services.work_whiteboards import (
    rebuild_whiteboard_snapshot_from_db,
    update_whiteboard_field,
    whiteboard_payload,
)
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    Organization,
    OrganizationMembership,
    RequestClassificationRecord,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
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


def _assign(org: Organization, company: Graph, user: User, role: str = "member") -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _message(company: Graph, sender: User, *, body: str, key: str = "request-message"):
    thread = create_thread(
        company=company,
        user=sender,
        data={
            "title": "Legacy consult",
            "thread_type": "support",
            "visibility_mode": "mixed",
            "source_key": f"request-router:{company.id}:{key}",
        },
    )
    return create_message(
        thread=thread,
        sender_user=sender,
        message_kind="request",
        body=body,
        visibility="customer",
        idempotency_key=f"{key}:{company.id}",
        metadata={},
    )


def test_new_request_creates_classification_whiteboard_and_onboarding_tasks() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-owner@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner)
    message = _message(
        company,
        owner,
        body="Please create a new campaign to launch DEPP GOLD on WhatsApp with a $5000 budget next week.",
    )

    classification, whiteboard, records = classify_and_route_request(message=message)

    assert classification.classification == RequestClassificationRecord.CLASS_NEW
    assert whiteboard is not None
    assert whiteboard.company_id == company.id
    assert whiteboard.status == WorkWhiteboard.STATUS_ONBOARDING
    assert whiteboard.budget_limit == "$5000"
    assert "whatsapp" in whiteboard.channel_context_json["requested_channels"]
    assert records
    assert TaskRoutingRecord.objects.filter(
        metadata_json__whiteboard_id=str(whiteboard.id)
    ).count() == len(records)
    assert all(record.communication_message_id == message.id for record in records)


def test_existing_request_resumes_active_whiteboard_without_duplicate_tasks() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-existing@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner)
    first_message = _message(
        company, owner, body="Create a new launch campaign for eyewear.", key="first"
    )
    _classification, whiteboard, _records = classify_and_route_request(message=first_message)
    assert whiteboard is not None
    second_message = create_message(
        thread=first_message.thread,
        sender_user=owner,
        message_kind="request",
        body="This should use the existing request.",
        visibility="customer",
        idempotency_key="second-existing",
        metadata={},
    )

    classification = classify_request(message=second_message)
    _classification, resumed, records = classify_and_route_request(message=second_message)

    assert classification.classification == RequestClassificationRecord.CLASS_EXISTING
    assert resumed is not None
    assert resumed.id == whiteboard.id
    assert records == []


def test_ambiguous_request_routes_clarification_to_account_intake() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-ambiguous@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner)
    message = _message(company, owner, body="Can you handle this?", key="ambiguous")

    classification, whiteboard, records = classify_and_route_request(message=message)

    assert classification.classification == RequestClassificationRecord.CLASS_AMBIGUOUS
    assert whiteboard is None
    assert len(records) == 1
    assert records[0].to_department.slug == "account-intake"
    assert records[0].status == "queued"


def test_duplicate_request_event_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-idempotent@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner)
    message = _message(
        company, owner, body="Launch a new email campaign for the spring frame drop.", key="idem"
    )

    first_classification, first_whiteboard, first_records = classify_and_route_request(
        message=message,
        idempotency_key="request-router:duplicate",
    )
    second_classification, second_whiteboard, second_records = classify_and_route_request(
        message=message,
        idempotency_key="request-router:duplicate",
    )

    assert first_classification.id == second_classification.id
    assert first_whiteboard is not None and second_whiteboard is not None
    assert first_whiteboard.id == second_whiteboard.id
    assert {record.id for record in first_records} == {record.id for record in second_records}
    assert WorkWhiteboard.objects.count() == 1


def test_whiteboard_completion_updates_and_snapshot_rebuilds_from_db() -> None:
    cache.clear()
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-snapshot@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner)
    message = _message(
        company, owner, body="Create a new campaign for DEPP GOLD on email.", key="snapshot"
    )
    _classification, whiteboard, _records = classify_and_route_request(message=message)
    assert whiteboard is not None
    before = whiteboard.completion_score

    updated = update_whiteboard_field(
        user=owner,
        whiteboard=whiteboard,
        fields={
            "objective": "Sell launch inventory.",
            "target_audience": {"segment": "premium eyewear shoppers"},
            "brand_context": {"brand_voice": "confident"},
            "constraints": {
                "visual_constraints": "gold product shots",
                "legal": "no medical claims",
            },
            "known_facts": {
                "approval_owner": "Dana",
                "success_metrics": "qualified consult bookings",
                "inventory": "120 units",
            },
            "channel_context": {"connectors": ["email"]},
        },
    )
    snapshot = rebuild_whiteboard_snapshot_from_db(updated.id)

    assert updated.completion_score > before
    assert "objective" not in updated.missing_fields_json
    assert snapshot is not None
    assert snapshot["id"] == str(updated.id)


def test_customer_payload_hides_internal_assumptions_and_routing() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "router-internal-owner@example.com", "owner")
    customer = _user(org, "router-customer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    message = _message(company, owner, body="Create a new campaign for DEPP GOLD.", key="payload")
    _classification, whiteboard, _records = classify_and_route_request(message=message)
    assert whiteboard is not None
    whiteboard.assumptions_json = ["Internal market assumption"]
    whiteboard.save(update_fields=["assumptions_json", "updated_at"])

    customer_payload = whiteboard_payload(whiteboard, user=customer)
    operator_payload = whiteboard_payload(whiteboard, user=owner)

    assert "assumptions" not in customer_payload
    assert "routing_records" not in customer_payload
    assert operator_payload["assumptions"] == ["Internal market assumption"]
    assert operator_payload["routing_records"]
