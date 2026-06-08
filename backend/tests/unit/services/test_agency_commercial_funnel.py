from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

import pytest

from application.services.agency_commercial_funnel import (
    build_proposal_packet,
    build_win_loss_status_summary,
    normalize_opportunity_intake,
)
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
            name="Atlas Prospect",
            description="",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _catalog(company: Graph, *, pricing_metadata: dict | None = None) -> ServiceCatalogItem:
    organization = company.organization
    assert organization is not None
    return ServiceCatalogItem.objects.create(
        organization=organization,
        slug="atlas-growth-accelerator",
        title="Atlas Growth Accelerator",
        description="Commercial funnel and lifecycle growth execution.",
        status="active",
        visibility="customer",
        deliverables_schema_json=[
            {"type": "strategy_brief", "title": "Growth strategy brief"},
            {"type": "approval_packet", "title": "Launch approval packet"},
        ],
        pricing_metadata_json=pricing_metadata or {},
    )


def _opportunity(
    company: Graph,
    user: User,
    *,
    status: str = "qualified",
    metadata: dict | None = None,
    signal: CompanySignal | None = None,
    title: str = "Lifecycle growth proposal",
) -> CompanyOpportunity:
    organization = company.organization
    assert organization is not None
    return CompanyOpportunity.objects.create(
        organization=organization,
        company=company,
        signal=signal,
        owner_user=user,
        status=status,
        title=title,
        summary="Client wants help converting discovery demand into retained execution.",
        estimated_value_amount=Decimal("0.00"),
        currency="usd",
        next_action="Prepare proposal packet.",
        metadata_json=metadata or {},
    )


def test_normalizes_opportunity_intake_fields_from_backend_metadata(user) -> None:
    company, _version = _company(user)
    opportunity = _opportunity(
        company,
        user,
        metadata={
            "commercial_intake": {
                "icp_fit": {"label": "strong", "score": "86"},
                "pain": "Slow lead handoff; no lifecycle attribution",
                "budget": {"amount": "15000", "currency": "usd"},
                "authority": "vp_marketing",
                "timing": "Q3 launch window",
                "expected_retainer": {"amount": "6500.456", "currency": "usd"},
                "close_probability": "72%",
                "internal_notes": "Discount only if procurement asks.",
            }
        },
    )

    intake = normalize_opportunity_intake(opportunity)

    assert intake == {
        "icp_fit": {"status": "known", "value": "strong", "score": 86},
        "pain": {
            "status": "known",
            "items": ["Slow lead handoff", "no lifecycle attribution"],
        },
        "budget": {"status": "known", "amount": "15000.00", "currency": "usd"},
        "authority": {"status": "known", "value": "vp_marketing"},
        "timing": {"status": "known", "value": "Q3 launch window"},
        "expected_retainer": {
            "status": "known",
            "amount": "6500.46",
            "currency": "usd",
        },
        "close_probability": {"status": "known", "value": 0.72},
    }


def test_missing_commercial_metrics_are_explicit_unknown(user) -> None:
    company, _version = _company(user)
    opportunity = _opportunity(company, user)

    intake = normalize_opportunity_intake(opportunity)
    packet = build_proposal_packet(opportunity)

    assert intake["budget"] == {"status": "unknown", "amount": None, "currency": None}
    assert intake["expected_retainer"] == {
        "status": "unknown",
        "amount": None,
        "currency": None,
    }
    assert intake["close_probability"] == {"status": "unknown", "value": None}
    assert packet["client_safe"]["sections"]["roi_estimate"] == {
        "status": "unknown",
        "projected_value": {"status": "unknown", "amount": None, "currency": None},
        "payback_period_months": {"status": "unknown", "value": None},
        "basis": "ROI cannot be estimated until explicit client-approved inputs are recorded.",
    }


