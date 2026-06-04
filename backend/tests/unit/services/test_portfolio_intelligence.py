from __future__ import annotations

import json
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest

from application.services.portfolio_intelligence import portfolio_intelligence_payload
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

pytestmark = pytest.mark.django_db


def _company(user: User, name: str) -> Graph:
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description=f"{name} portfolio intelligence company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _member_in_org(owner: User) -> User:
    organization = owner.default_organization
    assert organization is not None
    member = User.objects.create_user(
        email=f"portfolio-intel-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": "viewer", "is_default": True},
    )
    return member


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _catalog_item(organization: Organization) -> ServiceCatalogItem:
    item, _created = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug="portfolio-intelligence-engagement",
        defaults={
            "title": "Portfolio Intelligence Engagement",
            "status": "active",
            "visibility": "customer",
        },
    )
    return item


def _engagement(company: Graph, user: User, *, metadata: dict) -> ServiceEngagement:
    organization = _organization(company)
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=_catalog_item(organization),
        status="in_progress",
        customer_status="working",
        metadata_json=metadata,
        requested_by=user,
    )


def _restrict_to_assignments(
    owner: User,
    *companies: Graph,
    assigned_count: int = 2,
) -> User:
    member = _member_in_org(owner)
    for company in companies:
        organization = _organization(company)
        CompanyAccessPolicy.objects.create(
            organization=organization,
            company=company,
            assignment_required=True,
            org_admin_access_enabled=False,
        )
    for company in companies[:assigned_count]:
        CompanyAssignment.objects.create(
            organization=_organization(company),
            company=company,
            user=member,
            role="viewer",
            status="active",
            created_by=owner,
        )
    return member


def test_portfolio_intelligence_aggregates_accessible_companies_without_raw_peer_data(
    user,
) -> None:
    ensure_default_organization(user)
    at_risk = _company(user, "At Risk Client")
    growth_ready = _company(user, "Growth Ready Client")
    hidden = _company(user, "Hidden Client")
    member = _restrict_to_assignments(user, at_risk, growth_ready, hidden)
    organization = _organization(at_risk)
    _engagement(
        at_risk,
        user,
        metadata={
            "reporting": {"cadences": ["weekly"]},
            "economics": {"gross_margin": "0.16"},
            "private_note": "do-not-render-risk",
        },
    )
    CompanySignal.objects.create(
        organization=organization,
        company=at_risk,
        created_by=user,
        signal_type="fulfillment_issue",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Escalation from client",
        summary="Visible risk summary.",
        metadata_json={"access_token": "do-not-render-risk"},
    )
    engagement = _engagement(
        growth_ready,
        user,
        metadata={
            "expansion": {"recommended_services": ["Lifecycle CRM"]},
            "secret": "do-not-render-expansion",
        },
    )
    ServiceDeliverable.objects.create(
        organization=organization,
        company=growth_ready,
        engagement=engagement,
        title="Accepted report",
        deliverable_type="performance_report",
        status="accepted",
        visibility="customer",
        created_by=user,
    )
    signal = CompanySignal.objects.create(
        organization=organization,
        company=growth_ready,
        created_by=user,
        signal_type="lead",
        signal_kind="opportunity",
        status="qualified",
        source="manual",
        title="Lifecycle request",
        metadata_json={"secret": "do-not-render-expansion"},
    )
    CompanyOpportunity.objects.create(
        organization=organization,
        company=growth_ready,
        signal=signal,
        owner_user=user,
        status="qualified",
        title="Lifecycle expansion",
        estimated_value_amount=Decimal("1500.00"),
        currency="usd",
        metadata_json={"private_note": "do-not-render-expansion"},
    )
    hidden_org = _organization(hidden)
    CompanySignal.objects.create(
        organization=hidden_org,
        company=hidden,
        created_by=user,
        signal_type="manual",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Hidden tenant risk",
        metadata_json={"secret": "hidden-raw-secret"},
    )

    payload = portfolio_intelligence_payload(member)

    assert payload["privacy"]["mode"] == "aggregate_only"
    assert payload["privacy"]["raw_company_payloads_exposed"] is False
    assert payload["summary"]["companies_analyzed"] == 2
    assert payload["summary"]["high_churn_risk"] == 1
    assert payload["summary"]["expansion_opportunity_accounts"] == 1
    assert payload["benchmarks"]["churn_risk_score"]["sample_size"] == 2
    assert payload["benchmarks"]["expansion_opportunity_score"]["sample_size"] == 2
    assert payload["benchmarks"]["churn_risk_score"]["median"] is not None
    assert payload["priority_queue"][0]["priority"] in {"protect", "expand"}
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "Hidden Client" not in rendered
    assert "Hidden tenant risk" not in rendered
    assert "At Risk Client" not in rendered
    assert "Growth Ready Client" not in rendered
    assert "do-not-render-risk" not in rendered
    assert "do-not-render-expansion" not in rendered
    assert "hidden-raw-secret" not in rendered
    assert "access_token" not in rendered
    assert "private_note" not in rendered


def test_company_ops_portfolio_intelligence_api_uses_assignment_scoping(
    api_client,
    user,
) -> None:
    ensure_default_organization(user)
    allowed = _company(user, "Allowed Benchmark Client")
    hidden = _company(user, "Hidden Benchmark Client")
    member = _restrict_to_assignments(user, allowed, hidden, assigned_count=1)
    organization = _organization(allowed)
    CompanySignal.objects.create(
        organization=organization,
        company=allowed,
        created_by=user,
        signal_type="fulfillment_issue",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Allowed risk",
    )
    CompanySignal.objects.create(
        organization=_organization(hidden),
        company=hidden,
        created_by=user,
        signal_type="fulfillment_issue",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Hidden risk",
    )
    api_client.force_authenticate(user=member)

    response = api_client.get("/api/company-ops/portfolio-intelligence")

    assert response.status_code == 200
    payload = response.json()["data"]["portfolio_intelligence"]
    assert payload["summary"]["companies_analyzed"] == 1
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "Allowed Benchmark Client" not in rendered
    assert "Hidden Benchmark Client" not in rendered
    assert "Hidden risk" not in rendered


def test_portfolio_benchmarks_are_suppressed_below_minimum_peer_count(user) -> None:
    ensure_default_organization(user)
    allowed = _company(user, "Solo Benchmark Client")
    hidden = _company(user, "Hidden Solo Peer")
    member = _restrict_to_assignments(user, allowed, hidden, assigned_count=1)
    organization = _organization(allowed)
    CompanySignal.objects.create(
        organization=organization,
        company=allowed,
        created_by=user,
        signal_type="fulfillment_issue",
        signal_kind="risk",
        status="new",
        source="manual",
        title="Solo risk",
    )

    payload = portfolio_intelligence_payload(member)

    assert payload["summary"]["companies_analyzed"] == 1
    assert payload["privacy"]["minimum_peer_count"] == 2
    churn_benchmark = payload["benchmarks"]["churn_risk_score"]
    assert churn_benchmark["sample_size"] == 1
    assert churn_benchmark["suppressed"] is True
    assert churn_benchmark["suppression_reason"] == "minimum_peer_count"
    assert churn_benchmark["average"] is None
    assert churn_benchmark["median"] is None
    assert churn_benchmark["minimum"] is None
    assert churn_benchmark["maximum"] is None
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert "Solo Benchmark Client" not in rendered
    assert "Hidden Solo Peer" not in rendered
