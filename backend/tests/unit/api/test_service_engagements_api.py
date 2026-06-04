from __future__ import annotations

from datetime import date
from typing import cast
from uuid import uuid4

import pytest

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AuditLog,
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    Organization,
    OrganizationMembership,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _company(user: User, name: str) -> Graph:
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


def _member_in_org(owner: User, *, role: str = "viewer") -> User:
    organization = owner.default_organization
    assert organization is not None
    member = User.objects.create_user(
        email=f"service-member-{uuid4().hex}@example.com",
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


def _catalog_item(user: User, *, slug: str = "growth-audit") -> ServiceCatalogItem:
    organization = user.default_organization
    assert organization is not None
    return ServiceCatalogItem.objects.create(
        organization=organization,
        slug=slug,
        title="Growth Audit",
        description="Customer-facing audit service.",
        status="active",
        visibility="customer",
        required_pack_ids_json=["atlas.growth.v1"],
        intake_schema_json={"type": "object"},
        deliverables_schema_json=[{"type": "report"}],
        created_by=user,
    )


def _engagement(user: User, company: Graph) -> ServiceEngagement:
    return ServiceEngagement.objects.create(
        organization=_organization(company),
        company=company,
        catalog_item=_catalog_item(user, slug=f"service-{uuid4().hex}"),
        status="in_progress",
        customer_status="working",
        requested_by=user,
    )


def _artifact(company: Graph, *, title: str = "Service artifact") -> Asset:
    return Asset.objects.create(
        organization=_organization(company),
        company=company,
        title=title,
        asset_type="deliverable",
        created_by_type="system",
    )


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=_organization(company),
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


def test_service_catalog_engagement_and_deliverable_facade(authenticated_client, user):
    company = _company(user, "Legacy Eyewear")

    catalog_response = authenticated_client.post(
        "/api/service-catalog",
        {
            "slug": "legacy-growth-audit",
            "title": "Growth Audit",
            "description": "Audit packaged as a customer-facing service.",
            "status": "active",
            "visibility": "customer",
            "required_pack_ids": ["atlas.growth.v1"],
            "intake_schema": {"type": "object", "properties": {"site": {"type": "string"}}},
            "deliverables_schema": [{"type": "report", "title": "Audit report"}],
        },
        format="json",
    )
    assert catalog_response.status_code == 201
    service = catalog_response.data["data"]["service"]
    assert service["required_pack_ids"] == ["atlas.growth.v1"]

    engagement_response = authenticated_client.post(
        "/api/service-engagements",
        {
            "company_id": str(company.id),
            "catalog_item_id": service["id"],
            "customer_status": "intake_needed",
            "intake_data": {"site": "https://legacy.example"},
            "internal_notes": "Operator-only setup note.",
        },
        format="json",
    )
    assert engagement_response.status_code == 201
    engagement = engagement_response.data["data"]["engagement"]
    assert engagement["company_id"] == str(company.id)
    assert engagement["service_title"] == "Growth Audit"
    assert engagement["required_pack_ids"] == ["atlas.growth.v1"]
    assert engagement["internal_notes"] == "Operator-only setup note."

    artifact = Asset.objects.create(
        organization=_organization(company),
        company=company,
        title="Growth audit report",
        asset_type="deliverable",
        created_by_type="system",
    )
    deliverable_response = authenticated_client.post(
        f"/api/service-engagements/{engagement['id']}/deliverables",
        {
            "title": "Growth audit report",
            "deliverable_type": "report",
            "status": "delivered",
            "visibility": "customer",
            "artifact_id": str(artifact.id),
            "summary": "Ready for customer review.",
            "metadata": {"private_source_path": "s3://internal/report.md"},
        },
        format="json",
    )
    assert deliverable_response.status_code == 201
    deliverable = deliverable_response.data["data"]["deliverable"]
    assert deliverable["artifact_id"] == str(artifact.id)
    assert "private_source_path" not in str(deliverable)
    assert deliverable["metadata"]["quality_gate"]["status"] == "fail"
    stored_deliverable = ServiceDeliverable.objects.get(id=deliverable["id"])
    assert stored_deliverable.metadata_json["quality_gate"]["status"] == "fail"
    assert ServiceEngagement.objects.filter(company=company).count() == 1
    assert ServiceDeliverable.objects.filter(company=company).count() == 1


def test_service_engagements_are_company_assignment_filtered(api_client, user):
    visible = _company(user, "Visible Client")
    hidden = _company(user, "Hidden Client")
    member = _member_in_org(user, role="viewer")
    service = _catalog_item(user)
    for company in [visible, hidden]:
        CompanyAccessPolicy.objects.create(
            organization=_organization(company),
            company=company,
            assignment_required=True,
            org_admin_access_enabled=False,
        )
    CompanyAssignment.objects.create(
        organization=_organization(visible),
        company=visible,
        user=member,
        role="viewer",
        status="active",
        created_by=user,
    )
    visible_engagement = ServiceEngagement.objects.create(
        organization=_organization(visible),
        company=visible,
        catalog_item=service,
        status="in_progress",
        customer_status="working",
        public_summary="Visible work.",
        internal_notes="Hidden from customer viewer.",
        requested_by=user,
    )
    hidden_engagement = ServiceEngagement.objects.create(
        organization=_organization(hidden),
        company=hidden,
        catalog_item=service,
        status="in_progress",
        customer_status="working",
        requested_by=user,
    )

    api_client.force_authenticate(user=member)
    list_response = api_client.get("/api/service-engagements")
    assert list_response.status_code == 200
    engagements = list_response.data["data"]["engagements"]
    assert {item["id"] for item in engagements} == {str(visible_engagement.id)}
    assert "internal_notes" not in engagements[0]

    visible_detail = api_client.get(f"/api/service-engagements/{visible_engagement.id}")
    hidden_detail = api_client.get(f"/api/service-engagements/{hidden_engagement.id}")
    assert visible_detail.status_code == 200
    assert hidden_detail.status_code == 404


def test_service_deliverable_rejects_wrong_company_artifact(authenticated_client, user):
    company = _company(user, "Service Client")
    other_company = _company(user, "Other Client")
    service = _catalog_item(user)
    engagement = ServiceEngagement.objects.create(
        organization=_organization(company),
        company=company,
        catalog_item=service,
        status="in_progress",
        customer_status="working",
        requested_by=user,
    )
    other_artifact = Asset.objects.create(
        organization=_organization(other_company),
        company=other_company,
        title="Other company report",
        asset_type="deliverable",
        created_by_type="system",
    )

    response = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/deliverables",
        {
            "title": "Wrong artifact",
            "artifact_id": str(other_artifact.id),
            "status": "ready",
        },
        format="json",
    )

    assert response.status_code == 404
    assert ServiceDeliverable.objects.count() == 0


