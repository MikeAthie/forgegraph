from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from application.services.pack_tool_executions import (
    PackToolExecutionError,
    execute_whatsapp_connector_tool,
)
from application.services.whatsapp_connectors import (
    WHATSAPP_MODE_REAL_SEND,
    WHATSAPP_PROVIDER_HERMES_BRIDGE,
    FakeWhatsAppAdapter,
    HermesBridgeWhatsAppAdapter,
    OpenWaWebAutomationAdapter,
    WhatsAppConnectorError,
    WhatsAppSendRequest,
    dry_run_whatsapp,
    get_whatsapp_provider_adapter,
    sanitize_provider_error,
    send_whatsapp,
    validate_real_send_allowed,
    validate_recipient_allowlist,
    validate_whatsapp_request,
)
from infrastructure.orm.models import Graph, GraphVersion, Organization, Run, ToolExecution, User

pytestmark = pytest.mark.django_db


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: dict[str, Any],
        reason: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.reason = reason
        self.content = str(payload).encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(
        self,
        *,
        health: dict[str, Any] | None = None,
        send: dict[str, Any] | None = None,
        health_status_code: int = 200,
        status: dict[str, Any] | None = None,
        status_status_code: int = 200,
        send_status_code: int = 200,
        send_reason: str = "",
        post_exception: requests.RequestException | None = None,
    ) -> None:
        self.health = health or {"status": "ready"}
        self.send = send or {"id": "open-wa-message-123"}
        self.health_status_code = health_status_code
        self.status = status or {"status": "ready"}
        self.status_status_code = status_status_code
        self.send_status_code = send_status_code
        self.send_reason = send_reason
        self.post_exception = post_exception
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        kwargs["url"] = url
        kwargs["method"] = "GET"
        self.calls.append(kwargs)
        if url.rstrip("/").endswith("/status"):
            return _FakeResponse(status_code=self.status_status_code, payload=self.status)
        return _FakeResponse(status_code=self.health_status_code, payload=self.health)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        kwargs["url"] = url
        kwargs["method"] = "POST"
        self.calls.append(kwargs)
        if self.post_exception is not None:
            raise self.post_exception
        return _FakeResponse(
            status_code=self.send_status_code,
            payload=self.send,
            reason=self.send_reason,
        )


