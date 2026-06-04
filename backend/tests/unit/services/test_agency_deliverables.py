from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from application.services.agency_deliverable_catalog import MVP_DELIVERABLE_TYPES
from application.services.agency_deliverables import (
    assemble_atlas_deliverable,
    assemble_atlas_mvp_deliverables,
    ensure_atlas_service_engagement,
)
from application.services.service_engagements import service_deliverable_payload
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    Organization,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    StateProjection,
    User,
    WorkWhiteboard,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str = "atlas-deliverables@example.com") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role="owner", is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
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
        target_audience_json={"segments": ["returning customers"]},
        brand_context_json={"tone": "confident"},
        created_by=owner,
    )


def _content_for(deliverable: ServiceDeliverable) -> str:
    version_id = deliverable.metadata_json["asset_version_id"]
    version = AssetVersion.objects.get(id=version_id, asset=deliverable.artifact)
    return str(version.provenance_json["inline_content"])


def test_ensure_atlas_service_engagement_creates_catalog_and_engagement() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org)
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)

    engagement = ensure_atlas_service_engagement(whiteboard=whiteboard, user=owner)

    catalog = ServiceCatalogItem.objects.get(
        organization=org,
        slug="digital-marketing-agency-engagement",
    )
    assert engagement.catalog_item == catalog
    assert engagement.source_key == f"atlas-engagement:{whiteboard.id}"
    assert engagement.required_pack_ids_json == ["digital_marketing_pro.v1"]
    assert "summer campaign" in engagement.public_summary.lower()
    assert "repeat purchases" in engagement.public_summary.lower()


def test_ensure_atlas_service_engagement_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-idempotent@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)

    first = ensure_atlas_service_engagement(whiteboard=whiteboard, user=owner)
    second = ensure_atlas_service_engagement(whiteboard=whiteboard, user=owner)

    assert second.id == first.id
    assert ServiceCatalogItem.objects.count() == 1
    assert ServiceEngagement.objects.count() == 1


def test_assemble_client_brief_creates_asset_version_and_deliverable() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-client-brief@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)

    deliverable = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="client_brief",
    )

    asset = Asset.objects.get(source_key=f"atlas-deliverable:{whiteboard.id}:client_brief")
    version = AssetVersion.objects.get(asset=asset)
    assert asset.status == "active"
    assert asset.metadata_json["source"] == "atlas_deliverable_assembly"
    assert version.mime_type == "text/markdown"
    assert ServiceDeliverable.objects.count() == 1
    assert deliverable.deliverable_type == "client_brief"
    assert deliverable.status == "ready"
    assert deliverable.visibility == "customer"
    assert deliverable.artifact == asset
    assert deliverable.metadata_json["whiteboard_id"] == str(whiteboard.id)
    assert deliverable.metadata_json["deliverable_type"] == "client_brief"
    assert deliverable.metadata_json["owner_department_slug"] == "client_approval_ops"
    assert deliverable.metadata_json["asset_version_id"] == str(version.id)
    assert deliverable.metadata_json["quality_gate"]["status"] == "pass"
    assert deliverable.metadata_json["quality_gate"]["visibility"]["client_safe"] is True


def test_single_deliverable_assembly_is_idempotent_when_content_is_unchanged() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-single-idempotent@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)

    first = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="client_brief",
    )
    second = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="client_brief",
    )

    assert second.id == first.id
    assert ServiceEngagement.objects.count() == 1
    assert Asset.objects.count() == 1
    assert AssetVersion.objects.count() == 1
    assert ServiceDeliverable.objects.count() == 1


def test_assemble_atlas_mvp_deliverables_returns_all_types_and_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-batch@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)

    first = assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)
    second = assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)

    assert tuple(deliverable.deliverable_type for deliverable in first) == MVP_DELIVERABLE_TYPES
    assert {deliverable.id for deliverable in second} == {deliverable.id for deliverable in first}
    assert ServiceEngagement.objects.count() == 1
    assert Asset.objects.count() == 10
    assert AssetVersion.objects.count() == 10
    assert ServiceDeliverable.objects.count() == 10
    assert all("quality_gate" in deliverable.metadata_json for deliverable in first)

    package = next(
        deliverable for deliverable in first if deliverable.deliverable_type == "campaign_launch_package"
    )
    content = _content_for(package)
    assert "Client Brief" in content
    assert "`client_brief`" in content
    assert "Performance Report" in content
    assert "`performance_report`" in content


