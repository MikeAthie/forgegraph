from __future__ import annotations

import pytest

from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import OIDCProvider

pytestmark = pytest.mark.django_db


def test_sso_provider_get_returns_unavailable_status_when_unconfigured(authenticated_client):
    response = authenticated_client.get("/api/auth/sso/provider")

    assert response.status_code == 200
    assert response.data["status"] == {
        "state": "unavailable",
        "message": "No SSO provider is configured for this organization yet.",
    }


def test_sso_provider_get_returns_partial_status_when_disabled(authenticated_client, user):
    OIDCProvider.objects.create(
        tenant_id=user.default_organization_id,
        issuer_url="https://tenant.example.com",
        client_id="client-123",
        encrypted_client_secret=encrypt_api_key("secret-123"),
        audience="",
        email_domains=["example.com"],
        default_role="member",
        enabled=False,
    )

    response = authenticated_client.get("/api/auth/sso/provider")

    assert response.status_code == 200
    assert response.data["status"] == {
        "state": "partial",
        "message": "SSO configuration exists, but sign-in is currently disabled for this organization.",
    }
