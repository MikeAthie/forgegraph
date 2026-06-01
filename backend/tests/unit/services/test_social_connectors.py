from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.pack_tool_executions import (
    PackToolExecutionError,
    execute_social_connector_tool,
)
from application.services.social_connectors import (
    SOCIAL_MODE_PROVIDER_PUBLISH,
    FakeSocialProviderAdapter,
    MetaGraphSocialAdapter,
    SocialConnectorError,
    SocialPublishRequest,
    dry_run_social_publish,
    record_manual_publish_evidence,
    sanitize_provider_error,
    validate_platform_account_allowlist,
    validate_real_publish_allowed,
    validate_social_request,
)
from infrastructure.orm.models import Graph, GraphVersion, Organization, Run, ToolExecution, User

pytestmark = pytest.mark.django_db


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any], reason: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.reason = reason
        self.content = str(payload).encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        kwargs["url"] = url
        kwargs["method"] = "POST"
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _user(org: Organization) -> User:
    user = User.objects.create_user(
        email="social-connector@example.com", password="testpassword123"
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    return user


def _company_run() -> tuple[Graph, User, Run]:
    org = Organization.objects.create(name="Social Connector Org")
    user = _user(org)
    company = cast(
        Graph, Graph.objects.create(owner=user, organization=org, name="Social Connector Co")
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


def test_fake_social_dry_run_produces_sanitized_receipt() -> None:
    receipt = dry_run_social_publish(
        SocialPublishRequest(
            provider="fake",
            platform="configured_platform",
            mode="dry_run",
            account_id="account-123",
            asset_ids=["asset_1"],
            caption="Private caption",
            idempotency_key="social-dry-run",
        )
    ).as_dict()

    assert receipt["provider"] == "fake"
    assert receipt["mode"] == "dry_run"
    assert receipt["evidence_mode"] == "sandbox"
    assert receipt["status"] == "accepted"
    assert receipt["asset_count"] == 1
    assert receipt["caption_hash"].startswith("sha256:")
    persisted = str(receipt)
    assert "Private caption" not in persisted
    assert "account-123" not in persisted


def test_manual_publish_evidence_records_hashes_only() -> None:
    receipt = record_manual_publish_evidence(
        _request(
            mode="manual_publish_record",
            external_post_url="https://social.example/posts/private-id",
            external_post_id="post-private-id",
            operator_confirmed=True,
        )
    ).as_dict()

    assert receipt["provider"] == "manual"
    assert receipt["mode"] == "manual_publish_record"
    assert receipt["evidence_mode"] == "manual_publish"
    assert receipt["status"] == "recorded"
    assert receipt["external_post_url_hash"].startswith("sha256:")
    assert receipt["external_post_id_hash"].startswith("sha256:")
    persisted = str(receipt)
    assert "https://social.example" not in persisted
    assert "post-private-id" not in persisted
    assert "Private caption" not in persisted


@override_settings(SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=False)
def test_provider_publish_blocked_when_env_permission_disabled() -> None:
    with pytest.raises(SocialConnectorError) as exc:
        validate_real_publish_allowed(
            _request(),
            approved=True,
            policy_allows_provider_publish=True,
            adapter=FakeSocialProviderAdapter(),
        )

    assert exc.value.code == "provider_publish_disabled"
    assert exc.value.blocked_before_provider_call is True


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_provider_publish_blocked_without_approved_gate() -> None:
    with pytest.raises(SocialConnectorError) as exc:
        validate_real_publish_allowed(
            _request(),
            approved=False,
            policy_allows_provider_publish=True,
            adapter=FakeSocialProviderAdapter(),
        )

    assert exc.value.code == "approval_required"


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-999"],
)
def test_provider_publish_blocked_when_account_not_allowlisted() -> None:
    with pytest.raises(SocialConnectorError) as exc:
        validate_platform_account_allowlist(_request(), provider="fake")

    assert exc.value.code == "account_not_allowlisted"


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_provider_publish_blocked_when_credentials_missing() -> None:
    with pytest.raises(SocialConnectorError) as exc:
        validate_real_publish_allowed(
            _request(provider="meta_graph"),
            approved=True,
            policy_allows_provider_publish=True,
            adapter=MetaGraphSocialAdapter(access_token=""),
        )

    assert exc.value.code == "social_credentials_missing"


def test_asset_count_and_caption_caps_are_enforced() -> None:
    with override_settings(SOCIAL_CONNECTOR_MAX_ASSETS_PER_POST=1):
        with pytest.raises(SocialConnectorError) as exc:
            validate_social_request(
                SocialPublishRequest(
                    provider="fake",
                    platform="configured_platform",
                    mode="dry_run",
                    asset_ids=["asset-1", "asset-2"],
                ),
                dry_run=True,
            )
        assert exc.value.code == "asset_cap_exceeded"

    with override_settings(SOCIAL_CONNECTOR_MAX_CAPTION_CHARS=5):
        with pytest.raises(SocialConnectorError) as caption_exc:
            validate_social_request(
                SocialPublishRequest(
                    provider="fake",
                    platform="configured_platform",
                    mode="dry_run",
                    caption="too long",
                ),
                dry_run=True,
            )
        assert caption_exc.value.code == "caption_too_long"


@override_settings(
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_content_compliance_and_originality_gates_are_enforced() -> None:
    with pytest.raises(SocialConnectorError) as missing_asset:
        validate_real_publish_allowed(
            _request(asset_approved=False),
            approved=True,
            policy_allows_provider_publish=True,
            adapter=FakeSocialProviderAdapter(),
        )
    assert missing_asset.value.code == "asset_approval_required"

    with pytest.raises(SocialConnectorError) as compliance:
        validate_real_publish_allowed(
            _request(requires_compliance_gate=True, compliance_gate_passed=False),
            approved=True,
            policy_allows_provider_publish=True,
            adapter=FakeSocialProviderAdapter(),
        )
    assert compliance.value.code == "compliance_gate_required"

    with pytest.raises(SocialConnectorError) as originality:
        validate_real_publish_allowed(
            _request(requires_originality_check=True, originality_check_passed=False),
            approved=True,
            policy_allows_provider_publish=True,
            adapter=FakeSocialProviderAdapter(),
        )
    assert originality.value.code == "originality_check_required"


def test_meta_adapter_builds_instagram_container_publish_flow_with_fake_transport() -> None:
    session = _FakeSession(
        [
            _FakeResponse(status_code=200, payload={"id": "container-123"}),
            _FakeResponse(status_code=200, payload={"id": "post-456"}),
        ]
    )
    adapter = MetaGraphSocialAdapter(
        access_token="meta-secret-token",
        api_base_url="https://graph.facebook.com",
        api_version="v24.0",
        timeout_seconds=3,
        session=session,
    )

    receipt = adapter.publish(
        _request(
            provider="meta_graph", platform="instagram", media_url="https://cdn.example/private.jpg"
        )
    ).as_dict()

    assert receipt["provider"] == "meta_graph"
    assert receipt["platform"] == "instagram"
    assert receipt["provider_post_id"] == "post-456"
    assert receipt["provider_container_id"] == "container-123"
    assert session.calls[0]["url"] == "https://graph.facebook.com/v24.0/account-123/media"
    assert session.calls[1]["url"] == "https://graph.facebook.com/v24.0/account-123/media_publish"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer meta-secret-token"
    assert session.calls[1]["headers"]["Idempotency-Key"] == "social-provider"
    assert "meta-secret-token" not in str(receipt)
    assert "https://cdn.example/private.jpg" not in str(receipt)


def test_meta_adapter_builds_facebook_page_feed_request_with_fake_transport() -> None:
    session = _FakeSession([_FakeResponse(status_code=200, payload={"id": "page-post-123"})])
    adapter = MetaGraphSocialAdapter(access_token="meta-secret-token", session=session)

    receipt = adapter.publish(
        _request(provider="meta_graph", platform="facebook", link_url="https://example.com")
    ).as_dict()

    assert receipt["provider_post_id"] == "page-post-123"
    assert session.calls[0]["url"].endswith("/account-123/feed")
    assert session.calls[0]["json"]["message"] == "Private caption"
    assert session.calls[0]["json"]["link"] == "https://example.com"
    assert "https://example.com" not in str(receipt)


@override_settings(
    SOCIAL_CONNECTOR_PROVIDER="fake",
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_duplicate_idempotency_key_does_not_create_duplicate_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    adapter = FakeSocialProviderAdapter()
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_social_provider_adapter",
        lambda provider=None: adapter,
    )
    payload = _payload()

    first = execute_social_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs=payload,
        dry_run=False,
        idempotency_key="social-publish-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_provider_publish=True,
    )
    second = execute_social_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs={**payload, "account_id": "account-999", "caption": "Changed caption"},
        dry_run=False,
        idempotency_key="social-publish-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_provider_publish=True,
    )

    assert first["tool_execution_id"] == second["tool_execution_id"]
    assert first["result"]["provider_post_id"] == second["result"]["provider_post_id"]
    assert adapter.publish_count == 1
    execution = ToolExecution.objects.get(run=run, tool_name="social.provider_publish")
    persisted = f"{execution.result_json}{execution.error_json}"
    assert "account-123" not in persisted
    assert "Private caption" not in persisted
    assert ToolExecution.objects.filter(run=run, tool_name="social.provider_publish").count() == 1


