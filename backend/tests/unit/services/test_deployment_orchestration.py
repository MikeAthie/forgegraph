from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.deployment_orchestration import (
    DeploymentOrchestrationError,
    list_deployment_state,
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
    non_marketing_messaging_deployment_policy,
    non_marketing_social_deployment_policy,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
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


def _whiteboard(
    company: Graph, owner: User, *, status: str = WorkWhiteboard.STATUS_IN_APPROVAL
) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
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


def _install_synthetic_policy(
    company: Graph,
    policy: dict[str, object],
    *,
    connectors: list[str] | None = None,
) -> None:
    available_connectors = list(connectors or ["email_connector"])
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"synthetic-pack:{company.id}",
        base_pack_id=str(policy["pack_id"]),
        version="1.0.0",
        display_name="Synthetic Deployment Pack",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={
            "deployment_policies": [policy],
            "available_connectors": available_connectors,
        },
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=required_company_organization(company),
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id=str(policy["pack_id"]),
        role="primary",
        status="active",
        public_config_json={
            "deployment_policies": [policy],
            "available_connectors": available_connectors,
        },
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


def _asset(
    whiteboard: WorkWhiteboard, *, output_type: str = "asset", asset_type: str = "memo"
) -> Asset:
    asset = Asset.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        title=f"{output_type.title()} deployment asset",
        asset_type=asset_type,
        source_key=f"whiteboard:{whiteboard.id}:deployment-test:{output_type}",
        created_by_type="system",
        metadata_json={
            "whiteboard_id": str(whiteboard.id),
            "output_type": output_type,
            "artifact_type": output_type,
        },
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
    _install_policy_pack(company=company, user=owner, policy=policy, connectors=["email_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    channels = {item["id"]: item for item in contract["channels"]}

    assert contract["policy_id"] == policy["policy_id"]
    assert contract["status"] == "partial"
    assert channels["email"]["status"] == "executed"
    assert channels["email"]["tool_execution_id"]
    assert channels["email"]["receipt"]["result"]["status"] == "dry_run"
    assert channels["email"]["receipt"]["result"]["mode"] == "dry_run"
    assert channels["email"]["receipt"]["result"]["evidence_mode"] == "sandbox"
    assert channels["whatsapp"]["status"] == "blocked"
    assert channels["whatsapp"]["blocked_reason_code"] == "connector_missing"
    assert ToolExecution.objects.filter(tool_name="email.send_dry_run").count() == 1
    assert CompanySignal.objects.filter(
        company=company,
        signal_kind="capability_gap",
        domain_context="deployment",
        metadata_json__reason_code="connector_missing",
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company, metadata_json__blocked_reason_code="connector_missing"
    ).exists()
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
        connectors=["email_connector"],
    )
    whiteboard = _whiteboard(company, owner)
    _asset(whiteboard, output_type="asset")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["status"] == "blocked"
    assert {item["blocked_reason_code"] for item in contract["channels"]} == {"approval_required"}
    assert not ToolExecution.objects.exists()
    assert CompanySignal.objects.filter(
        company=company,
        signal_kind="capability_gap",
        domain_context="deployment",
        metadata_json__reason_code="approval_required",
    ).exists()


def test_duplicate_prepare_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-idempotent@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_policy_pack(
        company=company,
        user=owner,
        policy=atlas_launch_deployment_policy(),
        connectors=["email_connector"],
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")

    first = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    second = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert first["channels"][0]["tool_execution_id"] == second["channels"][0]["tool_execution_id"]
    assert ToolExecution.objects.filter(tool_name="email.send_dry_run").count() == 1
    assert CompanySignal.objects.filter(company=company).count() == 5
    assert (
        TaskRoutingRecord.objects.filter(
            company=company, metadata_json__blocked_reason_code="connector_missing"
        ).count()
        == 5
    )


def test_whatsapp_dry_run_creates_sanitized_tool_execution_receipt() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-whatsapp-dry-run@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    _install_policy_pack(
        company=company,
        user=owner,
        policy=policy,
        connectors=["email_connector", "whatsapp_connector"],
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")
    _asset(whiteboard, output_type="publication_draft")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)
    channels = {item["id"]: item for item in contract["channels"]}

    assert channels["whatsapp"]["status"] == "executed"
    assert channels["whatsapp"]["receipt"]["result"]["mode"] == "dry_run"
    assert channels["whatsapp"]["receipt"]["result"]["evidence_mode"] == "sandbox"
    assert channels["whatsapp"]["receipt"]["result"]["recipient_hashes"] == []
    assert ToolExecution.objects.filter(tool_name="whatsapp.send_dry_run").count() == 1
    persisted = str(ToolExecution.objects.get(tool_name="whatsapp.send_dry_run").result_json)
    assert "+1555" not in persisted


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="open_wa_web",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_WEB_AUTOMATION_ENABLED=False,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_open_wa_disabled_blocks_before_provider_call_and_routes_work() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-whatsapp-disabled@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    policy["channels"][1]["tool_id"] = "whatsapp.web_automation_send"  # type: ignore[index]
    policy["channels"][1]["allow_live_execution"] = True  # type: ignore[index]
    _install_policy_pack(
        company=company, user=owner, policy=policy, connectors=["whatsapp_connector"]
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="publication_draft")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="whatsapp",
        dry_run=False,
        inputs={
            "provider": "open_wa_web",
            "to": ["+15550101234"],
            "text": "Approved notice",
            "operator_confirmed": True,
        },
    )

    assert channel["status"] == "blocked"
    assert channel["blocked_reason_code"] == "whatsapp_web_automation_disabled"
    assert not ToolExecution.objects.filter(tool_name="whatsapp.web_automation_send").exists()
    assert CompanySignal.objects.filter(
        company=company,
        metadata_json__reason_code="whatsapp_web_automation_disabled",
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__blocked_reason_code="whatsapp_web_automation_disabled",
    ).exists()


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="open_wa_web",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_WEB_AUTOMATION_ENABLED=True,
    WHATSAPP_WEB_AUTOMATION_SESSION_REF="",
    WHATSAPP_WEB_AUTOMATION_SIDECAR_URL="",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_missing_web_automation_session_blocks_before_provider_call() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-whatsapp-session@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    policy["channels"][1]["tool_id"] = "whatsapp.web_automation_send"  # type: ignore[index]
    policy["channels"][1]["allow_live_execution"] = True  # type: ignore[index]
    _install_policy_pack(
        company=company, user=owner, policy=policy, connectors=["whatsapp_connector"]
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="publication_draft")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="whatsapp",
        dry_run=False,
        inputs={
            "provider": "open_wa_web",
            "to": ["+15550101234"],
            "text": "Approved notice",
            "operator_confirmed": True,
        },
    )

    assert channel["status"] == "blocked"
    assert channel["blocked_reason_code"] == "whatsapp_session_missing"
    assert not ToolExecution.objects.filter(tool_name="whatsapp.web_automation_send").exists()


@override_settings(
    EMAIL_CONNECTOR_PROVIDER="resend",
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
    RESEND_API_KEY="",
)
def test_missing_email_credentials_block_before_provider_call_and_route_work() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-email-credentials@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    policy["channels"][0]["allow_live_execution"] = True  # type: ignore[index]
    policy["channels"][0]["requires_unsubscribe_footer"] = False  # type: ignore[index]
    _install_policy_pack(company=company, user=owner, policy=policy, connectors=["email_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="asset")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="email",
        dry_run=False,
        inputs={
            "provider": "resend",
            "from_email": "sender@example.com",
            "to": ["allowed@example.com"],
            "subject": "Approved notice",
            "text": "Approved notice",
        },
    )

    assert channel["status"] == "blocked"
    assert channel["blocked_reason_code"] == "email_credentials_missing"
    assert not ToolExecution.objects.filter(tool_name="email.send_dry_run").exists()
    assert CompanySignal.objects.filter(
        company=company, metadata_json__reason_code="email_credentials_missing"
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__blocked_reason_code="email_credentials_missing",
    ).exists()


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

    assert contract["policy_id"] == "legal_ops.v1.client_notice_delivery"
    assert contract["channels"][0]["id"] == "client_notice_email"
    assert contract["channels"][0]["status"] == "executed"
    assert ToolExecution.objects.filter(tool_name="email.send_dry_run").exists()


def test_non_marketing_messaging_policy_uses_same_generic_connector() -> None:
    org = Organization.objects.create(name="Legal Ops")
    owner = _user(org, "deployment-legal-message@example.com", "owner")
    company = _company(org, owner, name="Legal Client")
    _assign(org, company, owner, "member")
    policy = non_marketing_messaging_deployment_policy()
    _install_synthetic_policy(company, policy, connectors=["whatsapp_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="document", asset_type="document")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["policy_id"] == "legal_ops.v1.client_notice_messaging"
    assert contract["channels"][0]["id"] == "client_notice_message"
    assert contract["channels"][0]["status"] == "executed"
    assert ToolExecution.objects.filter(tool_name="whatsapp.send_dry_run").exists()


def test_social_dry_run_creates_sanitized_tool_execution_receipt() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-social-dry-run@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    _install_policy_pack(
        company=company, user=owner, policy=policy, connectors=["social_connector"]
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="publication_draft")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="instagram",
        dry_run=True,
        inputs={"caption": "Private approved social caption"},
    )

    assert channel["status"] == "executed"
    assert channel["receipt"]["result"]["mode"] == "dry_run"
    assert channel["receipt"]["result"]["evidence_mode"] == "sandbox"
    assert channel["receipt"]["result"]["caption_hash"].startswith("sha256:")
    assert ToolExecution.objects.filter(tool_name="social.publish_dry_run").exists()
    persisted = str(ToolExecution.objects.get(tool_name="social.publish_dry_run").result_json)
    assert "Private approved social caption" not in persisted


def test_social_manual_evidence_creates_tool_execution_only_when_policy_allows() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-social-manual@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    policy["channels"][2]["tool_id"] = "social.manual_publish_record"  # type: ignore[index]
    _install_policy_pack(
        company=company, user=owner, policy=policy, connectors=["social_connector"]
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="publication_draft")

    blocked = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="instagram",
        dry_run=True,
        inputs={
            "caption": "Private approved social caption",
            "external_post_url": "https://social.example/posts/1",
            "operator_confirmed": True,
        },
    )
    assert blocked["status"] == "blocked"
    assert blocked["blocked_reason_code"] == "manual_publish_evidence_not_allowed"
    assert not ToolExecution.objects.filter(tool_name="social.manual_publish_record").exists()

    allowed_company = _company(org, owner, name="Allowed Manual Social")
    _assign(org, allowed_company, owner, "member")
    allowed_policy = atlas_launch_deployment_policy()
    allowed_policy["channels"][2]["tool_id"] = "social.manual_publish_record"  # type: ignore[index]
    allowed_policy["channels"][2]["allow_manual_publish_evidence"] = True  # type: ignore[index]
    _install_policy_pack(
        company=allowed_company, user=owner, policy=allowed_policy, connectors=["social_connector"]
    )
    allowed_whiteboard = _whiteboard(allowed_company, owner)
    _approval(allowed_whiteboard, owner)
    _asset(allowed_whiteboard, output_type="publication_draft")
    executed = request_tool_execution_for_channel(
        user=owner,
        whiteboard=allowed_whiteboard,
        channel_id="instagram",
        dry_run=True,
        inputs={
            "caption": "Private approved social caption",
            "external_post_url": "https://social.example/posts/1",
            "operator_confirmed": True,
        },
    )

    assert executed["status"] == "executed"
    assert executed["receipt"]["result"]["mode"] == "manual_publish_record"
    assert executed["receipt"]["result"]["evidence_mode"] == "manual_publish"
    persisted = str(
        ToolExecution.objects.get(
            run__graph_version__graph=allowed_company, tool_name="social.manual_publish_record"
        ).result_json
    )
    assert "https://social.example" not in persisted
    assert "Private approved social caption" not in persisted


@override_settings(
    SOCIAL_CONNECTOR_PROVIDER="meta_graph",
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
    META_GRAPH_ACCESS_TOKEN="",
)
def test_missing_meta_credentials_block_before_provider_call_and_route_work() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "deployment-social-credentials@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_deployment_policy()
    policy["channels"][2]["tool_id"] = "social.provider_publish"  # type: ignore[index]
    policy["channels"][2]["allow_live_execution"] = True  # type: ignore[index]
    policy["channels"][2]["allow_provider_publish"] = True  # type: ignore[index]
    _install_policy_pack(
        company=company, user=owner, policy=policy, connectors=["social_connector"]
    )
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="publication_draft")

    channel = request_tool_execution_for_channel(
        user=owner,
        whiteboard=whiteboard,
        channel_id="instagram",
        dry_run=False,
        inputs={
            "provider": "meta_graph",
            "account_id": "account-123",
            "caption": "Private approved social caption",
            "media_url": "https://cdn.example/private.jpg",
            "compliance_gate_passed": True,
            "originality_check_passed": True,
        },
    )

    assert channel["status"] == "blocked"
    assert channel["blocked_reason_code"] == "social_credentials_missing"
    assert not ToolExecution.objects.filter(tool_name="social.provider_publish").exists()
    assert CompanySignal.objects.filter(
        company=company, metadata_json__reason_code="social_credentials_missing"
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__blocked_reason_code="social_credentials_missing",
    ).exists()


def test_non_marketing_social_policy_uses_same_generic_connector() -> None:
    org = Organization.objects.create(name="Municipal Ops")
    owner = _user(org, "deployment-municipal-social@example.com", "owner")
    company = _company(org, owner, name="Municipal Client")
    _assign(org, company, owner, "member")
    policy = non_marketing_social_deployment_policy()
    _install_synthetic_policy(company, policy, connectors=["social_connector"])
    whiteboard = _whiteboard(company, owner)
    _approval(whiteboard, owner)
    _asset(whiteboard, output_type="document", asset_type="document")

    contract = prepare_deployment_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["policy_id"] == "municipal_ops.v1.community_notice_social_publish"
    assert contract["channels"][0]["id"] == "community_notice_social"
    assert contract["channels"][0]["status"] == "executed"
    assert ToolExecution.objects.filter(tool_name="social.publish_dry_run").exists()


def test_core_deployment_service_has_no_policy_channel_literals() -> None:
    service_path = (
        Path(__file__).resolve().parents[3]
        / "application"
        / "services"
        / "deployment_orchestration.py"
    )
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
