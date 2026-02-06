"""Integration tests for HTTP node run-test API."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from rest_framework import status

from infrastructure.crypto.encryption import EncryptionService, encrypt_api_key
from infrastructure.orm.models import APIKey

pytestmark = pytest.mark.django_db


class _MockResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        ok: bool = True,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.ok = ok
        self.headers = headers or {"Content-Type": "application/json"}
        self._json_body = json_body if json_body is not None else {"ok": True}
        self.text = text

    def json(self) -> Any:
        return self._json_body


@pytest.fixture(autouse=True)
def _configure_encryption_key(settings):
    settings.ENCRYPTION_KEY = "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI="
    EncryptionService._instance = None
    yield
    EncryptionService._instance = None


def test_http_node_test_requires_authentication(api_client):
    response = api_client.post(
        "/api/integrations/http/test",
        {"method": "GET", "url": "https://example.com"},
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_http_node_test_injects_bearer_from_credential(authenticated_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="gmail",
        name="gmail-prod",
        encrypted_key=encrypt_api_key("gmail-token-123"),
    )

    captured_headers: dict[str, str] = {}

    def _mock_request(**kwargs: Any) -> _MockResponse:
        nonlocal captured_headers
        captured_headers = dict(kwargs.get("headers") or {})
        return _MockResponse(json_body={"messages": []})

    with patch(
        "adapters.api.integrations.http_test_views.requests.request", side_effect=_mock_request
    ):
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

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["status_code"] == 200
    assert captured_headers.get("Authorization") == "Bearer gmail-token-123"


def test_http_node_test_injects_twilio_basic_auth(authenticated_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="twilio",
        name="twilio-auth",
        encrypted_key=encrypt_api_key("twilio-token-456"),
    )

    captured_headers: dict[str, str] = {}

    def _mock_request(**kwargs: Any) -> _MockResponse:
        nonlocal captured_headers
        captured_headers = dict(kwargs.get("headers") or {})
        return _MockResponse(json_body={"sid": "SM123"})

    with patch(
        "adapters.api.integrations.http_test_views.requests.request", side_effect=_mock_request
    ):
        response = authenticated_client.post(
            "/api/integrations/http/test",
            {
                "method": "POST",
                "url": "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json",
                "provider": "twilio",
                "credential_id": str(credential.id),
                "account_sid": "AC123",
                "body": "To=%2B15550001111&From=%2B15550002222&Body=hello",
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            },
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert captured_headers.get("Authorization", "").startswith("Basic ")


def test_http_node_test_rejects_provider_mismatch(authenticated_client, user):
    credential = APIKey.objects.create(
        organization=user.default_organization,
        user=user,
        provider="telegram",
        name="telegram-bot",
        encrypted_key=encrypt_api_key("bot-token"),
    )

    response = authenticated_client.post(
        "/api/integrations/http/test",
        {
            "method": "GET",
            "url": "https://example.com",
            "provider": "gmail",
            "credential_id": str(credential.id),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "INVALID_CREDENTIALS"
