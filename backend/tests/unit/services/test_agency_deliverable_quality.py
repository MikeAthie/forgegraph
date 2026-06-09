from __future__ import annotations

from typing import cast

import pytest

from application.services.agency_deliverable_quality import DeliverableQualityGate
from application.services.agency_deliverables import assemble_atlas_deliverable
from infrastructure.orm.models import (
    Asset,
    Graph,
    Organization,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str = "atlas-quality@example.com") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=org, user=user, role="owner", is_default=True
    )
    return user


def _company(org: Organization, owner: User, *, name: str = "Quality Client") -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=owner,
            organization=org,
            name=name,
            description="Customer operating company.",
        ),
    )


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        work_status=WorkWhiteboard.WORK_STATUS_DELIVERY,
        request_type="service_request",
        project_name="Summer Launch",
        client_name=company.name,
        request_summary="Launch a summer campaign across email and WhatsApp.",
        objective="Increase repeat purchases for summer accessories.",
        created_by=owner,
    )


def _engagement(company: Graph, owner: User) -> ServiceEngagement:
    organization = required_company_organization(company)
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="quality-service",
        title="Quality Service",
        description="Service used for quality gate tests.",
        status="active",
        visibility="customer",
        deliverables_schema_json=[
            {"type": "launch_readiness_checklist", "requires_approval": True}
        ],
        created_by=owner,
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        requested_by=owner,
    )


def _artifact(company: Graph) -> Asset:
    return Asset.objects.create(
        organization=required_company_organization(company),
        company=company,
        title="Deliverable artifact",
        asset_type="deliverable",
        created_by_type="system",
    )


def test_quality_gate_passes_normal_assembled_deliverable() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org)
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)
    deliverable = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="client_brief",
    )

    result = DeliverableQualityGate().evaluate(deliverable)

    assert result["status"] == "pass"
    assert result["passed"] is True
    assert result["score"] >= 90
    assert result["visibility"]["client_safe"] is True
    assert {check["id"] for check in result["checks"]} >= {
        "required_title",
        "required_summary",
        "required_artifact",
        "internal_confidential_leakage",
        "secret_like_metadata",
        "evidence_source_refs",
        "approval_requirement",
        "blocked_connectors",
        "customer_visibility",
    }
    assert result["blockers"] == []


def test_quality_gate_blocks_missing_artifact_and_sensitive_leakage() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-quality-fail@example.com")
    company = _company(org, owner)
    engagement = _engagement(company, owner)
    deliverable = ServiceDeliverable.objects.create(
        organization=org,
        company=company,
        engagement=engagement,
        title="Confidential launch plan",
        deliverable_type="client_brief",
        status="draft",
        visibility="customer",
        summary="Internal only strategy with customer-facing wording pending.",
        metadata_json={"api_key": "sk-test", "source_refs": {"whiteboard": "wb_123"}},
        created_by=owner,
    )

    result = DeliverableQualityGate().evaluate(deliverable)

    blocker_codes = {blocker["code"] for blocker in result["blockers"]}
    assert result["status"] == "fail"
    assert result["passed"] is False
    assert blocker_codes >= {
        "required_artifact",
        "internal_confidential_leakage",
        "secret_like_metadata",
    }
    assert result["visibility"]["client_safe"] is False


def test_quality_gate_flags_blocked_connectors_for_launch_deliverables() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-quality-blocked@example.com")
    company = _company(org, owner)
    engagement = _engagement(company, owner)
    deliverable = ServiceDeliverable.objects.create(
        organization=org,
        company=company,
        engagement=engagement,
        title="Launch Readiness Checklist",
        deliverable_type="launch_readiness_checklist",
        status="ready",
        visibility="customer",
        artifact=_artifact(company),
        summary="Ready for customer review after connector validation.",
        metadata_json={
            "requires_approval": True,
            "source_refs": {"deployment": {"status": "partial"}},
            "blocked_by": ["whatsapp"],
        },
        created_by=owner,
    )

    result = DeliverableQualityGate().evaluate(deliverable)

    assert result["status"] == "fail"
    assert result["passed"] is False
    assert "blocked_connectors" in {blocker["code"] for blocker in result["blockers"]}
    blocked_check = next(check for check in result["checks"] if check["id"] == "blocked_connectors")
    assert blocked_check["status"] == "fail"
