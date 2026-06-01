from __future__ import annotations

import os

import pytest
from django.conf import settings

from application.services.whatsapp_connectors import (
    OpenWaWebAutomationAdapter,
    WhatsAppSendRequest,
    send_whatsapp,
)

pytestmark = pytest.mark.django_db


def _integration_enabled() -> bool:
    return os.environ.get("RUN_WHATSAPP_WEB_AUTOMATION_INTEGRATION", "").lower() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.skipif(
    not _integration_enabled(), reason="WhatsApp web automation integration is opt-in."
)
def test_open_wa_sidecar_session_health_is_safe() -> None:
    if getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "") != "open_wa_web":
        pytest.skip("WHATSAPP_CONNECTOR_PROVIDER must be open_wa_web.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_ENABLED", False):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_ENABLED is required.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_SIDECAR_URL", ""):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_SIDECAR_URL is required.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_SESSION_REF", ""):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_SESSION_REF is required.")

    status = OpenWaWebAutomationAdapter().session_status()

    assert status in {
        "ready",
        "authenticated",
        "connected",
        "missing",
        "unreachable",
        "unhealthy",
        "unknown",
    }


@pytest.mark.skipif(
    not _integration_enabled(), reason="WhatsApp web automation integration is opt-in."
)
def test_open_wa_real_send_requires_explicit_safe_configuration() -> None:
    if getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "") != "open_wa_web":
        pytest.skip("WHATSAPP_CONNECTOR_PROVIDER must be open_wa_web.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_ENABLED", False):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_ENABLED is required.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_SIDECAR_URL", ""):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_SIDECAR_URL is required.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_SESSION_REF", ""):
        pytest.skip("WHATSAPP_WEB_AUTOMATION_SESSION_REF is required.")
    if not getattr(settings, "WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND", False):
        pytest.skip("Real send is disabled.")
    recipient = os.environ.get("WHATSAPP_WEB_AUTOMATION_TEST_RECIPIENT", "").strip()
    if not recipient:
        pytest.skip("WHATSAPP_WEB_AUTOMATION_TEST_RECIPIENT is required for real send.")

    receipt = send_whatsapp(
        WhatsAppSendRequest(
            provider="open_wa_web",
            mode="real_send",
            to=[recipient],
            text="ForgeGraph WhatsApp web automation integration test.",
            idempotency_key="whatsapp-web-automation-integration",
            operator_confirmed=True,
        ),
        approved=True,
        policy_allows_live=True,
    )

    assert receipt.status == "accepted"
    assert receipt.evidence_mode == "web_automation"
