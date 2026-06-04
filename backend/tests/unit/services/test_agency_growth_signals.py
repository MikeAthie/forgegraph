from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone

from application.services.agency_growth_signals import build_agency_growth_signals
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AtlasLaunchAttempt,
    CompanyOpportunity,
    CompanySignal,
    DepartmentRegistry,
    Graph,
    GraphVersion,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _company(user: User) -> tuple[Graph, GraphVersion]:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Growth Signals Client",
            description="",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _engagement(company: Graph, user: User, *, metadata: dict) -> ServiceEngagement:
    organization = company.organization
    assert organization is not None
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="digital-marketing-agency-engagement",
        title="Digital Marketing Agency Engagement",
        status="active",
        visibility="customer",
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        metadata_json=metadata,
        requested_by=user,
    )


def test_unknown_commercial_fields_remain_unknown(user) -> None:
    company, _version = _company(user)
    _engagement(
        company,
        user,
        metadata={
            "package": {"name": "Launch"},
            "api_key": "sk_live_metadata_secret",
        },
    )

    payload = build_agency_growth_signals(company)

    assert payload["commercial"]["monthly_retainer"] == {
        "status": "unknown",
        "amount": None,
        "currency": None,
    }
    assert payload["commercial"]["contract_value"] == {
        "status": "unknown",
        "amount": None,
        "currency": None,
    }
    assert payload["commercial"]["gross_margin"] == {"status": "unknown", "value": None}
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "sk_live_metadata_secret" not in rendered
    assert "api_key" not in rendered


