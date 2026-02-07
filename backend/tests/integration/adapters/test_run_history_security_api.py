from __future__ import annotations

import json
import time

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from infrastructure.orm.models import AuditLog, Graph, GraphVersion, NodeRun, Run
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


def _create_graph_version(user):
    graph = Graph.objects.create(owner=user, name="Security Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    return graph, version


def test_run_list_filters_by_failed_nodes(authenticated_client, user):
    _, version = _create_graph_version(user)
    run_ok = Run.objects.create(owner=user, graph_version=version, status="succeeded")
    run_bad = Run.objects.create(owner=user, graph_version=version, status="failed")
    NodeRun.objects.create(
        run=run_bad,
        node_id="node-a",
        node_type="prompt",
        status="failed",
        attempt=1,
    )

    response_true = authenticated_client.get("/api/runs/?has_failed_nodes=true")
    assert response_true.status_code == status.HTTP_200_OK
    ids_true = {row["id"] for row in response_true.data["data"]}
    assert str(run_bad.id) in ids_true
    assert str(run_ok.id) not in ids_true

    response_false = authenticated_client.get("/api/runs/?has_failed_nodes=false")
    assert response_false.status_code == status.HTTP_200_OK
    ids_false = {row["id"] for row in response_false.data["data"]}
    assert str(run_ok.id) in ids_false
    assert str(run_bad.id) not in ids_false


def test_run_start_audit_contains_version_context(authenticated_client, user):
    graph, version = _create_graph_version(user)

    response = authenticated_client.post(
        "/api/runs/start",
        {"graph_version_id": str(version.id), "input_json": {"x": 1}},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    run_id = response.data["data"]["id"]

    log = AuditLog.objects.filter(action="run.started", resource_id=run_id).latest("created_at")
    assert log.metadata["graph_id"] == str(graph.id)
    assert log.metadata["graph_version_id"] == str(version.id)
    assert log.metadata["graph_version"] == version.version
    assert log.metadata["trigger"] == "start"


@override_settings(RUN_INPUT_MAX_BYTES=32)
def test_start_run_rejects_oversized_input(authenticated_client, user):
    _, version = _create_graph_version(user)
    response = authenticated_client.post(
        "/api/runs/start",
        {"graph_version_id": str(version.id), "input_json": {"payload": "x" * 300}},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


@override_settings(RUN_MAX_ACTIVE_PER_TENANT=1)
def test_start_run_rejects_when_tenant_active_limit_reached(authenticated_client, user):
    _, version = _create_graph_version(user)
    Run.objects.create(
        owner=user,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )

    response = authenticated_client.post(
        "/api/runs/start",
        {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
        format="json",
    )
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["error"]["code"] == "RATE_LIMITED"


def test_run_detail_redacts_sensitive_fields(authenticated_client, user):
    _, version = _create_graph_version(user)
    run = Run.objects.create(
        owner=user,
        graph_version=version,
        status="failed",
        input_json={"api_key": "secret-value", "safe": "ok"},
        output_json={"authorization": "Bearer token-123"},
        error_message="failed with Bearer token-123",
    )
    NodeRun.objects.create(
        run=run,
        node_id="node-1",
        node_type="http",
        status="failed",
        input_json={"password": "hidden"},
        output_json={"safe": True},
        error_json={"token": "hidden-token"},
    )

    response = authenticated_client.get(f"/api/runs/{run.id}")
    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["input_json"]["api_key"] == "***REDACTED***"
    assert payload["output_json"]["authorization"] == "***REDACTED***"
    assert "***REDACTED***" in payload["error_message"]
    node = payload["node_runs"][0]
    assert node["input_json"]["password"] == "***REDACTED***"
    assert node["error_json"]["token"] == "***REDACTED***"


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_events_redact_sensitive_node_failure_payload(api_client, user):
    _, version = _create_graph_version(user)
    run = Run.objects.create(owner=user, graph_version=version, status="running")

    event = {
        "type": "node_failed",
        "run_id": str(run.id),
        "tenant_id": str(user.default_organization_id),
        "node_id": "prompt-1",
        "node_type": "prompt",
        "attempt": 1,
        "error": "Bearer sk-super-secret",
        "output": {"error": {"api_key": "sk-super-secret", "message": "bad token"}},
        "timestamp": int(time.time() * 1000),
    }
    body = json.dumps(event)
    timestamp_ms = int(time.time() * 1000)
    signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))

    response = api_client.post(
        "/api/runs/engine-events",
        data=body,
        content_type="application/json",
        HTTP_X_FORGEGRAPH_TIMESTAMP=str(timestamp_ms),
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
    )
    assert response.status_code == status.HTTP_200_OK

    node_run = NodeRun.objects.get(run=run, node_id="prompt-1", attempt=1)
    assert node_run.error_json is not None
    assert node_run.error_json["api_key"] == "***REDACTED***"
    assert "***REDACTED***" in str(node_run.error_json.get("error") or "")
