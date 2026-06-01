from __future__ import annotations

import os

import pytest

from application.services.whatsapp_connectors import WhatsAppSendRequest, dry_run_whatsapp
from tests.helpers.connector_contracts import assert_success_receipt_contract


def test_whatsapp_connector_integration_is_opt_in_and_does_not_message_by_default() -> None:
    if os.environ.get("RUN_WHATSAPP_WEB_AUTOMATION_INTEGRATION", "").lower() != "true":
        pytest.skip(
            "Set RUN_WHATSAPP_WEB_AUTOMATION_INTEGRATION=true to enable WhatsApp web automation checks."
        )
    if not os.environ.get("WHATSAPP_RECIPIENT_ALLOWLIST"):
        pytest.skip("Set WHATSAPP_RECIPIENT_ALLOWLIST for WhatsApp connector integration checks.")

    receipt = dry_run_whatsapp(
        WhatsAppSendRequest(
            provider=os.environ.get("WHATSAPP_CONNECTOR_PROVIDER", "fake"),
            mode="dry_run",
            to=[os.environ["WHATSAPP_RECIPIENT_ALLOWLIST"].split(",")[0].strip()],
            text="Local dry run. No WhatsApp message is performed by this test.",
            idempotency_key="whatsapp-integration-dry-run",
        )
    ).as_dict()

    assert_success_receipt_contract(receipt, expected_evidence_mode="sandbox")
    if os.environ.get("WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND", "").lower() == "true":
        pytest.skip(
            "Real WhatsApp sends are intentionally excluded from the default integration test."
        )
