"""
Pytest configuration and fixtures.
"""

import json
import time
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from adapters.gateways.grpc_engine_client import MockEngineClient
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import User
from infrastructure.security import s2s


@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()


@pytest.fixture
def user(db):
    """Create and return a test user."""
    user = User.objects.create_user(
        email="test@example.com",
        password="testpassword123",
    )
    ensure_default_organization(user)
    return user


@pytest.fixture
def authenticated_client(api_client, user):
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture(autouse=True)
def mock_engine_client():
    """Mock the engine client in all tests by default."""
    mock_client = MockEngineClient()
    with patch(
        "adapters.api.runs.views.get_engine_client",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def signed_engine_event_post(api_client):
    """Post a signed engine callback through the real S2S endpoint."""

    def _post(
        payload: dict[str, object], *, secret: str = "test-secret", timestamp_ms: int | None = None
    ):
        callback_timestamp = timestamp_ms or int(time.time() * 1000)
        body = json.dumps(payload)
        signature = s2s.build_signature(secret, str(callback_timestamp), body.encode("utf-8"))
        return api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            HTTP_X_FORGEGRAPH_TIMESTAMP=str(callback_timestamp),
            HTTP_X_FORGEGRAPH_SIGNATURE=signature,
        )

    return _post
