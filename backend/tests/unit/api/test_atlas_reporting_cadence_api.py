from __future__ import annotations

import json
from datetime import date, timedelta
from typing import cast
from uuid import uuid4

import pytest

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AtlasReportingCadencePlan,
    AtlasReportingCadenceRun,
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    Organization,
    OrganizationMembership,
    ProcessedCommand,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

pytestmark = pytest.mark.django_db


def _company(user: User, name: str = "Reporting API Client") -> Graph:
    organization = user.default_organization
    assert organization is not None
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description=f"{name} operating company.",
        ),
    )


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _member_in_org(owner: User, *, role: str = "member") -> User:
    organization = owner.default_organization
    assert organization is not None
    member = User.objects.create_user(
        email=f"reporting-member-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": role, "is_default": True},
    )
    return member


def _engagement(company: Graph, user: User) -> ServiceEngagement:
    catalog = ServiceCatalogItem.objects.create(
        organization=_organization(company),
        slug=f"reporting-api-{uuid4().hex}",
        title="Reporting API Service",
        status="active",
        visibility="customer",
    )
    return ServiceEngagement.objects.create(
        organization=_organization(company),
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        metadata_json={"private_api_key": "sk_live_should_not_leak"},
        requested_by=user,
    )


def test_reporting_cadence_plan_api_creates_due_backend_plan_and_replays(
    authenticated_client,
    user,
) -> None:
    company = _company(user)
    today = date.today()
    payload = {
        "company_id": str(company.id),
        "cadence_type": "monthly",
        "next_due_on": today.isoformat(),
    }

    first = authenticated_client.post(
        "/api/company-ops/reporting-cadences",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="monthly-plan-create",
    )
    replay = authenticated_client.post(
        "/api/company-ops/reporting-cadences",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="monthly-plan-create",
    )
    conflict = authenticated_client.post(
        "/api/company-ops/reporting-cadences",
        {**payload, "cadence_type": "weekly"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="monthly-plan-create",
    )
    list_response = authenticated_client.get(
        "/api/company-ops/reporting-cadences",
        {"company_id": str(company.id)},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.data["data"]["duplicate"] is True
    assert conflict.status_code == 409
    assert list_response.status_code == 200
    plan = first.data["data"]["reporting_cadence_plan"]
    assert plan["company_id"] == str(company.id)
    assert plan["cadence_type"] == "monthly"
    assert plan["next_due_on"] == today.isoformat()
    assert plan["due_status"] == "due"
    assert len(list_response.data["data"]["reporting_cadence_plans"]) == 1
    assert AtlasReportingCadencePlan.objects.filter(company=company).count() == 1
    assert ProcessedCommand.objects.count() == 1


def test_reporting_cadence_run_api_generates_sanitized_snapshot_and_scopes_access(
    api_client,
    authenticated_client,
    user,
) -> None:
    company = _company(user, "Visible Reporting Client")
    hidden_company = _company(user, "Hidden Reporting Client")
    engagement = _engagement(company, user)
    ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Delivered Performance Report",
        deliverable_type="performance_report",
        status="delivered",
        visibility="customer",
        summary="Delivered proof of value.",
        metadata_json={"access_token": "deliverable-secret"},
        created_by=user,
    )
    plan_response = authenticated_client.post(
        "/api/company-ops/reporting-cadences",
        {
            "company_id": str(company.id),
            "cadence_type": "weekly",
            "next_due_on": date.today().isoformat(),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="weekly-plan-create",
    )
    hidden_plan = AtlasReportingCadencePlan.objects.create(
        organization=_organization(hidden_company),
        company=hidden_company,
        cadence_type="weekly",
        status="active",
        next_due_on=date.today(),
        created_by=user,
    )
    member = _member_in_org(user, role="member")
    for scoped_company in [company, hidden_company]:
        CompanyAccessPolicy.objects.create(
            organization=_organization(scoped_company),
            company=scoped_company,
            assignment_required=True,
            org_admin_access_enabled=False,
        )
    CompanyAssignment.objects.create(
        organization=_organization(company),
        company=company,
        user=member,
        role="member",
        status="active",
        created_by=user,
    )
    api_client.force_authenticate(user=member)
    plan_id = plan_response.data["data"]["reporting_cadence_plan"]["id"]
    payload = {
        "period_start": (date.today() - timedelta(days=7)).isoformat(),
        "period_end": date.today().isoformat(),
    }

    first = api_client.post(
        f"/api/company-ops/reporting-cadences/{plan_id}/runs",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="weekly-run-generate",
    )
    replay = api_client.post(
        f"/api/company-ops/reporting-cadences/{plan_id}/runs",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="weekly-run-generate",
    )
    scoped = api_client.post(
        f"/api/company-ops/reporting-cadences/{hidden_plan.id}/runs",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="hidden-run-generate",
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert scoped.status_code == 404
    assert replay.data["data"]["duplicate"] is True
    run = first.data["data"]["reporting_cadence_run"]
    rendered = json.dumps(first.data, sort_keys=True, default=str)
    assert run["cadence_type"] == "weekly"
    assert run["proof_snapshot"]["inputs_present"]["deliverables"] is True
    assert run["proof_snapshot"]["latest_deliverables"][0]["status"] == "delivered"
    assert "deliverable-secret" not in rendered
    assert "access_token" not in rendered
    assert "sk_live_should_not_leak" not in rendered
    assert AtlasReportingCadenceRun.objects.filter(company=company).count() == 1
    assert AtlasReportingCadenceRun.objects.filter(company=hidden_company).count() == 0