def test_deployment_projection_feeds_gap_report_and_execution_receipt() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-deployment-state@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)
    StateProjection.objects.create(
        organization=org,
        company=company,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
        display_label="Whiteboard deployment",
        source_refs_json=[{"whiteboard_id": str(whiteboard.id), "policy_id": "atlas.launch"}],
        json_state={
            "whiteboard_id": str(whiteboard.id),
            "status": "partial",
            "channels": [
                {
                    "id": "email",
                    "label": "Email",
                    "status": "executed",
                    "receipt": {"result": {"status": "dry_run"}},
                },
                {
                    "id": "whatsapp",
                    "label": "WhatsApp",
                    "status": "blocked",
                    "blocked_reason_code": "connector_missing",
                },
            ],
        },
    )

    gap = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="connector_gap_report",
    )
    receipt = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="execution_receipt",
    )

    assert gap.metadata_json["source_refs"]["deployment"]["status"] == "partial"
    assert gap.metadata_json["blocked_by"] == ["whatsapp"]
    gap_content = _content_for(gap)
    receipt_content = _content_for(receipt)
    assert "Email" in gap_content
    assert "WhatsApp" in gap_content
    assert "connector_missing" in gap_content
    assert "Email" in receipt_content
    assert "dry_run" in receipt_content


def test_performance_projection_feeds_performance_report() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-performance-state@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)
    metric_snapshot_id = str(uuid4())
    report_run_id = str(uuid4())
    evaluation_id = str(uuid4())
    StateProjection.objects.create(
        organization=org,
        company=company,
        projection_type=f"whiteboard_performance:{whiteboard.id}",
        display_label="Whiteboard performance",
        source_refs_json=[{"whiteboard_id": str(whiteboard.id), "policy_id": "atlas.performance"}],
        json_state={
            "status": "evaluated",
            "metric_snapshot_id": metric_snapshot_id,
            "report_run_id": report_run_id,
            "evaluation_id": evaluation_id,
        },
    )

    report = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="performance_report",
    )

    assert report.metadata_json["source_refs"]["performance"]["metric_snapshot_id"] == metric_snapshot_id
    content = _content_for(report)
    assert metric_snapshot_id in content
    assert report_run_id in content
    assert evaluation_id in content


def test_service_deliverable_payload_includes_safe_metadata_and_latest_asset_version() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-payload@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner)
    deliverable = assemble_atlas_deliverable(
        whiteboard=whiteboard,
        user=owner,
        deliverable_type="strategy_brief",
    )
    deliverable.metadata_json = {
        **deliverable.metadata_json,
        "api_key": "secret",
        "customer_note": "Bearer operator-token",
        "evidence_link": "https://internal.example/report?token=secret",
        "internal_context": {"token": "operator-token"},
        "private_note": "operator-only",
    }
    deliverable.save(update_fields=["metadata_json", "updated_at"])

    payload = service_deliverable_payload(deliverable)
    internal_payload = service_deliverable_payload(deliverable, include_internal=True)

    assert payload["metadata"]["source"] == "atlas_deliverable_assembly"
    assert payload["metadata"]["deliverable_type"] == "strategy_brief"
    assert "api_key" not in payload["metadata"]
    assert "customer_note" not in payload["metadata"]
    assert "evidence_link" not in payload["metadata"]
    assert "internal_context" not in payload["metadata"]
    assert "private_note" not in payload["metadata"]
    assert "checks" not in payload["metadata"]["quality_gate"]
    assert "blockers" not in payload["metadata"]["quality_gate"]
    assert "warnings" not in payload["metadata"]["quality_gate"]
    assert internal_payload["metadata"]["quality_gate"]["checks"]
    assert "customer_note" not in internal_payload["metadata"]
    assert "evidence_link" not in internal_payload["metadata"]
    assert "internal_context" not in internal_payload["metadata"]
    assert payload["latest_asset_version_id"] == deliverable.metadata_json["asset_version_id"]
    assert payload["latest_asset_version_uri"].startswith("forgegraph://assets/")
    assert payload["latest_asset_version_mime_type"] == "text/markdown"
