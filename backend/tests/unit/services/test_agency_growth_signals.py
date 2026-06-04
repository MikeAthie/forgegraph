from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

import pytest

from application.services.agency_growth_signals import build_agency_growth_signals
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CompanyOpportunity,
    CompanySignal,
    Graph,
    GraphVersion,
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
