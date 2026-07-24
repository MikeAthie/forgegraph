from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, cast

import pytest
from django.utils import timezone

from application.services.agency_reporting_cadence import build_recurring_reporting_status
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
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
            name="Recurring Reporting Client",
            description="",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _engagement(company: Graph, user: User, *, metadata: dict[str, Any]) -> ServiceEngagement:
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


def _cadence(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    matches = [item for item in payload["cadences"] if item["slug"] == slug]
    assert len(matches) == 1
    return cast(dict[str, Any], matches[0])


def test_stale_weekly_report_is_at_risk(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    _engagement(
        company,
        user,
        metadata={
            "reporting": {"cadences": ["weekly"]},
            "private_api_key": "sk_live_should_not_leave_metadata",
        },
    )
    ReportRun.objects.create(
        organization=organization,
        company=company,
        report_template_id="agency.weekly_performance",
        period_start=date.today() - timedelta(days=21),
        period_end=date.today() - timedelta(days=14),
        generated_sections_json={"summary": "Old performance report"},
        created_by=user,
    )

    payload = build_recurring_reporting_status(company)

    assert [item["slug"] for item in payload["cadences"]] == ["weekly", "monthly", "qbr"]
    weekly = _cadence(payload, "weekly")
    assert weekly["status"] == "at_risk"
    assert weekly["configured"] is True
    assert weekly["last_report"]["status"] == "known"
    assert weekly["last_report"]["days_since_period_end"] >= 14
    assert any(risk["slug"] == "weekly_report_stale" for risk in payload["risks"])
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "sk_live_should_not_leave_metadata" not in rendered
    assert "private_api_key" not in rendered


def test_recent_delivered_performance_report_is_healthy(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    engagement = _engagement(
        company,
        user,
        metadata={"reporting": {"cadences": ["weekly"]}},
    )
    report = ReportRun.objects.create(
        organization=organization,
        company=company,
        report_template_id="agency.weekly_performance",
        period_start=date.today() - timedelta(days=10),
        period_end=date.today() - timedelta(days=2),
        generated_sections_json={"summary": "Recent performance report"},
        created_by=user,
    )
    deliverable = ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Weekly Performance Report",
        deliverable_type="performance_report",
        status="delivered",
        visibility="customer",
        summary="Delivered to client.",
        report_run=report,
        metadata_json={"access_token": "should-not-leak"},
        delivered_at=timezone.now(),
        created_by=user,
    )

    payload = build_recurring_reporting_status(company)

    weekly = _cadence(payload, "weekly")
    assert weekly["status"] == "healthy"
    assert weekly["last_report"]["report_run_id"] == str(report.id)
    assert weekly["latest_deliverable"]["deliverable_id"] == str(deliverable.id)
    assert weekly["latest_deliverable"]["status"] == "delivered"
    assert not [risk for risk in payload["risks"] if risk["slug"] == "weekly_report_stale"]
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "should-not-leak" not in rendered
    assert "access_token" not in rendered