def _user(org: Organization) -> User:
    user = User.objects.create_user(
        email="whatsapp-connector@example.com", password="testpassword123"
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    return user


def _company_run() -> tuple[Graph, User, Run]:
    org = Organization.objects.create(name="Messaging Connector Org")
    user = _user(org)
    company = cast(
        Graph, Graph.objects.create(owner=user, organization=org, name="Messaging Connector Co")
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


def test_fake_whatsapp_dry_run_produces_sanitized_receipt() -> None:
    receipt = dry_run_whatsapp(
        WhatsAppSendRequest(
            provider="fake",
            mode="dry_run",
            to=["+1 (555) 010-1234"],
            text="Private message body",
            idempotency_key="message-dry-run",
        )
    ).as_dict()

    assert receipt["provider"] == "fake"
    assert receipt["mode"] == "dry_run"
    assert receipt["evidence_mode"] == "sandbox"
    assert receipt["status"] == "accepted"
    assert receipt["recipient_count"] == 1
    assert receipt["recipient_hashes"][0].startswith("sha256:")
    persisted = str(receipt)
    assert "+15550101234" not in persisted
    assert "555" not in persisted
    assert "Private message body" not in persisted


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="open_wa_web",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_WEB_AUTOMATION_ENABLED=False,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_open_wa_provider_disabled_blocks_before_provider_call() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(provider="open_wa_web"),
            approved=True,
            policy_allows_live=True,
            adapter=OpenWaWebAutomationAdapter(sidecar_url="http://sidecar", session_ref="session"),
        )

    assert exc.value.code == "whatsapp_web_automation_disabled"
    assert exc.value.blocked_before_provider_call is True


@override_settings(WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE)
def test_hermes_bridge_provider_selection_returns_bridge_adapter() -> None:
    adapter = get_whatsapp_provider_adapter()

    assert isinstance(adapter, HermesBridgeWhatsAppAdapter)
    assert adapter.provider == WHATSAPP_PROVIDER_HERMES_BRIDGE


@pytest.mark.parametrize(
    ("enabled", "bridge_url", "session_ref"),
    [
        (False, "http://hermes-bridge", "session-secret"),
        (True, "", "session-secret"),
        (True, "http://hermes-bridge", ""),
    ],
)
def test_hermes_bridge_disabled_or_missing_config_blocks_before_provider_call(
    enabled: bool,
    bridge_url: str,
    session_ref: str,
) -> None:
    session = _FakeSession()
    with override_settings(
        WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE,
        WHATSAPP_CONNECTOR_ALLOW_REAL_SEND=True,
        WHATSAPP_HERMES_BRIDGE_ENABLED=enabled,
        WHATSAPP_HERMES_BRIDGE_URL=bridge_url,
        WHATSAPP_HERMES_BRIDGE_SESSION_REF=session_ref,
        WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
    ):
        with pytest.raises(WhatsAppConnectorError) as exc:
            validate_real_send_allowed(
                _real_request(provider=WHATSAPP_PROVIDER_HERMES_BRIDGE),
                approved=True,
                policy_allows_live=True,
                adapter=HermesBridgeWhatsAppAdapter(session=session),
            )

    assert exc.value.code == "whatsapp_session_missing"
    assert exc.value.blocked_before_provider_call is True
    assert session.calls == []


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="open_wa_web",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_WEB_AUTOMATION_ENABLED=True,
    WHATSAPP_WEB_AUTOMATION_SESSION_REF="",
    WHATSAPP_WEB_AUTOMATION_SIDECAR_URL="",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_missing_session_blocks_before_provider_call() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(provider="open_wa_web"),
            approved=True,
            policy_allows_live=True,
            adapter=OpenWaWebAutomationAdapter(sidecar_url="", session_ref=""),
        )

    assert exc.value.code == "whatsapp_session_missing"
    assert exc.value.blocked_before_provider_call is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "ready", "phone": "+15550101234"}, "ready"),
        (
            {"session_status": "authenticated", "session_ref": "session-secret"},
            "authenticated",
        ),
        ({"state": "connected", "qr_token": "qr-secret"}, "connected"),
        ({"connected": True, "phone": "+1 555 010 1234"}, "connected"),
    ],
)
@override_settings(
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
)
def test_hermes_bridge_session_status_maps_safe_values(
    payload: dict[str, Any], expected: str
) -> None:
    adapter = HermesBridgeWhatsAppAdapter(session=_FakeSession(health=payload))

    status = adapter.session_status()

    assert status == expected
    assert "+15550101234" not in status
    assert "+1 555 010 1234" not in status
    assert "session-secret" not in status
    assert "qr-secret" not in status


@override_settings(
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
)
def test_hermes_bridge_session_status_falls_back_to_status_endpoint() -> None:
    session = _FakeSession(
        health={"status": "session-secret +15550101234"},
        health_status_code=404,
        status={
            "session_status": "connected",
            "session_ref": "session-secret",
            "phone": "+15550101234",
        },
    )
    adapter = HermesBridgeWhatsAppAdapter(session=session)

    status = adapter.session_status()

    assert status == "connected"
    assert [call["url"].rsplit("/", 1)[-1] for call in session.calls] == ["health", "status"]
    assert all("params" not in call for call in session.calls)
    assert all(call["headers"]["X-ForgeGraph-Session-Ref"] == "session-secret" for call in session.calls)
    assert "session-secret" not in status
    assert "+15550101234" not in status


@override_settings(WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=False)
def test_real_send_blocked_when_env_permission_disabled() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(),
            approved=True,
            policy_allows_live=True,
            adapter=FakeWhatsAppAdapter(),
        )

    assert exc.value.code == "real_send_disabled"