def test_expansion_opportunity_is_derived_from_company_opportunity_and_signal(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    signal = CompanySignal.objects.create(
        organization=organization,
        company=company,
        created_by=user,
        signal_type="lead",
        signal_kind="opportunity",
        domain_context="services",
        status="qualified",
        source="manual",
        title="Lifecycle CRM request",
        summary="Client asked about lifecycle automation.",
        metadata_json={"secret_token": "do-not-render"},
    )
    opportunity = CompanyOpportunity.objects.create(
        organization=organization,
        company=company,
        signal=signal,
        owner_user=user,
        status="qualified",
        title="Lifecycle CRM expansion",
        summary="Add a lifecycle CRM workstream.",
        estimated_value_amount=Decimal("1200.00"),
        currency="usd",
        next_action="Prepare scope options.",
        metadata_json={"private_note": "internal-only"},
    )

    payload = build_agency_growth_signals(company)

    assert payload["expansion"]["status"] == "opportunity"
    assert payload["expansion"]["opportunities"] == [
        {
            "opportunity_id": str(opportunity.id),
            "source_signal_id": str(signal.id),
            "title": "Lifecycle CRM expansion",
            "summary": "Add a lifecycle CRM workstream.",
            "status": "qualified",
            "estimated_value": {"amount": "1200.00", "currency": "usd"},
            "next_action": "Prepare scope options.",
        }
    ]
    assert payload["expansion"]["signals"][0]["signal_id"] == str(signal.id)
    assert payload["expansion"]["signals"][0]["title"] == "Lifecycle CRM request"
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "do-not-render" not in rendered
    assert "internal-only" not in rendered
    assert "secret_token" not in rendered
    assert "private_note" not in rendered


def test_expansion_signal_fallback_is_scoped_to_company(user) -> None:
    company, _version = _company(user)
    other_user = User.objects.create_user(
        email="growth-signal-other@example.com",
        password="testpassword123",
    )
    other_company, _other_version = _company(other_user)
    other_organization = other_company.organization
    assert other_organization is not None
    leaked_signal = CompanySignal.objects.create(
        organization=other_organization,
        company=other_company,
        created_by=other_user,
        signal_type="lead",
        signal_kind="opportunity",
        domain_context="services",
        status="closed",
        source="manual",
        title="Other tenant expansion request",
        summary="This signal belongs to another company.",
    )
    organization = company.organization
    assert organization is not None
    CompanyOpportunity.objects.create(
        organization=organization,
        company=company,
        signal=leaked_signal,
        owner_user=user,
        status="qualified",
        title="Malformed cross-company opportunity",
        summary="Should not pull the linked signal payload.",
        estimated_value_amount=Decimal("300.00"),
        currency="usd",
    )

    payload = build_agency_growth_signals(company)

    assert payload["expansion"]["opportunities"][0]["source_signal_id"] == str(leaked_signal.id)
    assert payload["expansion"]["signals"] == []
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "Other tenant expansion request" not in rendered
    assert "This signal belongs to another company." not in rendered


def test_scope_creep_warning_from_requested_deliverables_over_package_limit(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    engagement = _engagement(
        company,
        user,
        metadata={
            "scope": {
                "package_limit": {"deliverables_per_period": 2},
                "requested_deliverables": 3,
            },
            "internal_notes": "do not expose",
        },
    )
    for index in range(3):
        ServiceDeliverable.objects.create(
            organization=organization,
            company=company,
            engagement=engagement,
            title=f"Requested Deliverable {index + 1}",
            deliverable_type="content_asset",
            status="draft",
            visibility="customer",
            summary="Requested by client.",
            created_by=user,
        )

    payload = build_agency_growth_signals(company)

    assert payload["scope"]["status"] == "warning"
    assert payload["scope"]["warnings"] == [
        {
            "slug": "scope_requested_deliverables_over_package_limit",
            "severity": "medium",
            "requested_deliverables": 3,
            "package_limit": 2,
            "summary": "Requested deliverables exceed the recorded package limit.",
        }
    ]
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "do not expose" not in rendered
    assert "internal_notes" not in rendered


def test_churn_risk_is_derived_from_health_reporting_sla_and_launch_inputs(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    engagement = _engagement(
        company,
        user,
        metadata={
            "reporting": {"cadences": ["weekly"]},
            "private_api_key": "sk_live_reporting_secret",
        },
    )
    deliverable = ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Launch approval packet",
        deliverable_type="approval_packet",
        status="in_review",
        visibility="customer",
        summary="Waiting on client approval.",
        metadata_json={"access_token": "do-not-render"},
        created_by=user,
    )
    ServiceDeliverable.objects.filter(id=deliverable.id).update(
        updated_at=timezone.now() - timedelta(days=12)
    )
    CompanySignal.objects.create(
        organization=organization,
        company=company,
        created_by=user,
        signal_type="fulfillment_issue",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Client asked why work is delayed",
        summary="Customer-visible delivery delay.",
        metadata_json={"secret_note": "hidden"},
    )
    department = DepartmentRegistry.objects.create(
        organization=organization,
        slug="strategy",
        name="Strategy",
    )
    TaskRoutingRecord.objects.create(
        organization=organization,
        company=company,
        service_engagement=engagement,
        to_department=department,
        status="blocked",
        priority="urgent",
        due_at=timezone.now() - timedelta(days=2),
        sla_breached_at=timezone.now() - timedelta(days=1),
        reason="Client escalation needs a response.",
        metadata_json={"bearer_token": "do-not-render"},
    )
    whiteboard = WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        status=WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        work_status=WorkWhiteboard.WORK_STATUS_DELIVERY,
        request_type="service_request",
        project_name="Launch blocked",
        client_name=company.name,
        request_summary="Launch is blocked.",
        objective="Ship campaign.",
        created_by=user,
    )
    AtlasLaunchAttempt.objects.create(
        organization=organization,
        company=company,
        whiteboard=whiteboard,
        source_key="launch-risk",
        idempotency_key="launch-risk",
        requested_mode="dry_run",
        status="blocked",
        blocker_snapshot_json=[{"code": "approval_missing", "secret": "hidden"}],
        readiness_snapshot_json={"status": "blocked", "api_key": "hidden"},
        created_by=user,
    )

    payload = build_agency_growth_signals(company)

    assert payload["retention"]["status"] == "risk"
    assert payload["retention"]["risk_score"] >= 80
    factor_slugs = {item["slug"] for item in payload["retention"]["factors"]}
    assert {
        "open_retention_signal",
        "stale_client_approval",
        "reporting_cadence_at_risk",
        "sla_breached",
        "launch_blocked",
    } <= factor_slugs
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "sk_live_reporting_secret" not in rendered
    assert "do-not-render" not in rendered
    assert "secret_note" not in rendered
    assert "bearer_token" not in rendered
    assert "api_key" not in rendered


def test_optional_profitability_metadata_informs_profit_without_schema_dependency(user) -> None:
    company, _version = _company(user)
    _engagement(
        company,
        user,
        metadata={
            "economics": {
                "monthly_retainer": {"amount": "4000.00", "currency": "usd"},
                "contract_value": {"amount": "48000.00", "currency": "usd"},
                "gross_margin": "0.18",
                "private_token": "do-not-render",
            }
        },
    )

    payload = build_agency_growth_signals(company)

    assert payload["commercial"]["monthly_retainer"] == {
        "status": "known",
        "amount": "4000.00",
        "currency": "usd",
    }
    assert payload["commercial"]["contract_value"] == {
        "status": "known",
        "amount": "48000.00",
        "currency": "usd",
    }
    assert payload["commercial"]["gross_margin"] == {"status": "known", "value": 0.18}
    assert payload["profit"]["status"] == "low_margin"
    assert any(
        item["slug"] == "gross_margin_below_target" for item in payload["retention"]["factors"]
    )
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "do-not-render" not in rendered
    assert "private_token" not in rendered


def test_expansion_intelligence_recommends_cross_sell_from_successful_delivery(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    engagement = _engagement(
        company,
        user,
        metadata={
            "package": {"name": "Launch"},
            "expansion": {"recommended_services": ["Lifecycle CRM", "Analytics Review"]},
            "secret": "hidden",
        },
    )
    ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Monthly report",
        deliverable_type="performance_report",
        status="accepted",
        visibility="customer",
        summary="Client accepted performance evidence.",
        created_by=user,
    )
    AtlasLaunchAttempt.objects.create(
        organization=organization,
        company=company,
        whiteboard=WorkWhiteboard.objects.create(
            organization=organization,
            company=company,
            status=WorkWhiteboard.STATUS_IN_DEPLOYMENT,
            work_status=WorkWhiteboard.WORK_STATUS_DELIVERY,
            request_type="service_request",
            project_name="Accepted launch",
            client_name=company.name,
            request_summary="Launch passed readiness.",
            objective="Ship campaign.",
            created_by=user,
        ),
        source_key="launch-ready",
        idempotency_key="launch-ready",
        requested_mode="dry_run",
        status="ready",
        readiness_snapshot_json={"status": "ready", "secret": "hidden"},
        created_by=user,
    )

    payload = build_agency_growth_signals(company)

    assert payload["expansion"]["status"] == "opportunity"
    assert payload["expansion"]["opportunity_score"] >= 60
    recommendation_slugs = {item["slug"] for item in payload["expansion"]["recommendations"]}
    assert {
        "accepted_deliverable_cross_sell",
        "successful_launch_follow_on",
        "recommended_service_lifecycle_crm",
    } <= recommendation_slugs
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "hidden" not in rendered
    assert "secret" not in rendered


def test_account_health_score_contributes_to_retention_risk(user) -> None:
    company, _version = _company(user)
    _engagement(company, user, metadata={"private_token": "do-not-render"})

    payload = build_agency_growth_signals(company)

    factor_slugs = {item["slug"] for item in payload["retention"]["factors"]}
    assert "account_health_attention" in factor_slugs
    assert payload["retention"]["risk_score"] > 0
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "do-not-render" not in rendered
    assert "private_token" not in rendered
