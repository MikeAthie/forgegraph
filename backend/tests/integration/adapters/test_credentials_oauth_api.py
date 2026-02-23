from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone
from rest_framework import status

from infrastructure.crypto.encryption import EncryptionService, decrypt_api_key, encrypt_api_key
from infrastructure.orm.models import APIKey

pytestmark = pytest.mark.django_db


class _MockTokenResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def _configure_encryption_key(settings):
    settings.ENCRYPTION_KEY = "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI="
    EncryptionService._instance = None
    yield
    EncryptionService._instance = None


def _configure_provider_env(monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    tokenized = provider.upper()
    monkeypatch.setenv(f"OAUTH_{tokenized}_CLIENT_ID", f"{provider}-client-id")
    monkeypatch.setenv(f"OAUTH_{tokenized}_CLIENT_SECRET", f"{provider}-client-secret")
    monkeypatch.setenv(f"OAUTH_{tokenized}_REDIRECT_URI", "http://localhost:3000/oauth/callback")


def _configure_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-shared-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-shared-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:3000/oauth/callback")


def test_oauth_provider_status_shows_supported_providers(authenticated_client):
    response = authenticated_client.get("/api/credentials/oauth/providers")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    providers = {item["provider"] for item in data}
    assert providers == {
        "gmail",
        "google_calendar",
        "google_tasks",
        "notion",
        "slack",
        "jira",
        "linear",
        "hubspot",
        "google_drive",
    }
    assert any(item["configured"] is False for item in data)


def test_oauth_start_returns_config_error_when_provider_not_configured(authenticated_client):
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "notion"},
        format="json",
    )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["error"]["code"] == "CONFIG_ERROR"
    assert "Missing configuration fields" in payload["error"]["message"]


def test_oauth_provider_config_put_is_read_only(authenticated_client):
    response = authenticated_client.put(
        "/api/credentials/oauth/providers/gmail",
        {
            "client_id": "gmail-client-id",
            "client_secret": "gmail-client-secret",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "CONFIG_READ_ONLY"


def test_oauth_start_and_callback_create_credential(authenticated_client, user, monkeypatch):
    _configure_provider_env(monkeypatch, "notion")

    start_response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "notion", "name": "Notion Production"},
        format="json",
    )
    assert start_response.status_code == status.HTTP_200_OK
    start_payload = start_response.json()["data"]
    assert "authorize_url" in start_payload
    state = parse_qs(urlparse(start_payload["authorize_url"]).query)["state"][0]

    with patch("application.services.oauth.requests.post") as mock_post:
        mock_post.return_value = _MockTokenResponse(
            {
                "access_token": "notion-access-token",
                "refresh_token": "notion-refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "workspace.read",
            }
        )
        callback_response = authenticated_client.post(
            "/api/credentials/oauth/callback",
            {"code": "oauth-code", "state": state},
            format="json",
        )

    assert callback_response.status_code == status.HTTP_201_CREATED
    callback_payload = callback_response.json()["data"]
    assert callback_payload["provider"] == "notion"
    assert callback_payload["name"] == "Notion Production"
    assert callback_payload["is_oauth_connection"] is True
    assert APIKey.objects.filter(
        organization=user.default_organization,
        provider="notion",
        name="Notion Production",
    ).exists()
    key = APIKey.objects.get(
        organization=user.default_organization,
        provider="notion",
        name="Notion Production",
    )
    assert key.encrypted_refresh_token is not None
    assert key.token_expires_at is not None
    assert decrypt_api_key(bytes(key.encrypted_refresh_token)) == "notion-refresh-token"


def test_oauth_callback_fails_when_token_response_missing_access_token(authenticated_client, monkeypatch):
    _configure_google_env(monkeypatch)

    start_response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "gmail"},
        format="json",
    )
    assert start_response.status_code == status.HTTP_200_OK
    state = parse_qs(urlparse(start_response.json()["data"]["authorize_url"]).query)["state"][0]

    with patch("application.services.oauth.requests.post") as mock_post:
        mock_post.return_value = _MockTokenResponse({"token_type": "Bearer"})
        callback_response = authenticated_client.post(
            "/api/credentials/oauth/callback",
            {"code": "oauth-code", "state": state},
            format="json",
        )

    assert callback_response.status_code == status.HTTP_400_BAD_REQUEST
    assert callback_response.json()["error"]["code"] == "OAUTH_EXCHANGE_FAILED"


def test_oauth_start_rejects_unsupported_provider(authenticated_client):
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "telegram"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oauth_start_for_slack_works_after_provider_config(authenticated_client, monkeypatch):
    _configure_provider_env(monkeypatch, "slack")
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "slack"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"]
    assert payload["provider"] == "slack"
    assert "slack.com" in payload["authorize_url"]


def test_oauth_start_for_hubspot_works_after_provider_config(authenticated_client, monkeypatch):
    _configure_provider_env(monkeypatch, "hubspot")
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "hubspot"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"]
    assert payload["provider"] == "hubspot"
    assert "hubspot.com" in payload["authorize_url"]


def test_oauth_start_for_google_calendar_works_after_provider_config(authenticated_client, monkeypatch):
    _configure_google_env(monkeypatch)
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "google_calendar"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"]
    assert payload["provider"] == "google_calendar"
    assert "accounts.google.com" in payload["authorize_url"]


def test_oauth_start_for_google_tasks_works_after_provider_config(authenticated_client, monkeypatch):
    _configure_google_env(monkeypatch)
    response = authenticated_client.post(
        "/api/credentials/oauth/start",
        {"provider": "google_tasks"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"]
    assert payload["provider"] == "google_tasks"
    assert "accounts.google.com" in payload["authorize_url"]


def test_credentials_list_marks_expired_oauth_token_for_reauth(authenticated_client, user):
    APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="notion",
        name="Notion Expired",
        encrypted_key=encrypt_api_key("expired-token"),
        token_expires_at=timezone.now() - timedelta(hours=1),
    )

    response = authenticated_client.get("/api/credentials/")
    assert response.status_code == status.HTTP_200_OK
    item = next(entry for entry in response.json()["data"] if entry["name"] == "Notion Expired")
    assert item["health_status"] == "expired"
    assert item["requires_reauth"] is True
    assert "Reconnect" in item["health_message"]
    assert item["is_oauth_connection"] is True


def test_credentials_list_does_not_mark_manual_oauth_provider_api_key_as_oauth(
    authenticated_client, user
):
    APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="gmail",
        name="Gmail API key",
        encrypted_key=encrypt_api_key("api-key-value"),
    )

    response = authenticated_client.get("/api/credentials/")
    assert response.status_code == status.HTTP_200_OK
    item = next(entry for entry in response.json()["data"] if entry["name"] == "Gmail API key")
    assert item["is_oauth_connection"] is False
