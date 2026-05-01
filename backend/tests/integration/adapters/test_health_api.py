from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework import status

pytestmark = pytest.mark.django_db


@override_settings(
    ENGINE_CALLBACK_SECRET="test-secret",
    RUNTIME_TOOL_SECRET="runtime-tool-secret",
    FRONTEND_URL="http://localhost:3000",
    READINESS_REQUIRE_ENGINE=False,
    FORGEGRAPH_ALLOW_INSECURE_TRANSPORT=True,
)
def test_root_readiness_endpoint_returns_success(api_client):
    response = api_client.get("/ready")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["runtime"]["ready"] is True
    assert response.json()["checks"]["database"]["ready"] is True
    assert response.json()["checks"]["cache"]["ready"] is True


@override_settings(
    ENGINE_CALLBACK_SECRET="",
    RUNTIME_TOOL_SECRET="",
    FRONTEND_URL="not-a-url",
    READINESS_REQUIRE_ENGINE=False,
)
def test_root_readiness_endpoint_surfaces_runtime_validation_failures(api_client):
    response = api_client.get("/ready")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["runtime"]["ready"] is False
    assert payload["checks"]["runtime"]["errors"]


@override_settings(
    ENGINE_CALLBACK_SECRET="test-secret",
    RUNTIME_TOOL_SECRET="runtime-tool-secret",
    FRONTEND_URL="http://localhost:3000",
    READINESS_REQUIRE_ENGINE=False,
    READINESS_REQUIRE_RUNTIME_TRANSPORT=True,
    FORGEGRAPH_ALLOW_INSECURE_TRANSPORT=True,
    SLO_QUEUE_MAX_DEPTH=10,
)
def test_root_readiness_endpoint_includes_runtime_transport_when_required(api_client):
    snapshot = SimpleNamespace(
        error="",
        dead_letter_count=0,
        backlog=0,
        source="redis",
        stream_length=0,
        pending=0,
        lag=0,
        consumer_idle_ms=0,
        oldest_pending_idle_ms=0,
    )

    with patch(
        "adapters.api.health.readiness.get_runtime_transport_observability_snapshot",
        return_value=snapshot,
    ):
        response = api_client.get("/ready")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["checks"]["runtime_transport"]["ready"] is True
    assert payload["checks"]["runtime_transport"]["dead_letter_count"] == 0


@override_settings(
    ENGINE_CALLBACK_SECRET="test-secret",
    RUNTIME_TOOL_SECRET="runtime-tool-secret",
    FRONTEND_URL="http://localhost:3000",
    READINESS_REQUIRE_ENGINE=False,
    READINESS_REQUIRE_RUNTIME_TRANSPORT=True,
    FORGEGRAPH_ALLOW_INSECURE_TRANSPORT=True,
    SLO_QUEUE_MAX_DEPTH=10,
)
def test_root_readiness_endpoint_fails_on_runtime_transport_dead_letters(api_client):
    snapshot = SimpleNamespace(
        error="",
        dead_letter_count=1,
        backlog=0,
        source="redis",
        stream_length=1,
        pending=0,
        lag=0,
        consumer_idle_ms=0,
        oldest_pending_idle_ms=0,
    )

    with patch(
        "adapters.api.health.readiness.get_runtime_transport_observability_snapshot",
        return_value=snapshot,
    ):
        response = api_client.get("/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["checks"]["runtime_transport"]["ready"] is False
    assert payload["checks"]["runtime_transport"]["dead_letter_count"] == 1
