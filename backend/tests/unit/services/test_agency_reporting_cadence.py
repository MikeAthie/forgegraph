from __future__ import annotations

import json
from datetime import date, timedelta
from typing import cast

import pytest
from django.utils import timezone

from application.services.agency_reporting_cadence import (
    build_recurring_reporting_status,
    generate_reporting_cadence_run,
    reporting_cadence_plan_payload,
    upsert_reporting_cadence_plan,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AtlasLaunchAttempt,
    AtlasReportingCadencePlan,
    AtlasReportingCadenceRun,
    AuditLog,
    DomainEvent,
    DomainEventOutbox,
    Graph,
    GraphVersion,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
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


def _cadence(payload: dict, slug: str) -> dict:
    matches = [item for item in payload["cadences"] if item["slug"] == slug]
    assert len(matches) == 1
    return matches[0]


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


def test_backend_owned_plan_tracks_next_due_and_due_status(user) -> None:
    company, _version = _company(user)
    today = date.today()

    plan = upsert_reporting_cadence_plan(
        company=company,
        cadence_type="weekly",
        actor=user,
        next_due_on=today - timedelta(days=1),
    )

    payload = reporting_cadence_plan_payload(plan)
    status = build_recurring_reporting_status(company)
    weekly = _cadence(status, "weekly")

    assert AtlasReportingCadencePlan.objects.filter(company=company).count() == 1
    assert plan.organization_id == company.organization_id
    assert payload["cadence_type"] == "weekly"
    assert payload["next_due_on"] == (today - timedelta(days=1)).isoformat()
    assert payload["due_status"] == "overdue"
    assert weekly["configured"] is True
    assert weekly["next_due_on"] == (today - timedelta(days=1)).isoformat()
    assert weekly["due_status"] == "overdue"
    assert AuditLog.objects.filter(
        action="atlas_reporting_cadence.plan_upserted",
        resource_type="atlas_reporting_cadence_plan",
        resource_id=str(plan.id),
    ).exists()


def test_generate_report_run_snapshots_proof_of_value_and_advances_plan(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    today = date.today()
    engagement = _engagement(
        company,
        user,
        metadata={
            "scope": {"requested_deliverables": 3, "deliverables_per_month": 5},
            "private_api_key": "sk_live_scope_secret",
        },
    )
    source_report = ReportRun.objects.create(
        organization=organization,
        company=company,
        report_template_id="agency.weekly_performance",
        period_start=today - timedelta(days=8),
        period_end=today - timedelta(days=1),
        generated_sections_json={
            "summary": "Performance improved.",
            "access_token": "raw-report-token",
        },
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
        report_run=source_report,
        summary="Client-safe result summary.",
        metadata_json={"private_note": "operator-only", "access_token": "deliverable-token"},
        delivered_at=timezone.now(),
        created_by=user,
    )
    whiteboard = WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        status=WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        work_status=WorkWhiteboard.WORK_STATUS_DELIVERY,
        request_type="service_request",
        project_name="Proof Launch",
        client_name=company.name,
        request_summary="Proof launch readiness.",
        objective="Show campaign proof of value.",
        created_by=user,
    )
    launch_attempt = AtlasLaunchAttempt.objects.create(
        organization=organization,
        company=company,
        whiteboard=whiteboard,
        source_key="atlas-launch-proof",
        idempotency_key="atlas-launch-proof",
        requested_mode="dry_run",
        status="ready",
        readiness_snapshot_json={"status": "ready", "secret": "launch-secret"},
        created_by=user,
        last_checkpoint_at=timezone.now(),
    )
    plan = upsert_reporting_cadence_plan(
        company=company,
        cadence_type="weekly",
        actor=user,
        next_due_on=today,
    )

    run = generate_reporting_cadence_run(
        plan=plan,
        actor=user,
        idempotency_key="weekly-proof-report",
        period_start=today - timedelta(days=7),
        period_end=today,
    )
    replay = generate_reporting_cadence_run(
        plan=plan,
        actor=user,
        idempotency_key="weekly-proof-report",
        period_start=today - timedelta(days=7),
        period_end=today,
    )

    plan.refresh_from_db()
    rendered = json.dumps(run.proof_snapshot_json, sort_keys=True, default=str)
    assert replay.id == run.id
    assert AtlasReportingCadenceRun.objects.filter(plan=plan).count() == 1
    assert run.report_run is not None
    assert run.report_run.report_template_id == "atlas.proof_of_value.weekly"
    assert plan.last_run_id == run.id
    assert plan.next_due_on == today + timedelta(days=7)
    assert run.proof_snapshot_json["cadence"]["type"] == "weekly"
    assert run.proof_snapshot_json["inputs_present"]["deliverables"] is True
    assert run.proof_snapshot_json["inputs_present"]["launch"] is True
    assert run.proof_snapshot_json["latest_deliverables"][0]["deliverable_id"] == str(
        deliverable.id
    )
    assert run.proof_snapshot_json["launch"]["latest_attempt"]["id"] == str(launch_attempt.id)
    assert "profit" in run.proof_snapshot_json["growth_signals"]
    assert "raw-report-token" not in rendered
    assert "deliverable-token" not in rendered
    assert "launch-secret" not in rendered
    assert "sk_live_scope_secret" not in rendered
    assert "access_token" not in rendered
    assert "private_api_key" not in rendered
    assert DomainEvent.objects.filter(
        event_type="atlas.reporting_cadence_run.generated",
        aggregate_id=run.id,
    ).exists()
    assert DomainEventOutbox.objects.filter(
        event_type="atlas.reporting_cadence_run.generated",
        aggregate_id=run.id,
        company=company,
        status="pending",
    ).exists()
    assert AuditLog.objects.filter(
        action="atlas_reporting_cadence.run_generated",
        resource_type="atlas_reporting_cadence_run",
        resource_id=str(run.id),
    ).exists()
