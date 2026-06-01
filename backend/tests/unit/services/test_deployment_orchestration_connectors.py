from __future__ import annotations

from typing import cast

import pytest
from django.utils import timezone

from application.services.deployment_orchestration import (
    prepare_deployment_for_whiteboard,
    request_tool_execution_for_channel,
)
from application.services.operating_model_packs import install_pack_for_company
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    AssetVersion,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanySignal,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    Run,
    TaskRoutingRecord,
    ToolExecution,
    User,
    WorkWhiteboard,
)
from tests.fixtures.connector_policies import (
    accounting_statement_delivery_policy,
    atlas_connector_test_deployment_policy,
)
from tests.helpers.connector_contracts import (
    assert_blocked_before_provider_call_routed,
    assert_success_receipt_contract,
    assert_tool_execution_receipt_sanitized,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str) -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=org, user=user, role="owner", is_default=True
    )
    return user


def _company(org: Organization, owner: User, *, name: str = "Connector Client") -> Graph:
    company = cast(Graph, Graph.objects.create(owner=owner, organization=org, name=name))
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=owner,
        role="member",
        status="active",
    )
    return company


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_IN_APPROVAL,
        request_type="service_request",
        client_name=company.name,
        request_summary="Connector contract deployment.",
        objective="Exercise connector testing contract.",
        completion_score=100,
        created_by=owner,
    )


def _approval(whiteboard: WorkWhiteboard, owner: User) -> ApprovalTask:
    version = GraphVersion.objects.create(
        graph=whiteboard.company, version=1, graph_json={"nodes": [], "edges": []}
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
        node_id=f"connector-approval:{whiteboard.id}",
        status="approved",
        payload={"whiteboard_id": str(whiteboard.id)},
        result={"approved": True},
        resolved_at=timezone.now(),
    )


def _asset(
    whiteboard: WorkWhiteboard, *, output_type: str = "asset", asset_type: str = "document"
) -> None:
    asset = Asset.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        title=f"{output_type.title()} connector asset",
        asset_type=asset_type,
        source_key=f"whiteboard:{whiteboard.id}:connector-test:{output_type}",
        metadata_json={
            "whiteboard_id": str(whiteboard.id),
            "output_type": output_type,
            "artifact_type": output_type,
        },
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri=f"forgegraph://assets/{asset.id}/connector-test",
        content_hash=f"hash-{asset.id}".replace("-", "")[:64],
        mime_type="application/json",
        provenance_json={"inline_content": {"whiteboard_id": str(whiteboard.id)}},
    )
    asset.metadata_json = {**asset.metadata_json, "canonical_asset_version_id": str(version.id)}
    asset.save(update_fields=["metadata_json", "updated_at"])


def _install_policy(
    company: Graph, owner: User, policy: dict[str, object], connectors: list[str]
) -> None:
    install_pack_for_company(
        company=company,
        user=owner,
        pack_id="digital_marketing_pro.v1",
        config={
            "skip_graph_version": True,
            "deployment_policies": [policy],
            "available_connectors": connectors,
        },
        role="primary",
    )


def test_connector_policy_fixture_records_email_receipt_and_honest_missing_connector_blocks() -> (
    None
):
    org = Organization.objects.create(name="Connector Test Org")
    owner = _user(org, "connector-deployment@example.com")
    company = _company(org, owner)
    _install_policy(company, owner, atlas_connector_test_deployment_policy(), ["email_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")
    _asset(whiteboard, output_type="publication_draft")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    channels = {channel["id"]: channel for channel in contract["channels"]}

    assert channels["email"]["status"] == "executed"
    assert_success_receipt_contract(
        channels["email"]["receipt"]["result"], expected_evidence_mode="sandbox"
    )
    assert channels["whatsapp"]["status"] == "blocked"
    assert channels["instagram"]["status"] == "blocked"
    assert channels["facebook"]["status"] == "blocked"
    assert channels["landing_page"]["status"] == "blocked"
    assert {
        channels[key]["blocked_reason_code"]
        for key in ("whatsapp", "instagram", "facebook", "landing_page")
    } == {"connector_missing"}
    email_execution = ToolExecution.objects.get(
        run__graph_version__graph=company, tool_name="email.send_dry_run"
    )
    assert ToolExecution.objects.filter(run__graph_version__graph=company).count() == 1
    assert_tool_execution_receipt_sanitized(email_execution)
    assert_blocked_before_provider_call_routed(company=company, reason_code="connector_missing")


def test_non_marketing_connector_fixture_uses_same_email_connector_contract() -> None:
    org = Organization.objects.create(name="Accounting Connector Org")
    owner = _user(org, "connector-accounting@example.com")
    company = _company(org, owner, name="Accounting Client")
    _install_policy(company, owner, accounting_statement_delivery_policy(), ["email_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="document")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["policy_id"] == "accounting_ops.v1.statement_delivery"
    assert contract["channels"][0]["id"] == "statement_email"
    assert contract["channels"][0]["status"] == "executed"
    assert_success_receipt_contract(
        contract["channels"][0]["receipt"]["result"], expected_evidence_mode="sandbox"
    )


def test_provider_publish_without_approval_blocks_without_provider_failure_receipt() -> None:
    org = Organization.objects.create(name="Connector Approval Org")
    owner = _user(org, "connector-no-approval@example.com")
    company = _company(org, owner)
    policy = atlas_connector_test_deployment_policy()
    policy["channels"][2]["tool_id"] = "social.provider_publish"  # type: ignore[index]
    policy["channels"][2]["allow_provider_publish"] = True  # type: ignore[index]
    policy["channels"][2]["allow_live_execution"] = True  # type: ignore[index]
    _install_policy(company, owner, policy, ["social_connector"])
    whiteboard = _whiteboard(company, owner)
    _asset(whiteboard, output_type="publication_draft")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="instagram",
        dry_run=False,
        inputs={
            "provider": "fake",
            "platform": "configured_platform",
            "account_id": "account-123",
            "asset_id": "asset-public-safe",
            "caption": "Private caption",
            "content_approved": True,
        },
    )

    assert channel["status"] == "blocked"
    assert channel["blocked_reason_code"] == "approval_required"
    assert not ToolExecution.objects.filter(run__graph_version__graph=company).exists()
    assert CompanySignal.objects.filter(
        company=company, metadata_json__reason_code="approval_required"
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__blocked_reason_code="approval_required",
    ).exists()