def test_proposal_packet_includes_client_safe_sow_roi_pricing_and_deliverables(user) -> None:
    company, _version = _company(user)
    opportunity = _opportunity(
        company,
        user,
        metadata={
            "commercial_intake": {
                "expected_retainer": {"amount": "6500", "currency": "usd"},
                "close_probability": 0.64,
            }
        },
    )
    catalog = _catalog(
        company,
        pricing_metadata={
            "package": {
                "slug": "growth-accelerator",
                "name": "Growth Accelerator",
                "billing_period": "monthly",
                "retainer": {"amount": "6500", "currency": "usd"},
            },
            "setup_fee": {"amount": "1500", "currency": "usd"},
            "internal_margin_target": "62%",
        },
    )
    organization = company.organization
    assert organization is not None
    engagement = ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="intake",
        customer_status="intake_needed",
        intake_data_json={
            "proposal": {
                "sow": {
                    "objective": "Convert paid discovery into a retained lifecycle program.",
                    "in_scope": ["Discovery synthesis", "Lifecycle campaign blueprint"],
                    "out_of_scope": ["Media buying"],
                    "assumptions": ["Client approves CRM access during onboarding"],
                    "internal_notes": "Do not promise custom procurement discount.",
                },
                "roi_estimate": {
                    "projected_value": {"amount": "42000", "currency": "usd"},
                    "payback_period_months": 3,
                    "basis": "Client supplied current lead volume and target conversion lift.",
                },
            }
        },
        metadata_json={
            "opportunity_id": str(opportunity.id),
            "internal_notes": "Procurement risk is high.",
        },
        internal_notes="Pricing guardrail: never expose margin target.",
        requested_by=user,
    )
    ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Proposal Packet",
        deliverable_type="approval_packet",
        status="draft",
        visibility="customer",
        summary="Draft client proposal.",
        metadata_json={"internal_notes": "Needs partner review."},
        created_by=user,
    )

    packet = build_proposal_packet(opportunity, engagement=engagement)
    client_safe = packet["client_safe"]

    assert client_safe["proposal"]["status"] == "draft"
    assert client_safe["sections"]["sow"] == {
        "status": "known",
        "objective": "Convert paid discovery into a retained lifecycle program.",
        "in_scope": ["Discovery synthesis", "Lifecycle campaign blueprint"],
        "out_of_scope": ["Media buying"],
        "assumptions": ["Client approves CRM access during onboarding"],
    }
    assert client_safe["sections"]["roi_estimate"] == {
        "status": "known",
        "projected_value": {"status": "known", "amount": "42000.00", "currency": "usd"},
        "payback_period_months": {"status": "known", "value": 3},
        "basis": "Client supplied current lead volume and target conversion lift.",
    }
    assert client_safe["pricing"] == {
        "status": "known",
        "package": {
            "slug": "growth-accelerator",
            "name": "Growth Accelerator",
            "billing_period": "monthly",
            "retainer": {"status": "known", "amount": "6500.00", "currency": "usd"},
        },
        "setup_fee": {"status": "known", "amount": "1500.00", "currency": "usd"},
    }
    assert client_safe["deliverables"] == [
        {
            "id": None,
            "title": "Growth strategy brief",
            "type": "strategy_brief",
            "status": "planned",
        },
        {
            "id": str(ServiceDeliverable.objects.get().id),
            "title": "Proposal Packet",
            "type": "approval_packet",
            "status": "draft",
        },
    ]
    rendered = json.dumps(client_safe, sort_keys=True, default=str)
    assert "internal" not in rendered.lower()
    assert "margin" not in rendered.lower()
    assert "partner review" not in rendered


def test_win_loss_status_summary_counts_backend_opportunity_statuses(user) -> None:
    company, _version = _company(user)
    _opportunity(company, user, status="converted", title="Won lifecycle retainer")
    _opportunity(
        company,
        user,
        status="lost",
        title="Lost content sprint",
        metadata={"loss_reason": "No executive sponsor"},
    )
    open_opportunity = _opportunity(company, user, status="follow_up", title="Open CRM expansion")

    summary = build_win_loss_status_summary(company, current_opportunity=open_opportunity)

    assert summary == {
        "current_opportunity": {
            "opportunity_id": str(open_opportunity.id),
            "status": "open",
            "raw_status": "follow_up",
        },
        "company": {
            "open": {"count": 1, "statuses": ["follow_up"]},
            "won": {"count": 1, "statuses": ["converted"]},
            "lost": {"count": 1, "statuses": ["lost"]},
        },
    }
