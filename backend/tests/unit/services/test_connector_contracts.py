from __future__ import annotations

import pytest
from django.apps import apps

from application.services.email_connectors import (
    EMAIL_MODE_REAL_SEND,
    EmailConnectorError,
    EmailSendRequest,
    FakeEmailProviderAdapter,
    dry_run_email,
)
from application.services.email_connectors import (
    sanitize_provider_error as sanitize_email_provider_error,
)
from application.services.social_connectors import (
    SOCIAL_MODE_PROVIDER_PUBLISH,
    FakeSocialProviderAdapter,
    SocialConnectorError,
    SocialPublishRequest,
    dry_run_social_publish,
    record_manual_publish_evidence,
)
from application.services.social_connectors import (
    sanitize_provider_error as sanitize_social_provider_error,
)
from application.services.whatsapp_connectors import (
    WHATSAPP_MODE_REAL_SEND,
    FakeWhatsAppAdapter,
    WhatsAppConnectorError,
    WhatsAppSendRequest,
    dry_run_whatsapp,
)
from application.services.whatsapp_connectors import (
    sanitize_provider_error as sanitize_whatsapp_provider_error,
)
from tests.helpers.connector_contracts import (
    assert_failure_receipt_contract,
    assert_no_forbidden_connector_material,
    assert_pii_minimized_receipt,
    assert_success_receipt_contract,
)


def test_shared_contract_accepts_sanitized_email_receipts() -> None:
    dry_run = dry_run_email(
        EmailSendRequest(
            provider="fake",
            mode="dry_run",
            to=["Owner@Example.com"],
            subject="Client notice",
            html="<p>Private message body</p>",
            text="Private message body",
            idempotency_key="email-contract-dry-run",
        )
    ).as_dict()
    assert_success_receipt_contract(dry_run, expected_evidence_mode="sandbox")
    assert_pii_minimized_receipt(dry_run)

    provider_send = (
        FakeEmailProviderAdapter()
        .send(
            EmailSendRequest(
                provider="fake",
                mode=EMAIL_MODE_REAL_SEND,
                from_email="sender@example.com",
                to=["allowed@example.com"],
                subject="Approved notice",
                text="Private message body with unsubscribe",
                idempotency_key="email-contract-provider",
            )
        )
        .as_dict()
    )
    assert_success_receipt_contract(
        provider_send, expected_evidence_mode="provider_send", allowed_statuses=("accepted",)
    )
    assert_pii_minimized_receipt(provider_send)


def test_shared_contract_accepts_sanitized_whatsapp_receipts() -> None:
    dry_run = dry_run_whatsapp(
        WhatsAppSendRequest(
            provider="fake",
            mode="dry_run",
            to=["+1 (555) 010-1234"],
            text="Private message body",
            idempotency_key="message-contract-dry-run",
        )
    ).as_dict()
    assert_success_receipt_contract(dry_run, expected_evidence_mode="sandbox")
    assert_pii_minimized_receipt(dry_run)

    web_automation = (
        FakeWhatsAppAdapter()
        .send(
            WhatsAppSendRequest(
                provider="fake",
                mode=WHATSAPP_MODE_REAL_SEND,
                to=["+15550101234"],
                text="Private message body",
                idempotency_key="message-contract-provider",
                operator_confirmed=True,
            )
        )
        .as_dict()
    )
    assert_success_receipt_contract(
        web_automation, expected_evidence_mode="web_automation", allowed_statuses=("accepted",)
    )
    assert_pii_minimized_receipt(web_automation)


def test_shared_contract_accepts_sanitized_social_receipts() -> None:
    request = SocialPublishRequest(
        provider="fake",
        platform="configured_platform",
        mode="dry_run",
        account_id="account-123",
        asset_ids=["asset-public-safe"],
        caption="Private caption",
        idempotency_key="social-contract-dry-run",
        asset_approved=True,
        caption_approved=True,
    )
    dry_run = dry_run_social_publish(request).as_dict()
    assert_success_receipt_contract(dry_run, expected_evidence_mode="sandbox")
    assert_pii_minimized_receipt(dry_run)

    manual = record_manual_publish_evidence(
        SocialPublishRequest(
            provider="manual",
            platform="configured_platform",
            mode="manual_publish_record",
            account_id="account-123",
            asset_ids=["asset-public-safe"],
            caption="Private caption",
            external_post_url="https://social.example/posts/private-id",
            external_post_id="private-post-id",
            idempotency_key="social-contract-manual",
            asset_approved=True,
            caption_approved=True,
            operator_confirmed=True,
        )
    ).as_dict()
    assert_success_receipt_contract(
        manual, expected_evidence_mode="manual_publish", allowed_statuses=("recorded",)
    )
    assert_pii_minimized_receipt(manual)

    provider = (
        FakeSocialProviderAdapter()
        .publish(
            SocialPublishRequest(
                provider="fake",
                platform="configured_platform",
                mode=SOCIAL_MODE_PROVIDER_PUBLISH,
                account_id="account-123",
                asset_ids=["asset-public-safe"],
                caption="Private caption",
                media_url="https://cdn.example/private.jpg",
                idempotency_key="social-contract-provider",
                asset_approved=True,
                caption_approved=True,
            )
        )
        .as_dict()
    )
    assert_success_receipt_contract(
        provider, expected_evidence_mode="provider_publish", allowed_statuses=("accepted",)
    )
    assert_pii_minimized_receipt(provider)


def test_shared_failure_contract_bounds_and_sanitizes_connector_errors() -> None:
    email_error = sanitize_email_provider_error(
        EmailConnectorError(
            "provider_http_error",
            "Bearer secret-api-key failed for owner@example.com with <p>Private message body</p>",
            provider="resend",
            mode="real_send",
        )
    )
    assert_failure_receipt_contract(email_error)

    whatsapp_error = sanitize_whatsapp_provider_error(
        WhatsAppConnectorError(
            "provider_http_error",
            "QR session-secret failed for +1 555 010 1234",
            provider="open_wa_web",
            mode="real_send",
        )
    )
    assert_failure_receipt_contract(whatsapp_error)

    social_error = sanitize_social_provider_error(
        SocialConnectorError(
            "provider_http_error",
            "Bearer meta-secret-token failed for https://cdn.example/private.jpg",
            provider="meta_graph",
            mode="provider_publish",
        )
    )
    assert_failure_receipt_contract(social_error)


def test_no_vertical_connector_routes_or_core_models_are_introduced() -> None:
    model_names = {model.__name__ for model in apps.get_models()}
    for forbidden_prefix in ("Marketing", "Instagram", "Facebook", "Atlas"):
        assert not any(name.startswith(forbidden_prefix) for name in model_names)

    url_modules = [
        "adapters.api.urls",
        "config.urls",
    ]
    for module_name in url_modules:
        module = __import__(module_name, fromlist=["urlpatterns"])
        assert_no_forbidden_connector_material(
            [
                str(getattr(pattern, "pattern", ""))
                for pattern in getattr(module, "urlpatterns", [])
            ],
            extra_forbidden=("/api/marketing", "/api/atlas", "/api/legacy"),
        )


def test_landing_connector_contract_skips_until_connector_exists() -> None:
    pytest.skip(
        "Landing/CMS connector is not implemented; enable this contract when a generic landing connector exists."
    )


def test_analytics_connector_contract_skips_until_connector_exists() -> None:
    pytest.skip(
        "Analytics/performance connector is not implemented; enable this contract when a generic analytics connector exists."
    )
