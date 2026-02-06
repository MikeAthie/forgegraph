"""Integration tests for generic webhook APIs."""

from __future__ import annotations

from typing import Any, cast

import pytest
from rest_framework import status

from infrastructure.orm.models import Graph, GraphVersion, Run

pytestmark = pytest.mark.django_db


def _create_graph_version(user: Any, *, metadata: dict[str, Any] | None = None) -> GraphVersion:
    graph = Graph.objects.create(owner=user, name="Webhook Graph")
    graph_json: dict[str, Any] = {"nodes": [], "edges": []}
    if metadata is not None:
        graph_json["metadata"] = metadata
    return cast(
        GraphVersion,
        GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json),
    )


def test_generic_webhook_requires_secret_configuration(api_client, user):
    version = _create_graph_version(user)

    response = api_client.post(
        f"/api/integrations/webhook/{version.id}",
        {"message": "hello"},
        format="json",
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["error"]["code"] == "CONFIG_ERROR"
    assert Run.objects.count() == 0


def test_generic_webhook_rejects_invalid_secret(api_client, user):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"webhook": {"secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/webhook/{version.id}",
        {"message": "hello"},
        format="json",
        HTTP_X_FORGEGRAPH_WEBHOOK_SECRET="wrong-secret",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"]["code"] == "FORBIDDEN"
    assert Run.objects.count() == 0


def test_generic_webhook_creates_and_starts_run(api_client, user, mock_engine_client):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"webhook": {"secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/webhook/{version.id}",
        {"message": "trigger run", "thread_id": "customer-42", "payload": {"source": "crm"}},
        format="json",
        HTTP_X_FORGEGRAPH_WEBHOOK_SECRET="secret-123",
        HTTP_X_THREAD_ID="customer-42",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    run = Run.objects.get(id=response.data["data"]["id"])
    assert run.status == "running"
    assert run.thread_id is not None
    assert run.input_json["channel"] == "webhook"
    assert run.input_json["message"] == "trigger run"
    assert run.input_json["webhook"]["payload"]["thread_id"] == "customer-42"

    start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
    assert len(start_calls) == 1
    assert start_calls[0][1]["run_id"] == run.id
    assert start_calls[0][1]["input_json"]["channel"] == "webhook"


def test_generic_webhook_rejects_non_object_payload(api_client, user):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"webhook": {"secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/webhook/{version.id}",
        ["invalid"],
        format="json",
        HTTP_X_FORGEGRAPH_WEBHOOK_SECRET="secret-123",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert Run.objects.count() == 0