def test_service_deliverable_can_reference_company_report(authenticated_client, user):
    company = _company(user, "Report Client")
    service = _catalog_item(user)
    engagement = ServiceEngagement.objects.create(
        organization=_organization(company),
        company=company,
        catalog_item=service,
        status="in_progress",
        customer_status="working",
        requested_by=user,
    )
    report = ReportRun.objects.create(
        organization=_organization(company),
        company=company,
        report_template_id="service_report_v1",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        generated_sections_json={"summary": "Delivered"},
        created_by=user,
    )

    response = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/deliverables",
        {
            "title": "Monthly service report",
            "report_run_id": str(report.id),
            "status": "ready",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["data"]["deliverable"]["report_run_id"] == str(report.id)


def test_service_deliverable_action_mark_ready_runs_quality_gate(authenticated_client, user):
    company = _company(user, "Lifecycle Ready Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Launch report",
        deliverable_type="report",
        status="draft",
        visibility="customer",
        artifact=_artifact(company),
        summary="Ready for customer review.",
        metadata_json={"source_refs": {"whiteboard": "wb_123"}},
        created_by=user,
    )

    response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "mark_ready"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.data["data"]["deliverable"]
    deliverable.refresh_from_db()
    assert deliverable.status == "ready"
    assert payload["status"] == "ready"
    assert deliverable.metadata_json["quality_gate"]["status"] == "pass"
    assert payload["metadata"]["quality_gate"]["checks"]
    assert AuditLog.objects.filter(
        action="service_deliverable.mark_ready",
        resource_type="service_deliverable",
        resource_id=str(deliverable.id),
    ).exists()


def test_service_deliverable_action_submit_for_approval(authenticated_client, user):
    company = _company(user, "Lifecycle Approval Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Approval Packet",
        deliverable_type="approval_packet",
        status="ready",
        visibility="customer",
        artifact=_artifact(company),
        summary="Approval packet ready for customer review.",
        metadata_json={"requires_approval": True, "source_refs": {"approval": "packet_123"}},
        created_by=user,
    )

    response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "submit_for_approval"},
        format="json",
    )

    assert response.status_code == 200
    deliverable.refresh_from_db()
    engagement.refresh_from_db()
    assert deliverable.status == "in_review"
    assert engagement.status == "waiting_on_customer"
    assert engagement.customer_status == "review_ready"


