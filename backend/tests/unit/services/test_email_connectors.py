from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.email_connectors import (
    EMAIL_MODE_REAL_SEND,
    EmailConnectorError,
    EmailSendRequest,
    FakeEmailProviderAdapter,
    ResendEmailProviderAdapter,
    dry_run_email,
    sanitize_provider_error,
    validate_email_request,
    validate_real_send_allowed,
    validate_recipient_allowlist,
)
from application.services.pack_tool_executions import execute_email_connector_tool
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
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        kwargs["url"] = url
        self.calls.append(kwargs)
        return self.response


def _user(org: Organization) -> User:
    user = User.objects.create_user(email="email-connector@example.com", password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    return user


def _company_run() -> tuple[Graph, User, Run]:
    org = Organization.objects.create(name="Email Connector Org")
    user = _user(org)
    company = cast(
        Graph, Graph.objects.create(owner=user, organization=org, name="Email Connector Co")
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


def test_fake_adapter_dry_run_produces_sanitized_receipt() -> None:
    receipt = dry_run_email(
        EmailSendRequest(
            provider="fake",
            mode="dry_run",
            to=["Owner@Example.com"],
            subject="Client notice",
            text="Private message body",
            idempotency_key="email-dry-run",
        )
    ).as_dict()

    assert receipt["provider"] == "fake"
    assert receipt["mode"] == "dry_run"
    assert receipt["evidence_mode"] == "sandbox"
    assert receipt["status"] == "dry_run"
    assert receipt["recipient_count"] == 1
    assert receipt["recipient_domains"] == ["example.com"]
    assert receipt["recipient_hashes"][0].startswith("sha256:")
    persisted = str(receipt)
    assert "Owner@Example.com" not in persisted
    assert "owner@example.com" not in persisted
    assert "Private message body" not in persisted


def test_resend_adapter_builds_sanitized_request_with_fake_transport() -> None:
    session = _FakeSession(_FakeResponse(status_code=200, payload={"id": "resend-message-123"}))
    adapter = ResendEmailProviderAdapter(
        api_key="resend-secret-token",
        api_base_url="https://api.resend.com",
        timeout_seconds=3,
        session=session,
    )

    receipt = adapter.send(
        EmailSendRequest(
            provider="resend",
            mode=EMAIL_MODE_REAL_SEND,
            from_email="sender@example.com",
            from_name="Sender",
            to=["allowed@example.com"],
            subject="Notice",
            html="<p>Hello</p><p>unsubscribe</p>",
            text="Hello unsubscribe",
            idempotency_key="resend-idempotency",
        )
    ).as_dict()

    assert receipt["provider"] == "resend"
    assert receipt["provider_message_id"] == "resend-message-123"
    assert receipt["status"] == "accepted"
    assert session.calls[0]["url"] == "https://api.resend.com/emails"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer resend-secret-token"
    assert session.calls[0]["headers"]["Idempotency-Key"] == "resend-idempotency"
    assert session.calls[0]["json"]["from"] == "Sender <sender@example.com>"
    assert session.calls[0]["json"]["to"] == ["allowed@example.com"]
    assert "resend-secret-token" not in str(receipt)


@override_settings(EMAIL_CONNECTOR_ALLOW_REAL_SEND=False)
def test_real_send_blocked_when_env_permission_disabled() -> None:
    request = _real_request()

    with pytest.raises(EmailConnectorError) as exc:
        validate_real_send_allowed(
            request,
            approved=True,
            policy_allows_live=True,
            adapter=FakeEmailProviderAdapter(),
        )

    assert exc.value.code == "real_send_disabled"
    assert exc.value.blocked_before_provider_call is True


@override_settings(
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
)
def test_real_send_blocked_without_approved_human_gate() -> None:
    with pytest.raises(EmailConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(),
            approved=False,
            policy_allows_live=True,
            adapter=FakeEmailProviderAdapter(),
        )

    assert exc.value.code == "approval_required"


@override_settings(
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
)
def test_real_send_blocked_when_recipient_not_allowlisted() -> None:
    with pytest.raises(EmailConnectorError) as exc:
        validate_recipient_allowlist(["blocked@example.com"], provider="fake")

    assert exc.value.code == "recipient_not_allowlisted"


@override_settings(
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
)
def test_real_send_blocked_when_provider_credentials_missing() -> None:
    with pytest.raises(EmailConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(provider="resend"),
            approved=True,
            policy_allows_live=True,
            adapter=ResendEmailProviderAdapter(api_key=""),
        )

    assert exc.value.code == "email_credentials_missing"


@override_settings(EMAIL_CONNECTOR_MAX_RECIPIENTS=1)
def test_recipient_cap_is_enforced() -> None:
    with pytest.raises(EmailConnectorError) as exc:
        validate_email_request(
            EmailSendRequest(
                provider="fake",
                mode="dry_run",
                to=["one@example.com", "two@example.com"],
                subject="Too many",
            ),
            dry_run=True,
        )

    assert exc.value.code == "recipient_cap_exceeded"


@override_settings(
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
)
def test_unsubscribe_footer_policy_hook_blocks_real_send() -> None:
    with pytest.raises(EmailConnectorError) as exc:
        validate_real_send_allowed(
            _real_request(requires_unsubscribe_footer=True),
            approved=True,
            policy_allows_live=True,
            adapter=FakeEmailProviderAdapter(),
        )

    assert exc.value.code == "unsubscribe_footer_required"


def test_provider_failure_is_bounded_and_sanitized() -> None:
    session = _FakeSession(
        _FakeResponse(
            status_code=400,
            payload={
                "name": "validation_error",
                "message": "Bad recipient owner@example.com with Bearer resend-secret-token",
            },
        )
    )
    adapter = ResendEmailProviderAdapter(api_key="resend-secret-token", session=session)

    with pytest.raises(EmailConnectorError) as exc:
        adapter.send(_real_request(provider="resend"))

    error = sanitize_provider_error(exc.value)
    assert error["error_code"] == "validation_error"
    assert "[redacted-email]" in error["error_message"]
    assert "resend-secret-token" not in str(error)
    assert len(error["error_message"]) <= 300


@override_settings(
    EMAIL_CONNECTOR_PROVIDER="fake",
    EMAIL_CONNECTOR_ALLOW_REAL_SEND=True,
    EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST=["allowed@example.com"],
)
def test_duplicate_idempotency_key_does_not_create_duplicate_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, run = _company_run()
    adapter = FakeEmailProviderAdapter()

    monkeypatch.setattr(
        "application.services.pack_tool_executions.get_email_provider_adapter",
        lambda provider=None: adapter,
    )
    payload = {
        "provider": "fake",
        "from_email": "sender@example.com",
        "to": ["allowed@example.com"],
        "subject": "Approved notice",
        "text": "Approved notice with unsubscribe",
    }

    first = execute_email_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="email.send",
        inputs=payload,
        dry_run=False,
        idempotency_key="email-send-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_live=True,
    )
    changed_payload = {
        **payload,
        "to": ["not-allowlisted@example.com"],
        "subject": "Changed payload must not create a second send",
    }
    second = execute_email_connector_tool(
        company=company,
        user=user,
        operation=run,
        tool_id="email.send",
        inputs=changed_payload,
        dry_run=False,
        idempotency_key="email-send-idempotent",
        approved=True,
        approval_id="approval-1",
        policy_allows_live=True,
    )

    assert first["tool_execution_id"] == second["tool_execution_id"]
    assert first["result"]["provider_message_id"] == second["result"]["provider_message_id"]
    assert adapter.send_count == 1
    assert ToolExecution.objects.filter(run=run, tool_name="email.send").count() == 1


def test_connector_core_has_no_company_or_marketing_literals() -> None:
    service_path = (
        Path(__file__).resolve().parents[3] / "application" / "services" / "email_connectors.py"
    )
    service_text = service_path.read_text(encoding="utf-8")

    for forbidden in (
        "ATLAS",
        "Legacy",
        "marketing",
        "campaign",
        "email_service_connector",
        "dmp.email_draft_send_schedule",
    ):
        assert forbidden not in service_text


def _real_request(
    *,
    provider: str = "fake",
    requires_unsubscribe_footer: bool = False,
) -> EmailSendRequest:
    return EmailSendRequest(
        provider=provider,
        mode=EMAIL_MODE_REAL_SEND,
        from_email="sender@example.com",
        to=["allowed@example.com"],
        subject="Approved notice",
        text="Approved notice body",
        idempotency_key="real-send",
        requires_unsubscribe_footer=requires_unsubscribe_footer,
    )
