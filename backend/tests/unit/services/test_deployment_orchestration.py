from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from django.utils import timezone

from application.services.deployment_orchestration import (
    DeploymentOrchestrationError,
    list_deployment_state,
    prepare_deployment_for_whiteboard,
)
from application.services.operating_model_packs import install_pack_for_company
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    AssetVersion,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    CompanySignal,
    Graph,
    GraphVersion,
    OperatingModelPackRelease,
    Organization,
    OrganizationMembership,
    Run,
    StateProjection,
    TaskRoutingRecord,
    ToolExecution,
    User,
    WorkWhiteboard,
)
from tests.fixtures.deployment_policies import (
    atlas_launch_deployment_policy,
    non_marketing_deployment_policy,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(Graph, Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"))
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    return company


def _assign(org: Organization, company: Graph, user: User, role: str = "member") -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _whiteboard(company: Graph, owner: User, *, status: str = WorkWhiteboard.STATUS_IN_APPROVAL) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=company.organization,
        company=company,
        status=status,
        request_type="service_request",
        client_name=company.name,
        request_summary="Prepare configured deployment.",
        objective="Prepare deployment through configured policy.",
        completion_score=100,
        created_by=owner,
    )


def _install_policy_pack(
    *,
    company: Graph,
    user: User,
    policy: dict[str, object],
    connectors: list[str] | None = None,
) -> None:
    install_pack_for_company(
        company=company,
        user=user,
        pack_id="digital_marketing_pro.v1",
        config={
            "skip_graph_version": True,
            "deployment_policies": [policy],
            "available_connectors": list(connectors or []),
        },
        role="primary",
    )


def _install_synthetic_policy(company: Graph, policy: dict[str, object]) -> None:
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"synthetic-pack:{company.id}",
        base_pack_id=str(policy["pack_id"]),
        version="1.0.0",
        display_name="Synthetic Deployment Pack",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={"deployment_policies": [policy]},
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=company.organization,
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id=str(policy["pack_id"]),
        role="primary",
        status="active",
        public_config_json={"deployment_policies": [policy]},
    )


def _approval(whiteboard: WorkWhiteboard, owner: User, *, status: str = "approved") -> ApprovalTask:
    version = GraphVersion.objects.create(
        graph=whiteboard.company,
        version=1,
        graph_json={"nodes": [], "edges": [], "source": "deployment-test"},
    )
    run = Run.objects.create(
        owner=owner,
        organization=whiteboard.organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
    )
    return ApprovalTask.objects.create(
        run=run,
        node_id=f"deployment-approval:{whiteboard.id}",
        status=status,
        payload={"whiteboard_id": str(whiteboard.id), "source": "deployment-test"},
        result={"approved": status == "approved"},
        resolved_at=timezone.now() if status == "approved" else None,
    )


def _asset(whiteboard: WorkWhiteboard, *, output_type: str = "asset", asset_type: str = "memo") -> Asset:
    asset = Asset.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        title=f"{output_type.title()} deployment asset",
        asset_type=asset_type,
        source_key=f"whiteboard:{whiteboard.id}:deployment-test:{output_type}",
        created_by_type="system",
        metadata_json={"whiteboard_id": str(whiteboard.id), "output_type": output_type, "artifact_type": output_type},
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri=f"forgegraph://assets/{asset.id}/deployment-test",
        content_hash=f"hash-{asset.id}".replace("-", "")[:64],
        mime_type="application/json",
        provenance_json={"inline_content": {"whiteboard_id": str(whiteboard.id)}},
    )
    asset.metadata_json = {**asset.metadata_json, "canonical_asset_version_id": str(version.id)}
    asset.save(update_fields=["metadata_json", "updated_at"])
    return asset


def test_atlas_policy_prepares_channels_and_email_sandbox_receipt() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-atlas@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    _install_policy_pack(company=company, user=owner, policy=policy, connectors=["email_service_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    channels = {item["id"]: item for item in contract["channels"]}

    assert contract["policy_id"] == policy["policy_id"]
    assert contract["status"] == "partial"
    assert channels["email"]["status"] == "executed"
    assert channels["email"]["tool_execution_id"]
    assert channels["email"]["receipt"]["result"]["status"] == "captured"
    assert channels["whatsapp"]["status"] == "blocked"
    assert channels["whatsapp"]["blocked_reason_code"] == "connector_missing"
    assert ToolExecution.objects.filter(tool_name="dmp.email_draft_send_schedule").count() == 1
    assert CompanySignal.objects.filter(company=company, metadata_json__reason_code="connector_missing").exists()
    assert TaskRoutingRecord.objects.filter(company=company, metadata_json__blocked_reason_code="connector_missing").exists()
    assert StateProjection.objects.filter(
        company=company,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
    ).exists()


def test_missing_approval_blocks_deployment_without_tool_execution() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-approval@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_policy_pack(
        company=company,
        user=owner,
        policy=atlas_launch_deployment_policy(),
        connectors=["email_service_connector"],
    )
    whiteboard = _whiteboard(company, owner)
    _asset(whiteboard, output_type="asset")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["status"] == "blocked"
    assert {item["blocked_reason_code"] for item in contract["channels"]} == {"approval_required"}
    assert not ToolExecution.objects.exists()
    assert CompanySignal.objects.filter(company=company, metadata_json__reason_code="approval_required").exists()


def test_duplicate_prepare_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-idempotent@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_policy_pack(company=company, user=owner, policy=atlas_launch_deployment_policy(), connectors=["email_service_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")

    first = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    second = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert first["channels"][0]["tool_execution_id"] == second["channels"][0]["tool_execution_id"]
    assert ToolExecution.objects.filter(tool_name="dmp.email_draft_send_schedule").count() == 1
    assert CompanySignal.objects.filter(company=company).count() == 5
    assert TaskRoutingRecord.objects.filter(company=company, metadata_json__blocked_reason_code="connector_missing").count() == 5


def test_other_client_cannot_access_deployment_state() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-owner@example.com", "owner")
    other = _user(org, "deployment-other@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other, "viewer")
    _install_policy_pack(company=company, user=owner, policy=atlas_launch_deployment_policy())
    whiteboard = _whiteboard(company, owner)

    with pytest.raises(DeploymentOrchestrationError, match="access"):
        list_deployment_state(user=other, whiteboard=whiteboard)


def test_non_marketing_policy_works_without_channel_specific_logic() -> None:
    org = Organization.objects.create(name="Legal Ops")
    owner = _user(org, "deployment-legal@example.com", "owner")
    company = _company(org, owner, name="Legal Client")
    _assign(org, company, owner, "member")
    policy = non_marketing_deployment_policy()
    _install_synthetic_policy(company, policy)
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="document", asset_type="document")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["policy_id"] == "legal_ops.v1.contract_delivery"
    assert contract["channels"][0]["id"] == "client_portal"
    assert contract["channels"][0]["status"] == "ready"
    assert not ToolExecution.objects.exists()


def test_core_deployment_service_has_no_policy_channel_literals() -> None:
    service_path = Path(__file__).resolve().parents[3] / "application" / "services" / "deployment_orchestration.py"
    service_text = service_path.read_text(encoding="utf-8")

    for forbidden in (
        "atlas_agency_ops",
        "whatsapp",
        "instagram",
        "facebook",
        "tiktok",
        "landing_page",
        "email_service_connector",
        "dmp.email_draft_send_schedule",
        "cms_landing_page_connector",
    ):
        assert forbidden not in service_text
