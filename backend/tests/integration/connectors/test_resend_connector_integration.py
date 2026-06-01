from __future__ import annotations

import os

import pytest

from application.services.email_connectors import EmailSendRequest, dry_run_email
from tests.helpers.connector_contracts import assert_success_receipt_contract


def test_resend_connector_integration_is_opt_in_and_does_not_send_by_default() -> None:
    if os.environ.get("RUN_EMAIL_CONNECTOR_INTEGRATION", "").lower() != "true":
        pytest.skip(
            "Set RUN_EMAIL_CONNECTOR_INTEGRATION=true to enable Resend connector integration checks."
        )
    if os.environ.get("EMAIL_CONNECTOR_PROVIDER", "").lower() != "resend":
        pytest.skip("Set EMAIL_CONNECTOR_PROVIDER=resend for Resend connector integration checks.")
    if not os.environ.get("RESEND_API_KEY"):
        pytest.skip("Set RESEND_API_KEY for Resend connector integration checks.")
    if not os.environ.get("EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST"):
        pytest.skip(
            "Set EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST for Resend connector integration checks."
        )

    receipt = dry_run_email(
        EmailSendRequest(
            provider="resend",
            mode="dry_run",
            to=[os.environ["EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST"].split(",")[0].strip()],
            subject="ForgeGraph connector integration dry run",
            text="Local dry run. No provider send is performed by this test.",
            idempotency_key="resend-integration-dry-run",
        )
    ).as_dict()

    assert_success_receipt_contract(receipt, expected_evidence_mode="sandbox")
    if os.environ.get("EMAIL_CONNECTOR_ALLOW_REAL_SEND", "").lower() == "true":
        pytest.skip(
            "Real Resend sends are intentionally excluded from the default integration test."
        )