@override_settings(
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_real_send_blocked_without_approved_gate_or_operator_confirmation() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(),
            approved=False,
            policy_allows_live=True,
            adapter=FakeWhatsAppAdapter(),
        )
    assert exc.value.code == "approval_required"

    with pytest.raises(WhatsAppConnectorError) as missing_operator:
        validate_real_send_allowed(
            _real_request(operator_confirmed=False),
            approved=True,
            policy_allows_live=True,
            adapter=FakeWhatsAppAdapter(),
        )
    assert missing_operator.value.code == "operator_confirmation_required"


@override_settings(
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550109999"],
)
def test_real_send_blocked_when_recipient_not_allowlisted() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_recipient_allowlist(["+15550101234"], provider="fake")

    assert exc.value.code == "recipient_not_allowlisted"


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE,
    WHATSAPP_CONNECTOR_ALLOW_REAL_SEND=True,
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550109999"],
)
def test_hermes_bridge_blocks_unallowlisted_recipient_before_status_call() -> None:
    session = _FakeSession(health={"status": "ready"})
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(provider=WHATSAPP_PROVIDER_HERMES_BRIDGE),
            approved=True,
            policy_allows_live=True,
            adapter=HermesBridgeWhatsAppAdapter(session=session),
        )

    assert exc.value.code == "recipient_not_allowlisted"
    assert exc.value.blocked_before_provider_call is True
    assert session.calls == []