def test_manual_evidence_requires_policy_permission() -> None:
    company, user, run = _company_run()

    with pytest.raises(PackToolExecutionError) as exc:
        execute_social_connector_tool(
            company=company,
            user=user,
            operation=run,
            tool_id="social.manual_publish_record",
            inputs=_payload(
                external_post_url="https://social.example/posts/1", operator_confirmed=True
            ),
            dry_run=True,
            idempotency_key="manual-social",
        )

    assert exc.value.code == "manual_publish_evidence_not_allowed"
    assert not ToolExecution.objects.filter(
        run=run, tool_name="social.manual_publish_record"
    ).exists()

    receipt = execute_social_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.manual_publish_record",
        inputs=_payload(
            external_post_url="https://social.example/posts/1", operator_confirmed=True
        ),
        dry_run=True,
        idempotency_key="manual-social",
        policy_allows_manual_publish_evidence=True,
    )

    assert receipt["result"]["mode"] == "manual_publish_record"
    assert receipt["result"]["evidence_mode"] == "manual_publish"
    persisted = str(
        ToolExecution.objects.get(run=run, tool_name="social.manual_publish_record").result_json
    )
    assert "https://social.example" not in persisted
    assert "Private caption" not in persisted


@override_settings(
    SOCIAL_CONNECTOR_PROVIDER="fake",
    SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH=True,
    SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST=["account-123"],
)
def test_provider_failure_stores_bounded_sanitized_error(monkeypatch: pytest.MonkeyPatch) -> None:
    company, user, run = _company_run()
    adapter = FakeSocialProviderAdapter(fail=True, failure_code="fake_failure")
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_social_provider_adapter",
        lambda provider=None: adapter,
    )

    receipt = execute_social_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="social.provider_publish",
        inputs=_payload(),
        dry_run=False,
        idempotency_key="social-provider-failed",
        approved=True,
        policy_allows_provider_publish=True,
    )

    execution = ToolExecution.objects.get(id=receipt["tool_execution_id"])
    assert execution.status == "failed"
    assert execution.error_json["error_code"] == "fake_failure"
    assert execution.error_json["sanitized"] is True
    assert "Private caption" not in str(execution.error_json)
    assert len(execution.error_json["error_message"]) <= 300


