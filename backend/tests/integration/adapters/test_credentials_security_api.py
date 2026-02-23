from __future__ import annotations

import json
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from django.test import override_settings
from rest_framework import status

from application.services.oauth import OAuthProviderConfig
from infrastructure.crypto.encryption import EncryptionService, decrypt_api_key, encrypt_api_key
from infrastructure.orm.models import APIKey
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configure_encryption_key(settings):
    settings.ENCRYPTION_KEY = "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI="
    EncryptionService._instance = None
    yield
    EncryptionService._instance = None


def test_credential_revoke_then_rotate(authenticated_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="openai",
        name="prod-openai",
        encrypted_key=encrypt_api_key("openai-old-secret"),
        encrypted_refresh_token=encrypt_api_key("refresh-old"),
    )

    revoke_response = authenticated_client.post(
        f"/api/credentials/{credential.id}/revoke",
        {"reason": "Compromised"},
        format="json",
    )
    assert revoke_response.status_code == status.HTTP_200_OK
    assert revoke_response.data["data"]["revoked"] is True

    credential.refresh_from_db()
    assert credential.encrypted_refresh_token is None
    assert isinstance(credential.token_metadata, dict)
    assert credential.token_metadata.get("revoked") is True

    list_response = authenticated_client.get("/api/credentials/")
    assert list_response.status_code == status.HTTP_200_OK
    item = next(row for row in list_response.data["data"] if row["id"] == str(credential.id))
    assert item["revoked"] is True
    assert item["health_status"] == "revoked"

    rotate_response = authenticated_client.post(
        f"/api/credentials/{credential.id}/rotate",
        {
            "api_key": "openai-new-secret",
            "refresh_token": "refresh-new",
            "expires_in": 3600,
        },
        format="json",
    )
    assert rotate_response.status_code == status.HTTP_200_OK

    credential.refresh_from_db()
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "openai-new-secret"
    assert credential.encrypted_refresh_token is not None
    assert decrypt_api_key(bytes(credential.encrypted_refresh_token)) == "refresh-new"
    assert isinstance(credential.token_metadata, dict)
    assert credential.token_metadata.get("revoked") is not True


def test_http_test_rejects_revoked_credential(authenticated_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="gmail",
        name="gmail-revoked",
        encrypted_key=encrypt_api_key("gmail-token"),
        token_metadata={"revoked": True},
    )

    response = authenticated_client.post(
        "/api/integrations/http/test",
        {
            "method": "GET",
            "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            "provider": "gmail",
            "credential_id": str(credential.id),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "INVALID_CREDENTIALS"
    assert "revoked" in response.data["error"]["message"].lower()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_credential_endpoint_rejects_revoked_credential(api_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="openai",
        name="engine-revoked",
        encrypted_key=encrypt_api_key("openai-token"),
        token_metadata={"revoked": True},
    )

    timestamp_ms = int(time.time() * 1000)
    body = b""
    signature = s2s.build_signature("test-secret", str(timestamp_ms), body)
    response = api_client.get(
        f"/api/engine/credentials/{credential.id}?tenant_id={user.default_organization_id}",
        HTTP_X_FORGEGRAPH_TIMESTAMP=str(timestamp_ms),
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
    )

    assert response.status_code == status.HTTP_410_GONE
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["error"]["code"] == "CREDENTIAL_REVOKED"


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_credential_endpoint_refreshes_expired_oauth_token(api_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="gmail",
        name="gmail-expired",
        encrypted_key=encrypt_api_key("old-access-token"),
        encrypted_refresh_token=encrypt_api_key("refresh-token"),
        token_expires_at=timezone.now() - timedelta(minutes=1),
        token_metadata={"provider": "gmail"},
    )

    config = OAuthProviderConfig(
        provider="gmail",
        client_id="client-id",
        client_secret="client-secret",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        redirect_uri="http://localhost:3000/oauth/callback",
        scopes=[],
        authorize_extra_params={},
        token_extra_params={},
    )

    timestamp_ms = int(time.time() * 1000)
    body = b""
    signature = s2s.build_signature("test-secret", str(timestamp_ms), body)

    with patch(
        "adapters.api.engine.views.get_oauth_provider_config",
        return_value=(config, []),
    ), patch(
        "adapters.api.engine.views.exchange_refresh_token_for_access_token",
        return_value={
            "access_token": "new-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    ):
        response = api_client.get(
            f"/api/engine/credentials/{credential.id}?tenant_id={user.default_organization_id}",
            HTTP_X_FORGEGRAPH_TIMESTAMP=str(timestamp_ms),
            HTTP_X_FORGEGRAPH_SIGNATURE=signature,
        )

    assert response.status_code == status.HTTP_200_OK
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["data"]["api_key"] == "new-access-token"

    credential.refresh_from_db()
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "new-access-token"
    assert credential.token_expires_at is not None
    assert credential.token_expires_at > timezone.now()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_credential_endpoint_returns_refresh_failed_when_refresh_errors(api_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="gmail",
        name="gmail-refresh-fails",
        encrypted_key=encrypt_api_key("old-access-token"),
        encrypted_refresh_token=encrypt_api_key("refresh-token"),
        token_expires_at=timezone.now() - timedelta(minutes=1),
        token_metadata={"provider": "gmail"},
    )

    config = OAuthProviderConfig(
        provider="gmail",
        client_id="client-id",
        client_secret="client-secret",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        redirect_uri="http://localhost:3000/oauth/callback",
        scopes=[],
        authorize_extra_params={},
        token_extra_params={},
    )

    timestamp_ms = int(time.time() * 1000)
    signature = s2s.build_signature("test-secret", str(timestamp_ms), b"")

    with patch(
        "adapters.api.engine.views.get_oauth_provider_config",
        return_value=(config, []),
    ), patch(
        "adapters.api.engine.views.exchange_refresh_token_for_access_token",
        side_effect=ValueError("refresh failed"),
    ):
        response = api_client.get(
            f"/api/engine/credentials/{credential.id}?tenant_id={user.default_organization_id}",
            HTTP_X_FORGEGRAPH_TIMESTAMP=str(timestamp_ms),
            HTTP_X_FORGEGRAPH_SIGNATURE=signature,
        )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["error"]["code"] == "CREDENTIAL_REFRESH_FAILED"
