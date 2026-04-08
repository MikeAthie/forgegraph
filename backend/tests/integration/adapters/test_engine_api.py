import json
import time
from typing import Any
from uuid import uuid4

import pytest
from django.utils import timezone

from infrastructure.orm.models import Graph, GraphVersion, NodeRun, Run, User
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


def _signed_headers(secret: str) -> dict[str, str]:
    timestamp_ms = str(int(time.time() * 1000))
    signature = s2s.build_signature(secret, timestamp_ms, b"")
    return {
        "HTTP_X_FORGEGRAPH_TIMESTAMP": timestamp_ms,
        "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
    }


def _signed_json_request(secret: str, payload: dict[str, Any]) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    timestamp_ms = str(int(time.time() * 1000))
    signature = s2s.build_signature(secret, timestamp_ms, body.encode("utf-8"))
    return body, {
        "HTTP_X_FORGEGRAPH_TIMESTAMP": timestamp_ms,
        "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
    }


@pytest.fixture(autouse=True)
def _engine_callback_secret(settings):
    settings.ENGINE_CALLBACK_SECRET = "test-secret"


class TestEngineRunApi:
    def test_run_detail_round_trip(self, api_client):
        user = User.objects.create_user(email="engine-api@example.com", password="password123")
        graph = Graph.objects.create(owner=user, name="Engine API Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [], "edges": []},
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="pending",
            input_json={"ticket": "FG-1"},
        )

        response = api_client.get(
            f"/api/engine/runs/{run.id}",
            **_signed_headers("test-secret"),
        )

        assert response.status_code == 200
        assert response.data["data"]["status"] == "pending"
        assert response.data["data"]["graph_version_id"] == str(version.id)
        assert response.data["data"]["recovery_policy"] == "fail"

        patch_payload = {
            "status": "running",
            "trace_id": "trace-123",
            "output_json": {"step": "started"},
        }
        body, headers = _signed_json_request("test-secret", patch_payload)
        response = api_client.generic(
            "PATCH",
            f"/api/engine/runs/{run.id}",
            body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == 200
        run.refresh_from_db()
        assert run.status == "running"
        assert run.trace_id == "trace-123"
        assert run.output_json == {"step": "started"}
        assert run.last_progress_at is not None
        assert run.recovery_state == "active"

    def test_run_detail_rejects_terminal_status_regression(self, api_client):
        user = User.objects.create_user(
            email="engine-status-guard@example.com",
            password="password123",
        )
        graph = Graph.objects.create(owner=user, name="Engine Status Guard Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [], "edges": []},
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        patch_payload = {
            "status": "running",
        }
        body, headers = _signed_json_request("test-secret", patch_payload)
        response = api_client.generic(
            "PATCH",
            f"/api/engine/runs/{run.id}",
            body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == "INVALID_STATE"
        run.refresh_from_db()
        assert run.status == "succeeded"

    def test_checkpoint_upsert_preserves_newer_step(self, api_client):
        user = User.objects.create_user(
            email="engine-checkpoint@example.com", password="password123"
        )
        graph = Graph.objects.create(owner=user, name="Checkpoint Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [], "edges": []},
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        first_payload = {
            "node_id": "node_a",
            "step_index": 2,
            "state_snapshot": {"vars": {"alpha": 1}},
            "completed_nodes": ["node_a"],
            "skipped_nodes": [],
            "graph_json": json.dumps({"nodes": [{"id": "node_a"}], "edges": []}),
        }
        body, headers = _signed_json_request("test-secret", first_payload)
        response = api_client.generic(
            "PUT",
            f"/api/engine/runs/{run.id}/checkpoint",
            body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == 200
        assert response.data["data"]["step_index"] == 2

        stale_payload = {
            "node_id": "node_b",
            "step_index": 1,
            "state_snapshot": {"vars": {"beta": 2}},
            "completed_nodes": ["node_b"],
            "skipped_nodes": [],
            "graph_json": json.dumps({"nodes": [{"id": "node_b"}], "edges": []}),
        }
        body, headers = _signed_json_request("test-secret", stale_payload)
        response = api_client.generic(
            "PUT",
            f"/api/engine/runs/{run.id}/checkpoint",
            body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == 200
        assert response.data["data"]["step_index"] == 2
        assert response.data["data"]["node_id"] == "node_a"

        response = api_client.get(
            f"/api/engine/runs/{run.id}/checkpoint",
            **_signed_headers("test-secret"),
        )
        assert response.status_code == 200
        assert response.data["data"]["step_index"] == 2
        assert response.data["data"]["completed_nodes"] == ["node_a"]

    def test_pause_state_round_trip_preserves_graph_json(self, api_client):
        user = User.objects.create_user(
            email="engine-pause-state@example.com",
            password="password123",
        )
        graph = Graph.objects.create(owner=user, name="Pause State Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "gate", "type": "human_gate"}], "edges": []},
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        graph_json = json.dumps(version.graph_json)
        payload = {
            "paused_node_id": "gate",
            "state_snapshot": {"input.ticket": "FG-123"},
            "completed_nodes": ["seed"],
            "skipped_nodes": [],
            "graph_json": graph_json,
            "tenant_id": str(user.default_organization_id),
        }
        body, headers = _signed_json_request("test-secret", payload)
        response = api_client.generic(
            "PUT",
            f"/api/engine/runs/{run.id}/pause-state",
            body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == 200
        assert response.data["data"]["paused_node_id"] == "gate"
        assert response.data["data"]["graph_json"] == graph_json

        response = api_client.get(
            f"/api/engine/runs/{run.id}/pause-state",
            **_signed_headers("test-secret"),
        )

        assert response.status_code == 200
        assert response.data["data"]["paused_node_id"] == "gate"
        assert response.data["data"]["state_snapshot"] == {"input.ticket": "FG-123"}
        assert response.data["data"]["completed_nodes"] == ["seed"]
        assert response.data["data"]["graph_json"] == graph_json

        run.refresh_from_db()
        assert run.pause_state_json is not None
        assert run.pause_state_json["graph_json"] == graph_json

    def test_node_run_upsert_and_latest_lookup(self, api_client):
        user = User.objects.create_user(email="engine-node-run@example.com", password="password123")
        graph = Graph.objects.create(owner=user, name="Node Run Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [], "edges": []},
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        first_started_at = timezone.now().isoformat()
        first_payload = {
            "node_type": "prompt",
            "status": "running",
            "attempt": 1,
            "started_at": first_started_at,
            "input_json": {"prompt": "hello"},
            "trace_id": "trace-a",
            "span_id": "span-a",
        }
        body, headers = _signed_json_request("test-secret", first_payload)
        response = api_client.generic(
            "PUT",
            f"/api/engine/runs/{run.id}/node-runs/node_1",
            body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == 200
        node_run_id = response.data["data"]["id"]

        second_payload = {
            "id": str(uuid4()),
            "node_type": "prompt",
            "status": "succeeded",
            "attempt": 2,
            "started_at": timezone.now().isoformat(),
            "ended_at": timezone.now().isoformat(),
            "output_json": {"ok": True},
            "trace_id": "trace-b",
            "span_id": "span-b",
        }
        body, headers = _signed_json_request("test-secret", second_payload)
        response = api_client.generic(
            "PUT",
            f"/api/engine/runs/{run.id}/node-runs/node_1",
            body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == 200
        assert response.data["data"]["attempt"] == 2

        response = api_client.get(
            f"/api/engine/runs/{run.id}/node-runs/node_1",
            **_signed_headers("test-secret"),
        )
        assert response.status_code == 200
        assert response.data["data"]["attempt"] == 2
        assert response.data["data"]["output_json"] == {"ok": True}

        response = api_client.get(
            f"/api/engine/runs/{run.id}/node-runs",
            **_signed_headers("test-secret"),
        )
        assert response.status_code == 200
        assert len(response.data["data"]) == 2
        assert {item["attempt"] for item in response.data["data"]} == {1, 2}

        stored_first = NodeRun.objects.get(id=node_run_id)
        assert stored_first.attempt == 1
        assert stored_first.input_json == {"prompt": "hello"}

    def test_memory_entry_round_trip(self, api_client):
        payload = {
            "namespace": "tenant-a",
            "key": "session-buffer",
            "value": {"messages": ["hello"]},
            "ttl_seconds": 60,
        }
        body, headers = _signed_json_request("test-secret", payload)
        response = api_client.generic(
            "PUT",
            "/api/engine/memory/entries",
            body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == 200
        assert response.data["data"]["stored"] is True

        response = api_client.get(
            "/api/engine/memory/entries",
            {"namespace": "tenant-a", "key": "session-buffer"},
            **_signed_headers("test-secret"),
        )
        assert response.status_code == 200
        assert response.data["data"]["value"] == {"messages": ["hello"]}

        response = api_client.delete(
            "/api/engine/memory/entries?namespace=tenant-a&key=session-buffer",
            **_signed_headers("test-secret"),
        )
        assert response.status_code == 200
        assert response.data["data"]["deleted"] is True