def test_service_deliverable_action_deliver_to_client_sets_delivered_at(
    authenticated_client, user
):
    company = _company(user, "Lifecycle Delivered Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Monthly report",
        deliverable_type="performance_report",
        status="ready",
        visibility="customer",
        artifact=_artifact(company),
        summary="Monthly performance report ready for delivery.",
        metadata_json={"source_refs": {"performance": {"status": "evaluated"}}},
        created_by=user,
    )

    response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "deliver_to_client"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.data["data"]["deliverable"]
    deliverable.refresh_from_db()
    assert deliverable.status == "delivered"
    assert deliverable.delivered_at is not None
    assert payload["status"] == "delivered"
    assert payload["delivered_at"] is not None


def test_service_deliverable_action_deliver_to_client_requires_approval_submission(
    authenticated_client, user
):
    company = _company(user, "Lifecycle Approval Guard Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Approval packet",
        deliverable_type="approval_packet",
        status="ready",
        visibility="customer",
        artifact=_artifact(company),
        summary="Approval packet ready for customer review.",
        metadata_json={"requires_approval": True, "source_refs": {"approval": "packet_123"}},
        created_by=user,
    )

    blocked_response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "deliver_to_client"},
        format="json",
    )
    assert blocked_response.status_code == 400
    assert blocked_response.data["error"]["code"] == "APPROVAL_REQUIRED"
    deliverable.refresh_from_db()
    assert deliverable.status == "ready"

    approval_response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "submit_for_approval"},
        format="json",
    )
    assert approval_response.status_code == 200

    delivery_response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "deliver_to_client"},
        format="json",
    )
    assert delivery_response.status_code == 200
    deliverable.refresh_from_db()
    assert deliverable.status == "delivered"


def test_service_deliverable_action_accept_only_after_delivered(authenticated_client, user):
    company = _company(user, "Lifecycle Accepted Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Accepted report",
        deliverable_type="report",
        status="ready",
        visibility="customer",
        artifact=_artifact(company),
        summary="Ready for customer review.",
        metadata_json={"source_refs": {"whiteboard": "wb_123"}},
        created_by=user,
    )

    invalid_response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "accept"},
        format="json",
    )
    assert invalid_response.status_code == 400
    assert invalid_response.data["error"]["code"] == "INVALID_DELIVERABLE_TRANSITION"

    deliverable.status = "delivered"
    deliverable.save(update_fields=["status", "updated_at"])
    response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "accept"},
        format="json",
    )

    assert response.status_code == 200
    deliverable.refresh_from_db()
    assert deliverable.status == "accepted"


