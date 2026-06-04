from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from application.services import service_engagement_snapshots as snapshots
from application.services.agency_growth_signals import build_agency_growth_signals
from application.services.service_engagement_snapshots import (
    record_service_engagement_business_snapshot,
    service_engagement_business_snapshot_payload,
)
from application.services.service_engagements import ServiceEngagementError
from infrastructure.orm.models import (
    AuditLog,
    DomainEvent,
    DomainEventOutbox,
    Graph,
    Organization,
    OrganizationMembership,
    ProcessedCommand,
    ServiceCatalogItem,
    ServiceEngagement,
    ServiceEngagementBusinessSnapshot,
    User,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str = "atlas-profitability@example.com") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role="owner", is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Atlas SLA Client") -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=owner,
            organization=org,
            name=name,
            description="Digital marketing agency client.",
        ),
    )


def _engagement(company: Graph, user: User) -> ServiceEngagement:
    org = company.organization
    assert org is not None
    catalog = ServiceCatalogItem.objects.create(
        organization=org,
        slug="digital-marketing-agency-engagement",
        title="Digital Marketing Agency Engagement",
        status="active",
        visibility="customer",
    )
    return ServiceEngagement.objects.create(
        organization=org,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        public_summary="Monthly launch and optimization support.",
        requested_by=user,
    )


def _snapshot_payload() -> dict[str, object]:
    return {
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "economics": {
            "revenue": {"amount": "10000.00", "currency": "USD"},
            "delivery_cost": {"amount": "6200.00", "currency": "USD"},
            "pass_through_cost": {"amount": "800.00", "currency": "USD"},
            "tooling_cost": {"amount": "0.00", "currency": "USD"},
        },
        "scope": {
            "unit": "deliverable",
            "included_units": 10,
            "used_units": 12,
            "overage_alert_threshold": "0.80",
        },
        "sla": {
            "target_hours": "48.0",
            "elapsed_hours": "50.0",
            "breach_count": 1,
            "breaches": [
                {
                    "code": "first_response_late",
                    "summary": "First response exceeded the client SLA.",
                    "secret_token": "should-not-render",
                }
            ],
        },
        "metadata": {
            "source": "operator_plan",
            "api_key": "sk_live_should_not_persist",
            "connector_readiness": {"email": {"status": "ready"}},
        },
    }


def test_business_snapshot_computes_profit_scope_and_sla_without_leaking_secrets() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org)
    company = _company(org, owner)
    engagement = _engagement(company, owner)

    snapshot = record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=owner,
        data=_snapshot_payload(),
        idempotency_key="profitability-sla-snapshot-1",
    )

    assert snapshot.organization == org
    assert snapshot.company == company
    assert snapshot.engagement == engagement
    assert snapshot.currency == "USD"
    assert snapshot.revenue_amount == Decimal("10000.00")
    assert snapshot.delivery_cost_amount == Decimal("6200.00")
    assert snapshot.pass_through_cost_amount == Decimal("800.00")
    assert snapshot.gross_margin_amount == Decimal("3000.00")
    assert snapshot.gross_margin_percent == Decimal("30.00")
    assert snapshot.profitability_band == "healthy"
    assert snapshot.scope_included_units == 10
    assert snapshot.scope_used_units == 12
    assert snapshot.scope_overage_units == 2
    assert snapshot.scope_utilization_percent == Decimal("120.00")
    assert snapshot.scope_status == "over_limit"
    assert snapshot.sla_status == "breached"
    assert snapshot.sla_breach_count == 1

    operator_payload = service_engagement_business_snapshot_payload(
        snapshot,
        include_internal=True,
    )
    client_payload = service_engagement_business_snapshot_payload(snapshot)

    assert operator_payload["profitability"]["band"] == "healthy"
    assert operator_payload["profitability"]["gross_margin_percent"] == "30.00"
    assert operator_payload["economics"]["delivery_cost"]["amount"] == "6200.00"
    assert client_payload["economics"] == {
        "revenue": {"amount": "10000.00", "currency": "USD"}
    }
    assert "profitability" not in client_payload
    assert "delivery_cost" not in client_payload["economics"]
    assert client_payload["scope"]["status"] == "over_limit"
    assert client_payload["sla"]["status"] == "breached"

    rendered = json.dumps(
        {
            "model": snapshot.snapshot_json,
            "operator": operator_payload,
            "client": client_payload,
        },
        sort_keys=True,
        default=str,
    )
    assert "sk_live_should_not_persist" not in rendered
    assert "should-not-render" not in rendered
    assert "api_key" not in rendered
    assert "secret_token" not in rendered
    assert "connector_readiness" not in rendered

    audit = AuditLog.objects.get(action="service_engagement.business_snapshot_recorded")
    assert audit.tenant_id == org.id
    assert audit.resource_type == "service_engagement_business_snapshot"
    assert audit.resource_id == str(snapshot.id)
    assert audit.metadata["company_id"] == str(company.id)
    assert audit.metadata["engagement_id"] == str(engagement.id)

    event = DomainEvent.objects.get(event_type="service_engagement.business_snapshot_recorded")
    outbox = DomainEventOutbox.objects.get(domain_event=event)
    assert event.organization == org
    assert event.aggregate_type == "service_engagement_business_snapshot"
    assert event.aggregate_id == snapshot.id
    assert outbox.company == company
    assert outbox.topic == "forgegraph.service_engagements.events.v1"
    event_text = json.dumps(
        {"event": event.payload, "outbox": outbox.payload_json},
        sort_keys=True,
        default=str,
    )
    assert "sk_live_should_not_persist" not in event_text
    assert "connector_readiness" not in event_text


