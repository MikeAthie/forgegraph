from __future__ import annotations

from typing import cast

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.email_connectors import FakeEmailProviderAdapter
from application.services.pack_tool_executions import (
    PackToolExecutionError,
    execute_deployment_connector_tool,
)
from application.services.social_connectors import FakeSocialProviderAdapter
from application.services.whatsapp_connectors import FakeWhatsAppAdapter
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    GatewayMediaArtifact,
    Graph,
    GraphVersion,
    OperatingModelPackRelease,
    Organization,
    Run,
    ToolExecution,
    User,
)
from tests.helpers.connector_contracts import (
    assert_success_receipt_contract,
    assert_tool_execution_company_scope,
    assert_tool_execution_receipt_sanitized,
)
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _company_run() -> tuple[Graph, User, Run]:
    org = Organization.objects.create(name="Connector Pack Org")
    user = User.objects.create_user(email="connector-pack@example.com", password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    company = cast(
        Graph, Graph.objects.create(owner=user, organization=org, name="Connector Pack Co")
    )
    version = GraphVersion.objects.create(
        graph=company, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(
        owner=user,
        organization=org,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
    )
    return company, user, run


def _install_policy_only_pack(company: Graph) -> None:
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"connector-contract-policy-only:{company.id}",
        base_pack_id="connector_contracts.v1",
        version="1.0.0",
        display_name="Connector Contract Policy Pack",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={
            "deployment_policies": [
                {
                    "policy_id": "connector_contracts.v1.policy_only",
                    "channels": [
                        {
                            "id": "client_notice",
                            "required_connector": "email_connector",
                            "tool_id": "email.send_dry_run",
                        }
                    ],
                }
            ],
            "available_connectors": ["email_connector"],
        },
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=required_company_organization(company),
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id=release.base_pack_id,
        role="primary",
        status="active",
        public_config_json=release.manifest_json,
    )


@override_settings(
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_managed_tool_ids_route_to_connector_adapters_and_store_sanitized_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    _install_policy_only_pack(company)
    email_adapter = FakeEmailProviderAdapter()
    whatsapp_adapter = FakeWhatsAppAdapter()
    social_adapter = FakeSocialProviderAdapter()
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_email_provider_adapter",
        lambda provider=None: email_adapter,
    )
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_whatsapp_provider_adapter",
        lambda provider=None: whatsapp_adapter,
    )
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_social_provider_adapter",
        lambda provider=None: social_adapter,
    )

    email = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="email.send",
        inputs={
            "provider": "fake",
            "from_email": "sender@example.com",
            "to": ["allowed@example.com"],
            "subject": "Approved notice",
            "text": "Approved notice with unsubscribe",
        },
        dry_run=False,
        idempotency_key="connector-email-live",
        approved=True,
        approval_id="approval-email",
        policy_allows_live=True,
    )
    assert_success_receipt_contract(
        email["result"], expected_evidence_mode="provider_send", allowed_statuses=("accepted",)
    )

    message = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="whatsapp.web_automation_send",
        inputs={"provider": "fake", "to": ["+15550101234"], "text": "Approved private notice"},
        dry_run=False,
        idempotency_key="connector-message-live",
        approved=True,
        approval_id="approval-message",
        policy_allows_live=True,
        operator_confirmed=True,
    )
    assert_success_receipt_contract(
        message["result"], expected_evidence_mode="web_automation", allowed_statuses=("accepted",)
    )

    social = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs={
            "provider": "fake",
            "platform": "configured_platform",
            "account_id": "account-123",
            "asset_id": "asset-public-safe",
            "caption": "Private caption",
            "content_approved": True,
            "compliance_gate_passed": True,
            "originality_check_passed": True,
        },
        dry_run=False,
        idempotency_key="connector-social-live",
        approved=True,
        approval_id="approval-social",
        policy_allows_provider_publish=True,
    )
    assert_success_receipt_contract(
        social["result"], expected_evidence_mode="provider_publish", allowed_statuses=("accepted",)
    )

    assert email_adapter.send_count == 1
    assert whatsapp_adapter.send_count == 1
    assert social_adapter.publish_count == 1
    executions = ToolExecution.objects.filter(run=run).order_by("tool_name")
    assert executions.count() == 3
    for execution in executions:
        assert_tool_execution_company_scope(execution, company=company)
        assert_tool_execution_receipt_sanitized(execution)


def test_unsupported_connector_tool_id_fails_safely() -> None:
    company, user, run = _company_run()

    with pytest.raises(PackToolExecutionError) as exc:
        execute_deployment_connector_tool(
            company=company,
            user=user,
            operation=run,
            tool_id="connector.not_declared",
            inputs={},
            dry_run=True,
            idempotency_key="unsupported-tool",
        )

    assert exc.value.code == "tool_not_found"
    assert not ToolExecution.objects.filter(run=run).exists()