@override_settings(WHATSAPP_WEB_AUTOMATION_MAX_RECIPIENTS=1)
def test_recipient_cap_is_enforced() -> None:
    with pytest.raises(WhatsAppConnectorError) as exc:
        validate_whatsapp_request(
            WhatsAppSendRequest(
                provider="fake",
                mode="dry_run",
                to=["+15550101234", "+15550105678"],
            ),
            dry_run=True,
        )

    assert exc.value.code == "recipient_cap_exceeded"


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="open_wa_web",
    WHATSAPP_WEB_AUTOMATION_ENABLED=True,
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_WEB_AUTOMATION_SESSION_REF="session-secret",
    WHATSAPP_WEB_AUTOMATION_SIDECAR_URL="http://open-wa-sidecar",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_open_wa_adapter_returns_web_automation_receipt_without_session_material() -> None:
    session = _FakeSession()
    adapter = OpenWaWebAutomationAdapter(session=session)

    receipt = adapter.send(_real_request(provider="open_wa_web")).as_dict()

    assert receipt["provider"] == "open_wa_web"
    assert receipt["mode"] == "real_send"
    assert receipt["evidence_mode"] == "web_automation"
    assert receipt["status"] == "accepted"
    assert receipt["provider_message_id"] == "open-wa-message-123"
    assert receipt["session_required"] is True
    persisted = str(receipt)
    assert "session-secret" not in persisted
    assert "+15550101234" not in persisted
    assert "Private" not in persisted
    assert session.calls[-1]["json"]["idempotency_key"] == "message-send"


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE,
    WHATSAPP_CONNECTOR_ALLOW_REAL_SEND=True,
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_hermes_bridge_send_returns_sanitized_receipt() -> None:
    session = _FakeSession(
        health={"status": "connected", "phone": "+15550101234"},
        send={
            "messageId": "hermes-message-123",
            "to": "+15550101234",
            "text": "Private approved notice",
            "session_ref": "session-secret",
        },
    )
    adapter = HermesBridgeWhatsAppAdapter(session=session)

    receipt = send_whatsapp(
        _real_request(provider=WHATSAPP_PROVIDER_HERMES_BRIDGE),
        approved=True,
        policy_allows_live=True,
        adapter=adapter,
    ).as_dict()

    assert receipt["provider"] == WHATSAPP_PROVIDER_HERMES_BRIDGE
    assert receipt["mode"] == "real_send"
    assert receipt["evidence_mode"] == "web_automation"
    assert receipt["status"] == "accepted"
    assert receipt["provider_message_id"] == "hermes-message-123"
    assert receipt["session_required"] is True
    persisted = str(receipt)
    assert "session-secret" not in persisted
    assert "+15550101234" not in persisted
    assert "Private approved notice" not in persisted
    assert session.calls[-1]["json"]["idempotency_key"] == "message-send"


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE,
    WHATSAPP_CONNECTOR_ALLOW_REAL_SEND=True,
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_hermes_bridge_request_failure_is_retryable_and_sanitized() -> None:
    adapter = HermesBridgeWhatsAppAdapter(
        session=_FakeSession(
            health={"status": "ready"},
            post_exception=requests.Timeout(
                "failed for +1 555 010 1234 Private approved notice session-secret"
            ),
        )
    )

    with pytest.raises(WhatsAppConnectorError) as exc:
        send_whatsapp(
            _real_request(provider=WHATSAPP_PROVIDER_HERMES_BRIDGE),
            approved=True,
            policy_allows_live=True,
            adapter=adapter,
        )

    assert exc.value.code == "provider_request_failed"
    assert exc.value.retryable is True
    error = sanitize_provider_error(exc.value)
    persisted = str(error)
    assert error["sanitized"] is True
    assert error["retryable"] is True
    assert "+1 555 010 1234" not in persisted
    assert "Private approved notice" not in persisted
    assert "session-secret" not in persisted


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER=WHATSAPP_PROVIDER_HERMES_BRIDGE,
    WHATSAPP_CONNECTOR_ALLOW_REAL_SEND=True,
    WHATSAPP_HERMES_BRIDGE_ENABLED=True,
    WHATSAPP_HERMES_BRIDGE_URL="http://hermes-bridge",
    WHATSAPP_HERMES_BRIDGE_SESSION_REF="session-secret",
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_hermes_bridge_http_error_does_not_persist_provider_echoed_message_text() -> None:
    adapter = HermesBridgeWhatsAppAdapter(
        session=_FakeSession(
            health={"status": "ready"},
            send_status_code=500,
            send={
                "error": {
                    "code": "bridge_send_failed",
                    "message": "failed for +1 555 010 1234 Private approved notice session-secret",
                }
            },
        )
    )

    with pytest.raises(WhatsAppConnectorError) as exc:
        send_whatsapp(
            _real_request(provider=WHATSAPP_PROVIDER_HERMES_BRIDGE),
            approved=True,
            policy_allows_live=True,
            adapter=adapter,
        )

    error = sanitize_provider_error(exc.value)
    persisted = str(error)
    assert exc.value.code == "bridge_send_failed"
    assert exc.value.message == "Messaging provider request failed with HTTP 500."
    assert "Private approved notice" not in persisted
    assert "+1 555 010 1234" not in persisted
    assert "session-secret" not in persisted


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="fake",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_duplicate_idempotency_key_does_not_create_duplicate_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    adapter = FakeWhatsAppAdapter()
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_whatsapp_provider_adapter",
        lambda provider=None: adapter,
    )
    payload = {"provider": "fake", "to": ["+15550101234"], "text": "Approved private notice"}

    first = execute_whatsapp_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="whatsapp.web_automation_send",
        inputs=payload,
        dry_run=False,
        idempotency_key="message-send-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_live=True,
        operator_confirmed=True,
    )
    second = execute_whatsapp_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="whatsapp.web_automation_send",
        inputs={**payload, "to": ["+15550109999"], "text": "Changed text"},
        dry_run=False,
        idempotency_key="message-send-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_live=True,
        operator_confirmed=True,
    )

    assert first["tool_execution_id"] == second["tool_execution_id"]
    assert first["result"]["provider_message_id"] == second["result"]["provider_message_id"]
    assert first["result"]["evidence_mode"] == "web_automation"
    assert adapter.send_count == 1
    execution = ToolExecution.objects.get(run=run, tool_name="whatsapp.web_automation_send")
    persisted = f"{execution.result_json}{execution.error_json}"
    assert "+15550101234" not in persisted
    assert "Approved private notice" not in persisted
    assert (
        ToolExecution.objects.filter(run=run, tool_name="whatsapp.web_automation_send").count() == 1
    )


