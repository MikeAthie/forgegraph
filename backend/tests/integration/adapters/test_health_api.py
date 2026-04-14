import pytest
from django.test import override_settings
from rest_framework import status

pytestmark = pytest.mark.django_db


@override_settings(
    ENGINE_CALLBACK_SECRET="test-secret",
    FRONTEND_URL="http://localhost:3000",
    READINESS_REQUIRE_ENGINE=False,
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