@override_settings(
    GATEWAY_CONNECTOR_ALLOW_REAL_SEND=True,
    GATEWAY_RECIPIENT_ALLOWLIST=["chat-123"],
)
def test_gateway_tool_id_routes_to_backend_owned_tool_execution_receipt() -> None:
    company, user, run = _company_run()

    receipt = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="gateway.telegram.send",
        inputs={
            "provider": "fake",
            "to": "chat-123",
            "text": "Approved gateway message",
        },
        dry_run=False,
        idempotency_key="gateway-telegram-live",
        approved=True,
        approval_id="approval-gateway",
        policy_allows_live=True,
        operator_confirmed=True,
    )

    assert receipt["tool_id"] == "gateway.telegram.send"
    assert receipt["status"] == "succeeded"
    assert receipt["result"]["platform"] == "telegram"
    assert receipt["result"]["provider"] == "fake"
    assert receipt["result"]["status"] == "accepted"
    execution = ToolExecution.objects.get(run=run, tool_name="gateway.telegram.send")
    assert_tool_execution_company_scope(execution, company=company)
    assert_tool_execution_receipt_sanitized(execution)


@override_settings(
    GATEWAY_CONNECTOR_ALLOW_REAL_SEND=True,
    GATEWAY_RECIPIENT_ALLOWLIST=["chat-456"],
)
def test_gateway_tool_normalizes_outbound_media_artifacts() -> None:
    company, user, run = _company_run()

    receipt = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="gateway.telegram.send",
        inputs={
            "provider": "fake",
            "to": "chat-456",
            "text": "Approved gateway media message",
            "attachments": [
                {
                    "url": "https://provider.example/private-media?token=secret",
                    "content_type": "image/png",
                    "filename": "campaign.png",
                    "token": "secret-token",
                }
            ],
        },
        dry_run=False,
        idempotency_key="gateway-telegram-media-live",
        approved=True,
        approval_id="approval-gateway-media",
        policy_allows_live=True,
        operator_confirmed=True,
    )

    assert receipt["status"] == "succeeded"
    media_ids = receipt["result"]["media_artifact_ids"]
    assert len(media_ids) == 1
    artifact = GatewayMediaArtifact.objects.get(id=media_ids[0])
    assert artifact.direction == "outbound"
    assert str(artifact.tool_execution_id) == receipt["tool_execution_id"]
    assert "url" not in artifact.metadata_json
    assert artifact.metadata_json["url_hash"].startswith("sha256:")
    assert artifact.metadata_json["token_configured"] is True


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_duplicate_idempotency_reuses_failed_connector_receipt_without_second_adapter_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    adapter = FakeSocialProviderAdapter(fail=True, failure_code="fake_failure")
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_social_provider_adapter",
        lambda provider=None: adapter,
    )
    payload = {
        "provider": "fake",
        "platform": "configured_platform",
        "account_id": "account-123",
        "asset_id": "asset-public-safe",
        "caption": "Private caption",
        "content_approved": True,
        "compliance_gate_passed": True,
        "originality_check_passed": True,
    }

    first = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs=payload,
        dry_run=False,
        idempotency_key="failed-social-idempotent",
        approved=True,
        policy_allows_provider_publish=True,
    )
    second = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs={**payload, "account_id": "account-999", "caption": "Changed caption"},
        dry_run=False,
        idempotency_key="failed-social-idempotent",
        approved=True,
        policy_allows_provider_publish=True,
    )

    assert first["tool_execution_id"] == second["tool_execution_id"]
    assert first["status"] == "failed"
    assert second["status"] == "failed"
    assert adapter.publish_count == 1
    execution = ToolExecution.objects.get(id=first["tool_execution_id"])
    assert execution.error_json["error_code"] == "fake_failure"
    assert_tool_execution_receipt_sanitized(execution)


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_duplicate_idempotency_reuses_success_connector_receipt_without_second_adapter_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    adapter = FakeSocialProviderAdapter()
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_social_provider_adapter",
        lambda provider=None: adapter,
    )
    payload = {
        "provider": "fake",
        "platform": "configured_platform",
        "account_id": "account-123",
        "asset_id": "asset-public-safe",
        "caption": "Private caption",
        "content_approved": True,
        "compliance_gate_passed": True,
        "originality_check_passed": True,
    }

    first = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs=payload,
        dry_run=False,
        idempotency_key="succeeded-social-idempotent",
        approved=True,
        policy_allows_provider_publish=True,
    )
    second = execute_deployment_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs={**payload, "caption": "Changed caption after ack loss"},
        dry_run=False,
        idempotency_key="succeeded-social-idempotent",
        approved=True,
        policy_allows_provider_publish=True,
    )

    assert first["tool_execution_id"] == second["tool_execution_id"]
    assert first["status"] == "succeeded"
    assert second["status"] == "succeeded"
    assert first["result"] == second["result"]
    assert adapter.publish_count == 1
    execution = ToolExecution.objects.get(id=first["tool_execution_id"])
    assert execution.status == "succeeded"
    assert_tool_execution_receipt_sanitized(execution)
