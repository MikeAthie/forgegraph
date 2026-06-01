from __future__ import annotations

import os

import pytest

from application.services.email_connectors import EmailSendRequest, dry_run_email, send_email

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_EMAIL_CONNECTOR_INTEGRATION", "").lower() not in {"1", "true", "yes"},
    reason="Resend email connector integration tests are opt-in.",
)


def _first_allowlisted_recipient() -> str:
    values = [
        item.strip()
        for item in os.environ.get("EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST", "").split(",")
        if item.strip() and not item.strip().startswith("@")
    ]
    if not values:
        pytest.skip("EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST must include an exact recipient.")
    return values[0]


def test_resend_integration_dry_run_does_not_call_provider() -> None:
    if os.environ.get("EMAIL_CONNECTOR_PROVIDER", "").lower() != "resend":
        pytest.skip("EMAIL_CONNECTOR_PROVIDER must be resend.")
    if not os.environ.get("RESEND_API_KEY"):
        pytest.skip("RESEND_API_KEY is required for opt-in Resend integration coverage.")

    receipt = dry_run_email(
        EmailSendRequest(
            provider="resend",
            mode="dry_run",
            to=[_first_allowlisted_recipient()],
            subject="ForgeGraph email connector dry run",
            text="Dry-run only. No provider call is made.",
            idempotency_key="resend-integration-dry-run",
        )
    ).as_dict()

    assert receipt["provider"] == "resend"
    assert receipt["mode"] == "dry_run"
    assert receipt["evidence_mode"] == "sandbox"


def test_resend_real_send_requires_explicit_real_send_permission() -> None:
    if os.environ.get("EMAIL_CONNECTOR_PROVIDER", "").lower() != "resend":
        pytest.skip("EMAIL_CONNECTOR_PROVIDER must be resend.")
    if not os.environ.get("RESEND_API_KEY"):
        pytest.skip("RESEND_API_KEY is required for Resend integration coverage.")
    if os.environ.get("EMAIL_CONNECTOR_ALLOW_REAL_SEND", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("EMAIL_CONNECTOR_ALLOW_REAL_SEND=true is required for real provider send.")
    from_email = os.environ.get("EMAIL_CONNECTOR_DEFAULT_FROM_EMAIL", "").strip()
    if not from_email:
        pytest.skip("EMAIL_CONNECTOR_DEFAULT_FROM_EMAIL is required for real provider send.")

    recipient = _first_allowlisted_recipient()
    receipt = send_email(
        EmailSendRequest(
            provider="resend",
            mode="real_send",
            from_email=from_email,
            from_name=os.environ.get("EMAIL_CONNECTOR_DEFAULT_FROM_NAME", "").strip(),
            to=[recipient],
            subject="ForgeGraph email connector integration",
            text="This explicit integration test send includes unsubscribe.",
            idempotency_key=f"resend-integration-real-send:{recipient}",
            requires_unsubscribe_footer=True,
        ),
        approved=True,
        policy_allows_live=True,
    ).as_dict()

    assert receipt["provider"] == "resend"
    assert receipt["mode"] == "real_send"
    assert receipt["evidence_mode"] == "provider_send"
    assert receipt["status"] == "accepted"
