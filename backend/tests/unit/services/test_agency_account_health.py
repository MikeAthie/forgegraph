from __future__ import annotations

import json
from datetime import date, timedelta
from typing import cast

import pytest
from django.utils import timezone

from application.services.agency_account_health import build_agency_account_health_snapshot
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    APIKey,
    GatewayConnection,
    Graph,
    GraphVersion,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
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
            name="Legacy Eyewear",
            description="",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _engagement(
    company: Graph,
    user: User,
    *,
    metadata: dict | None = None,
) -> ServiceEngagement:
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
        metadata_json=metadata or {},
        requested_by=user,
    )


def test_account_health_snapshot_exposes_required_sections_and_unknown_commercial_values(
    user,
) -> None:
    company, version = _company(user)
    organization = company.organization
    assert organization is not None
    credential = APIKey.objects.create(
        organization=organization,
        user=user,
        provider="gmail",
        name="Unsafe Gmail",
        encrypted_key=b"secret-api-key",
    )
    GatewayConnection.objects.create(
        organization=organization,
        graph_version=version,
        credential=credential,
        platform="email",
        provider="gmail",
        name="Unsafe connection",
        status="enabled",
        config_json={"api_key": "secret-api-key", "raw_provider_config": "private"},
    )
    _engagement(
        company,
        user,
        metadata={
            "reporting": {"cadences": ["weekly"]},
            "private_token": "metadata-secret-token",
        },
    )

    snapshot = build_agency_account_health_snapshot(company)

    assert set(snapshot) >= {
        "profile",
        "health",
        "onboarding_items",
        "connector_readiness",
        "recurring_reporting",
        "growth_signals",
        "risks",
        "opportunities",
        "next_actions",
    }
    assert snapshot["profile"]["commercial"]["monthly_retainer"]["status"] == "unknown"
    assert snapshot["profile"]["commercial"]["contract_value"]["status"] == "unknown"
    assert snapshot["profile"]["commercial"]["gross_margin"]["status"] == "unknown"
    assert snapshot["connector_readiness"]["summary"]["missing"] >= 1
    assert any(
        action["slug"].startswith("configure_") for action in snapshot["next_actions"]
    )
    assert snapshot["health"]["score"] < 80
    rendered = json.dumps(snapshot, sort_keys=True, default=str)
    assert str(credential.id) not in rendered
    assert "credential_id" not in rendered
    assert "secret-api-key" not in rendered
    assert "raw_provider_config" not in rendered
    assert "api_key" not in rendered
    assert "metadata-secret-token" not in rendered
    assert "private_token" not in rendered


def test_account_health_snapshot_flags_stale_approval_and_recent_report(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    engagement = _engagement(company, user)
    deliverable = ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Approval Packet",
        deliverable_type="approval_packet",
        status="in_review",
        visibility="customer",
        summary="Waiting on approval.",
        created_by=user,
    )
    stale_time = timezone.now() - timedelta(days=15)
    ServiceDeliverable.objects.filter(id=deliverable.id).update(updated_at=stale_time)
    ReportRun.objects.create(
        organization=organization,
        company=company,
        report_template_id="agency.monthly_review",
        period_start=date.today() - timedelta(days=30),
        period_end=date.today(),
        generated_sections_json={"summary": "Recent report"},
        created_by=user,
    )

    snapshot = build_agency_account_health_snapshot(company)
    risk_slugs = {item["slug"] for item in snapshot["risks"]}
    opportunity_slugs = {item["slug"] for item in snapshot["opportunities"]}
    dimensions = {item["slug"]: item for item in snapshot["health"]["dimensions"]}

    assert "stale_client_approval" in risk_slugs
    assert "recent_performance_report" in opportunity_slugs
    assert snapshot["recurring_reporting"]["summary"]["status"] in {"healthy", "monitor"}
    assert snapshot["growth_signals"]["commercial"]["gross_margin"]["status"] == "unknown"
    assert dimensions["reporting"]["score"] >= 80
    assert any(
        action["owner_department_slug"] == "client_approval_ops"
        and "approval" in action["slug"]
        for action in snapshot["next_actions"]
    )