def test_business_snapshot_mutation_is_service_idempotent_and_conflicts_on_body_change() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-profit-idempotent@example.com")
    company = _company(org, owner)
    engagement = _engagement(company, owner)
    payload = _snapshot_payload()

    first = record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=owner,
        data=payload,
        idempotency_key="profitability-sla-replay",
    )
    second = record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=owner,
        data=payload,
        idempotency_key="profitability-sla-replay",
    )

    assert second.id == first.id
    assert first._idempotency_status == "applied"
    assert second._idempotency_status == "already_applied"
    assert ServiceEngagementBusinessSnapshot.objects.count() == 1
    assert AuditLog.objects.filter(action="service_engagement.business_snapshot_recorded").count() == 1
    assert (
        DomainEvent.objects.filter(
            event_type="service_engagement.business_snapshot_recorded"
        ).count()
        == 1
    )

    changed = _snapshot_payload()
    changed["scope"] = {"included_units": 10, "used_units": 8}
    with pytest.raises(ServiceEngagementError) as exc_info:
        record_service_engagement_business_snapshot(
            engagement=engagement,
            actor=owner,
            data=changed,
            idempotency_key="profitability-sla-replay",
        )
    assert exc_info.value.code == "idempotency_conflict"


def test_api_records_business_snapshot_idempotently_and_scopes_to_company() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-profit-api@example.com")
    company = _company(org, owner)
    engagement = _engagement(company, owner)
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("service-engagement-business-snapshots", kwargs={"engagement_id": engagement.id})
    payload = _snapshot_payload()

    first = client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="api-profitability-key")
    second = client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="api-profitability-key")
    conflict = client.post(
        url,
        {**payload, "scope": {"included_units": 10, "used_units": 8}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-profitability-key",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert conflict.status_code == 409
    assert first.data["data"]["idempotency"]["status"] == "applied"
    assert second.data["data"]["idempotency"]["status"] == "already_applied"
    assert conflict.data["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert first.data["data"]["snapshot"]["id"] == second.data["data"]["snapshot"]["id"]
    assert first.data["data"]["snapshot"]["profitability"]["band"] == "healthy"
    assert first.data["data"]["client_snapshot"]["scope"]["status"] == "over_limit"
    assert "profitability" not in first.data["data"]["client_snapshot"]
    assert ServiceEngagementBusinessSnapshot.objects.count() == 1
    assert ProcessedCommand.objects.count() == 1

    other_org = Organization.objects.create(name="OTHER")
    outsider = _user(other_org, "atlas-profit-outsider@example.com")
    client.force_authenticate(user=outsider)
    denied = client.post(
        url,
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-profitability-outsider",
    )

    assert denied.status_code == 404
    assert denied.data["error"]["code"] == "NOT_FOUND"
    assert ServiceEngagementBusinessSnapshot.objects.count() == 1


def test_growth_signals_use_latest_backend_business_snapshot(user: User) -> None:
    org = user.default_organization
    assert org is not None
    company = _company(org, user, name="Atlas Growth Snapshot Client")
    engagement = _engagement(company, user)
    record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=user,
        data=_snapshot_payload(),
        idempotency_key="growth-signal-profitability",
    )

    payload = build_agency_growth_signals(company)

    assert payload["commercial"]["monthly_retainer"] == {
        "status": "known",
        "amount": "10000.00",
        "currency": "USD",
    }
    assert payload["commercial"]["gross_margin"] == {
        "status": "known",
        "value": "30.00",
        "band": "healthy",
    }
    assert payload["profit"]["status"] == "known"
    assert payload["profit"]["profitability_band"] == "healthy"
    assert payload["scope"]["status"] == "warning"
    assert payload["scope"]["utilization_percent"] == "120.00"


def test_business_snapshot_replays_after_concurrent_unique_conflict(monkeypatch) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-profit-race@example.com")
    company = _company(org, owner)
    engagement = _engagement(company, owner)
    payload = _snapshot_payload()
    first = record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=owner,
        data=payload,
        idempotency_key="profitability-sla-race",
    )

    original_existing = snapshots._existing_snapshot
    original_existing_locked = snapshots._existing_snapshot_locked
    calls = {"existing": 0, "locked": 0}

    def miss_then_existing(*, engagement, idempotency_key, source_key):
        calls["existing"] += 1
        if calls["existing"] == 1:
            return None
        return original_existing(
            engagement=engagement,
            idempotency_key=idempotency_key,
            source_key=source_key,
        )

    def miss_locked_once(*, engagement, idempotency_key, source_key):
        calls["locked"] += 1
        if calls["locked"] == 1:
            return None
        return original_existing_locked(
            engagement=engagement,
            idempotency_key=idempotency_key,
            source_key=source_key,
        )

    def raise_unique_conflict(**kwargs):
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(snapshots, "_existing_snapshot", miss_then_existing)
    monkeypatch.setattr(snapshots, "_existing_snapshot_locked", miss_locked_once)
    monkeypatch.setattr(ServiceEngagementBusinessSnapshot.objects, "create", raise_unique_conflict)

    replay = record_service_engagement_business_snapshot(
        engagement=engagement,
        actor=owner,
        data=payload,
        idempotency_key="profitability-sla-race",
    )

    assert replay.id == first.id
    assert replay._idempotency_status == "already_applied"
    assert ServiceEngagementBusinessSnapshot.objects.count() == 1