def test_provider_error_sanitizes_tokens_urls_and_raw_response_material() -> None:
    error = sanitize_provider_error(
        SocialConnectorError(
            "provider_http_error",
            "Failed for https://example.com/private.jpg with Bearer meta-secret-token",
            provider="meta_graph",
        )
    )

    assert "[redacted-url]" in error["error_message"]
    assert "[redacted-token]" in error["error_message"]
    assert "https://example.com" not in str(error)
    assert "meta-secret-token" not in str(error)


def test_connector_core_has_no_company_or_marketing_literals() -> None:
    service_path = (
        Path(__file__).resolve().parents[3] / "application" / "services" / "social_connectors.py"
    )
    service_text = service_path.read_text(encoding="utf-8")

    for forbidden in (
        "ATLAS",
        "Legacy",
        "marketing",
        "campaign",
        "/api/marketing",
    ):
        assert forbidden not in service_text


def _request(
    *,
    provider: str = "fake",
    platform: str = "configured_platform",
    mode: str = SOCIAL_MODE_PROVIDER_PUBLISH,
    account_id: str = "account-123",
    asset_approved: bool = True,
    caption_approved: bool = True,
    compliance_gate_passed: bool = True,
    originality_check_passed: bool = True,
    requires_compliance_gate: bool = False,
    requires_originality_check: bool = False,
    operator_confirmed: bool = False,
    external_post_url: str = "",
    external_post_id: str = "",
    media_url: str = "",
    link_url: str = "",
) -> SocialPublishRequest:
    return SocialPublishRequest(
        provider=provider,
        platform=platform,
        mode=mode,
        account_id=account_id,
        asset_ids=["asset-1"],
        caption="Private caption",
        link_url=link_url,
        media_url=media_url,
        external_post_url=external_post_url,
        external_post_id=external_post_id,
        idempotency_key="social-provider",
        asset_approved=asset_approved,
        caption_approved=caption_approved,
        compliance_gate_passed=compliance_gate_passed,
        originality_check_passed=originality_check_passed,
        requires_compliance_gate=requires_compliance_gate,
        requires_originality_check=requires_originality_check,
        operator_confirmed=operator_confirmed,
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "provider": "fake",
        "platform": "configured_platform",
        "account_id": "account-123",
        "asset_id": "asset-1",
        "caption": "Private caption",
        "asset_approved": True,
        "caption_approved": True,
        "compliance_gate_passed": True,
        "originality_check_passed": True,
    }
    payload.update(overrides)
    return payload