def test_manual_ops_evidence_requires_policy_permission() -> None:
    company, user, run = _company_run()
    payload = {"provider": "fake", "to": ["+15550101234"], "text": "Manual private notice"}

    with pytest.raises(PackToolExecutionError) as exc:
        execute_whatsapp_connector_tool(
            company=company,
            user=user,
            operation=run,
            tool_id="whatsapp.send_manual",
            inputs=payload,
            dry_run=True,
            idempotency_key="manual-message",
        )

    assert exc.value.code == "web_automation_evidence_not_allowed"
    assert not ToolExecution.objects.filter(run=run, tool_name="whatsapp.send_manual").exists()

    receipt = execute_whatsapp_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="whatsapp.send_manual",
        inputs=payload,
        dry_run=True,
        idempotency_key="manual-message",
        policy_allows_web_automation_evidence=True,
    )

    assert receipt["result"]["mode"] == "manual_ops"
    assert receipt["result"]["evidence_mode"] == "web_automation"
    persisted = str(
        ToolExecution.objects.get(run=run, tool_name="whatsapp.send_manual").result_json
    )
    assert "+15550101234" not in persisted
    assert "Manual private notice" not in persisted


@override_settings(
    WHATSAPP_CONNECTOR_PROVIDER="fake",
    WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND=True,
    WHATSAPP_RECIPIENT_ALLOWLIST=["+15550101234"],
)
def test_provider_failure_stores_bounded_sanitized_error(monkeypatch: pytest.MonkeyPatch) -> None:
    company, user, run = _company_run()
    adapter = FakeWhatsAppAdapter(fail=True, failure_code="fake_failure")
    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_whatsapp_provider_adapter",
        lambda provider=None: adapter,
    )

    receipt = execute_whatsapp_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="whatsapp.web_automation_send",
        inputs={"provider": "fake", "to": ["+15550101234"], "text": "Approved private notice"},
        dry_run=False,
        idempotency_key="message-send-failed",
        approved=True,
        policy_allows_live=True,
        operator_confirmed=True,
    )

    execution = ToolExecution.objects.get(id=receipt["tool_execution_id"])
    assert execution.status == "failed"
    assert execution.error_json["error_code"] == "fake_failure"
    assert execution.error_json["sanitized"] is True
    assert "+15550101234" not in str(execution.error_json)
    assert "Approved private notice" not in str(execution.error_json)
    assert len(execution.error_json["error_message"]) <= 300


def test_provider_error_sanitizes_phone_and_session_material() -> None:
    error = sanitize_provider_error(
        WhatsAppConnectorError(
            "provider_http_error",
            "Failed for +1 555 010 1234 with QR session-secret-token",
            provider="open_wa_web",
        )
    )

    assert "[redacted-phone]" in error["error_message"]
    assert "+1 555 010 1234" not in str(error)
    assert "session-secret-token" not in str(error)


def test_connector_core_has_no_company_or_marketing_literals() -> None:
    service_path = (
        Path(__file__).resolve().parents[3] / "application" / "services" / "whatsapp_connectors.py"
    )
    service_text = service_path.read_text(encoding="utf-8")

    for forbidden in (
        "ATLAS",
        "Legacy",
        "marketing",
        "campaign",
        "whatsapp_business_connector",
        "messaging.whatsapp_template_send",
    ):
        assert forbidden not in service_text


def _real_request(
    *,
    provider: str = "fake",
    operator_confirmed: bool = True,
) -> WhatsAppSendRequest:
    return WhatsAppSendRequest(
        provider=provider,
        mode=WHATSAPP_MODE_REAL_SEND,
        to=["+15550101234"],
        text="Private approved notice",
        idempotency_key="message-send",
        operator_confirmed=operator_confirmed,
    )