def test_service_deliverable_action_deliver_to_client_blocks_quality_failures(
    authenticated_client, user
):
    company = _company(user, "Lifecycle Blocked Client")
    engagement = _engagement(user, company)
    deliverable = ServiceDeliverable.objects.create(
        organization=_organization(company),
        company=company,
        engagement=engagement,
        title="Blocked report",
        deliverable_type="report",
        status="ready",
        visibility="customer",
        summary="Ready wording without an artifact.",
        metadata_json={"source_refs": {"whiteboard": "wb_123"}},
        created_by=user,
    )

    response = authenticated_client.post(
        f"/api/service-deliverables/{deliverable.id}/actions",
        {"action": "deliver_to_client"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "QUALITY_GATE_BLOCKED"
    deliverable.refresh_from_db()
    assert deliverable.status == "ready"
    assert deliverable.delivered_at is None


def test_atlas_deliverables_batch_assemble_api(authenticated_client, user):
    company = _company(user, "Atlas Batch Client")
    whiteboard = _whiteboard(company, user)

    response = authenticated_client.post(
        f"/api/whiteboards/{whiteboard.id}/atlas-deliverables/assemble",
        {},
        format="json",
    )

    assert response.status_code == 200
    payload = response.data["data"]
    assert payload["engagement"]["company_id"] == str(company.id)
    assert payload["engagement"]["source_key"] == f"atlas-engagement:{whiteboard.id}"
    assert len(payload["deliverables"]) == 10
    assert {item["deliverable_type"] for item in payload["deliverables"]} == {
        "client_brief",
        "strategy_brief",
        "message_house",
        "launch_readiness_checklist",
        "connector_gap_report",
        "measurement_plan",
        "approval_packet",
        "execution_receipt",
        "performance_report",
        "campaign_launch_package",
    }
    assert ServiceEngagement.objects.filter(company=company).count() == 1
    assert ServiceDeliverable.objects.filter(company=company).count() == 10
    assert AuditLog.objects.filter(
        action="atlas_deliverables.assembled",
        resource_type="work_whiteboard",
        resource_id=str(whiteboard.id),
    ).exists()


def test_atlas_deliverables_single_assemble_api(authenticated_client, user):
    company = _company(user, "Atlas Single Client")
    whiteboard = _whiteboard(company, user)

    response = authenticated_client.post(
        f"/api/whiteboards/{whiteboard.id}/atlas-deliverables/assemble",
        {"deliverable_type": "performance_report"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.data["data"]
    assert payload["engagement"]["source_key"] == f"atlas-engagement:{whiteboard.id}"
    assert [item["deliverable_type"] for item in payload["deliverables"]] == [
        "performance_report"
    ]
    assert ServiceDeliverable.objects.get(company=company).deliverable_type == "performance_report"


def test_atlas_deliverables_assemble_api_rejects_unknown_type(authenticated_client, user):
    company = _company(user, "Atlas Invalid Client")
    whiteboard = _whiteboard(company, user)

    response = authenticated_client.post(
        f"/api/whiteboards/{whiteboard.id}/atlas-deliverables/assemble",
        {"deliverable_type": "not_real"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert ServiceEngagement.objects.count() == 0
    assert ServiceDeliverable.objects.count() == 0


def test_atlas_deliverables_assemble_api_hides_inaccessible_whiteboard(api_client, user):
    visible_company = _company(user, "Visible Atlas Client")
    hidden_company = _company(user, "Hidden Atlas Client")
    whiteboard = _whiteboard(hidden_company, user)
    member = _member_in_org(user, role="member")
    for company in [visible_company, hidden_company]:
        CompanyAccessPolicy.objects.create(
            organization=_organization(company),
            company=company,
            assignment_required=True,
            org_admin_access_enabled=False,
        )
    CompanyAssignment.objects.create(
        organization=_organization(visible_company),
        company=visible_company,
        user=member,
        role="member",
        status="active",
        created_by=user,
    )

    api_client.force_authenticate(user=member)
    response = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/atlas-deliverables/assemble",
        {},
        format="json",
    )

    assert response.status_code == 404
    assert ServiceEngagement.objects.count() == 0
    assert ServiceDeliverable.objects.count() == 0
