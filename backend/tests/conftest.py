"""
Pytest configuration and fixtures.
"""

import importlib
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from adapters.gateways.grpc_engine_client import MockEngineClient
from application.services import run_snapshots
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import User
from infrastructure.security import s2s


class _InMemoryRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str):
        return self._values.get(key)

    def set(self, key: str, value: str) -> bool:
        self._values[key] = value
        return True

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        _ = ttl_seconds
        self._values[key] = value
        return True

    def delete(self, key: str) -> int:
        return 1 if self._values.pop(key, None) is not None else 0


@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()


@pytest.fixture
def user(db):
    """Create and return a test user."""
    user = User.objects.create_user(
        email=f"test-{uuid4().hex}@example.com",
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
    runs_pkg = importlib.import_module("adapters.api.runs")
    if not hasattr(runs_pkg, "responses"):
        runs_pkg.responses = SimpleNamespace(get_engine_client=lambda *args, **kwargs: mock_client)
    if not hasattr(runs_pkg, "common"):
        runs_pkg.common = SimpleNamespace(get_engine_client=lambda *args, **kwargs: mock_client)
    with (
        patch(
            "adapters.api.runs.responses.get_engine_client",
            return_value=mock_client,
        ),
        patch(
            "adapters.api.runs.common.get_engine_client",
            return_value=mock_client,
        ),
    ):
        yield mock_client


@pytest.fixture
def signed_engine_event_post(api_client):
    """Post a signed engine callback through the real S2S endpoint."""
    last_timestamp_ms = 0

    def _post(
        payload: dict[str, object], *, secret: str = "test-secret", timestamp_ms: int | None = None
    ):
        nonlocal last_timestamp_ms
        callback_timestamp = timestamp_ms or int(time.time() * 1000)
        if timestamp_ms is None and callback_timestamp <= last_timestamp_ms:
            callback_timestamp = last_timestamp_ms + 1
        last_timestamp_ms = callback_timestamp
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


@pytest.fixture(autouse=True)
def in_memory_run_snapshot_redis(monkeypatch):
    redis_client = _InMemoryRedis()
    monkeypatch.setattr(run_snapshots, "build_run_snapshot_redis_client", lambda: redis_client)
    yield redis_client
