"""
Integration tests for Run APIs.

Tests run history and run detail endpoints for Phase 4 observability MVP.
"""

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from infrastructure.orm.models import (
    ApprovalTask,
    Graph,
    GraphVersion,
    MemoryConfiguration,
    NodeRun,
    Run,
    RunCheckpoint,
    User,
)

pytestmark = pytest.mark.django_db


class TestRunList:
    """Tests for GET /api/runs/"""

    def test_list_runs_requires_authentication(self, api_client):
        response = api_client.get("/api/runs/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_runs_returns_user_runs_only(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        other_user = User.objects.create_user(email="other@example.com", password="password123")
        other_graph = Graph.objects.create(owner=other_user, name="Other Graph")
        other_version = GraphVersion.objects.create(
            graph=other_graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        Run.objects.create(owner=other_user, graph_version=other_version, status="succeeded")

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "meta" in response.data
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["id"] == str(run.id)

    def test_list_runs_includes_graph_context(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=2, graph_json={"nodes": [], "edges": []}
        )
        Run.objects.create(owner=user, graph_version=version, status="succeeded")

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        run_data = response.data["data"][0]
        assert run_data["graph_id"] == str(graph.id)
        assert run_data["graph_name"] == graph.name
        assert run_data["graph_version_id"] == str(version.id)
        assert run_data["graph_version"] == 2

    def test_list_runs_orders_null_started_at_last(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        run_new = Run.objects.create(
            owner=user, graph_version=version, status="succeeded", started_at=now
        )
        run_old = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=now - timedelta(hours=1),
        )
        run_null = Run.objects.create(
            owner=user, graph_version=version, status="pending", started_at=None
        )

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["data"]]
        assert ids[0] == str(run_new.id)
        assert ids[1] == str(run_old.id)
        assert ids[2] == str(run_null.id)


class TestRunDetail:
    """Tests for GET /api/runs/{run_id}"""

    def test_get_run_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        response = api_client.get(f"/api/runs/{run.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_run_returns_node_runs(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        node_run1 = NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(milliseconds=100),
            input_json={"a": 1},
            output_json={"ok": True},
        )
        node_run2 = NodeRun.objects.create(
            run=run,
            node_id="node_2",
            node_type="http",
            status="running",
            started_at=now + timedelta(seconds=1),
            input_json={},
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == str(run.id)
        assert response.data["data"]["graph_id"] == str(graph.id)
        assert response.data["data"]["graph_name"] == graph.name
        assert response.data["data"]["graph_version_id"] == str(version.id)
        assert response.data["data"]["graph_version"] == 1
        assert len(response.data["data"]["node_runs"]) == 2

        # Node run ordering and fields
        assert response.data["data"]["node_runs"][0]["id"] == str(node_run1.id)
        assert response.data["data"]["node_runs"][0]["duration_ms"] == 100
        assert response.data["data"]["node_runs"][1]["id"] == str(node_run2.id)

    def test_get_run_not_found_returns_standard_error(self, authenticated_client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/runs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data
        assert "meta" in response.data
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_get_run_for_other_user_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=other_user, graph_version=version, status="succeeded")

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"


class TestRunStart:
    """Tests for POST /api/runs/start"""

    def test_start_run_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = api_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_start_run_creates_run(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "data" in response.data
        run_data = response.data["data"]
        assert run_data["graph_version_id"] == str(version.id)
        # Status is "running" after engine accepts the run
        assert run_data["status"] == "running"
        assert run_data["input_json"] == {"hello": "world"}

        created_run_id = run_data["id"]
        assert Run.objects.filter(id=created_run_id, owner=user, graph_version=version).exists()

    def test_start_run_for_other_user_graph_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        api_client.force_authenticate(user=user)
        response = api_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_start_run_rejects_invalid_input_schema(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Schema Graph")
        graph_json = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                }
            },
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"name": 123}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_INPUT_SCHEMA"

    def test_start_run_sends_memory_config_to_engine(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Memory Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        MemoryConfiguration.objects.create(
            graph=graph,
            buffer_enabled=True,
            buffer_size=50,
            auto_prepend=False,
            redis_enabled=True,
            redis_summary_ttl=7200,
            redis_facts_ttl=172800,
            vector_enabled=True,
            vector_top_k=8,
            vector_threshold=0.85,
            vector_recency_weight=0.35,
            embedding_model="text-embedding-3-small",
            summarization_enabled=True,
            summarization_threshold=40,
            summarization_keep_recent=12,
            summarization_model="gpt-4",
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        call_payload = start_calls[0][1]
        assert call_payload["tenant_id"] == str(user.id)

        memory_config = json.loads(call_payload["memory_config_json"])
        assert memory_config["tier1"]["enabled"] is True
        assert memory_config["tier1"]["buffer_size"] == 50
        assert memory_config["tier1"]["auto_prepend"] is False
        assert memory_config["tier2"]["enabled"] is True
        assert memory_config["tier2"]["summary_ttl_seconds"] == 7200
        assert memory_config["tier2"]["facts_ttl_seconds"] == 172800
        assert memory_config["tier3"]["enabled"] is True
        assert memory_config["tier3"]["top_k"] == 8
        assert memory_config["tier3"]["threshold"] == 0.85
        assert memory_config["tier3"]["recency_weight"] == 0.35
        assert memory_config["tier3"]["embedding_model"] == "text-embedding-3-small"
        assert memory_config["summarization"]["enabled"] is True
        assert memory_config["summarization"]["trigger_threshold"] == 40
        assert memory_config["summarization"]["keep_recent_count"] == 12
        assert memory_config["summarization"]["model"] == "gpt-4"


class TestRunInvoke:
    """Tests for POST /api/runs/invoke"""

    def test_invoke_requires_authentication(self, api_client, user):
        response = api_client.post(
            "/api/runs/invoke",
            {"thread_id": str(uuid4()), "input_json": {}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invoke_creates_threaded_run(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        thread_id = uuid4()
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            thread_id=thread_id,
            started_at=timezone.now(),
            input_json={"initial": "state"},
        )
        RunCheckpoint.objects.create(
            run=run,
            node_id="seed",
            step_index=1,
            state_json={"input.initial": "state", "node.step.output": "done"},
            completed_nodes=["step"],
            skipped_nodes=[],
            graph_json=json.dumps(version.graph_json),
        )

        response = authenticated_client.post(
            "/api/runs/invoke",
            {"thread_id": str(thread_id), "input_json": {"query": "hi"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        run_data = response.data["data"]
        assert run_data["thread_id"] == str(thread_id)
        assert run_data["status"] == "running"

        new_run = Run.objects.get(id=run_data["id"])
        assert new_run.thread_id == thread_id
        assert new_run.input_json == {"query": "hi"}

        new_checkpoint = new_run.checkpoint
        assert new_checkpoint.state_json["input.query"] == "hi"

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        assert start_calls[0][1]["run_id"] == new_run.id


class TestRunCancel:
    """Tests for POST /api/runs/{run_id}/cancel"""

    def test_cancel_run_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = api_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cancel_run_updates_status(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == str(run.id)
        assert response.data["data"]["status"] == "canceled"
        assert response.data["data"]["ended_at"] is not None

        run.refresh_from_db()
        assert run.status == "canceled"
        assert run.ended_at is not None
        assert run.error_message

    def test_cancel_completed_run_returns_invalid_state(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_STATE"

    def test_cancel_run_for_other_user_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=other_user, graph_version=version, status="running")

        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"


class TestRunEvents:
    """Tests for POST /api/runs/{run_id}/events"""

    def test_run_events_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = api_client.post(
            f"/api/runs/{run.id}/events",
            {"event_type": "run.updated", "run": {"status": "canceled"}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_run_updated_event_persists(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = authenticated_client.post(
            f"/api/runs/{run.id}/events",
            {
                "event_type": "run.updated",
                "run": {"status": "canceled", "error_message": "Canceled by test"},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["type"] == "run.updated"

        run.refresh_from_db()
        assert run.status == "canceled"
        assert run.error_message == "Canceled by test"

    def test_node_run_updated_event_upserts(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        payload: dict[str, Any] = {
            "event_type": "node_run.updated",
            "node_run": {
                "node_id": "start",
                "node_type": "prompt",
                "status": "running",
                "attempt": 1,
                "input_json": {"hello": "world"},
            },
        }

        response = authenticated_client.post(f"/api/runs/{run.id}/events", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["type"] == "node_run.updated"

        node_run = NodeRun.objects.get(run=run, node_id="start", attempt=1)
        assert node_run.node_type == "prompt"
        assert node_run.status == "running"
        assert node_run.input_json == {"hello": "world"}

        payload["node_run"]["status"] = "succeeded"
        payload["node_run"]["output_json"] = {"ok": True}
        response = authenticated_client.post(f"/api/runs/{run.id}/events", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        node_run.refresh_from_db()
        assert node_run.status == "succeeded"
        assert node_run.output_json == {"ok": True}

    def test_run_events_for_other_user_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=other_user, graph_version=version, status="running")

        api_client.force_authenticate(user=user)
        response = api_client.post(
            f"/api/runs/{run.id}/events",
            {"event_type": "run.updated", "run": {"status": "failed"}},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_run_paused_event_creates_approval_task(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        payload = {
            "event_type": "run.updated",
            "run": {
                "status": "paused",
                "paused_node_id": "human_gate_1",
                "pause_state_json": {"state": "snapshot"},
                "pause_payload": {
                    "node_id": "human_gate_1",
                    "prompt_message": "Please approve",
                    "required_fields": ["ticket"],
                },
            },
        }

        response = authenticated_client.post(f"/api/runs/{run.id}/events", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "paused"
        assert run.paused_node_id == "human_gate_1"
        assert run.pause_state_json == {"state": "snapshot"}

        tasks = ApprovalTask.objects.filter(run=run, node_id="human_gate_1", status="pending")
        assert tasks.count() == 1
        task = tasks.first()
        assert task is not None
        assert task.assignee == user
        assert task.payload["prompt_message"] == "Please approve"
        assert task.payload["required_fields"] == ["ticket"]

        # Idempotent: second identical event should not create a duplicate task
        authenticated_client.post(f"/api/runs/{run.id}/events", payload, format="json")
        assert (
            ApprovalTask.objects.filter(run=run, node_id="human_gate_1", status="pending").count()
            == 1
        )

    def test_run_output_schema_strict_marks_failed(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Schema Graph")
        graph_json = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "schema_mode": "strict",
                "output_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        payload = {
            "event_type": "run.updated",
            "run": {"status": "succeeded", "output_json": {"value": "nope"}},
        }

        response = authenticated_client.post(f"/api/runs/{run.id}/events", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "failed"
        assert "Output schema validation failed" in run.error_message


class TestRunResume:
    """Tests for POST /api/runs/{run_id}/resume"""

    def test_resume_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )

        response = api_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_resume_rejects_non_paused_run(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", paused_node_id="gate"
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_STATE"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)

    def test_resume_rejects_node_mismatch(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "other_gate", "input_json": {"approved": True}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_NODE"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)

    def test_resume_calls_engine_and_marks_task_approved(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        task = ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve", "required_fields": ["ticket"]},
        )

        input_json = {"approved": True, "fields": {"ticket": "ABC-123"}, "feedback": "LGTM"}
        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["resumed"] is True

        # Engine called
        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1
        assert resume_calls[0][1]["run_id"] == run.id
        assert resume_calls[0][1]["node_id"] == "gate"
        assert resume_calls[0][1]["input_json"] == input_json

        # Task updated
        task.refresh_from_db()
        assert task.status == "approved"
        assert task.result == input_json
        assert task.resolved_at is not None

    def test_resume_calls_engine_and_marks_task_rejected(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        task = ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )

        input_json = {"approved": False, "feedback": "Needs changes"}
        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        task.refresh_from_db()
        assert task.status == "rejected"
        assert task.result == input_json
        assert task.resolved_at is not None


class TestRunListEdgeCases:
    """Edge case tests for GET /api/runs/"""

    def test_list_runs_with_pagination(self, authenticated_client, user):
        """Test that pagination parameters work correctly."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        # Create 15 runs
        now = timezone.now()
        for i in range(15):
            Run.objects.create(
                owner=user,
                graph_version=version,
                status="succeeded",
                started_at=now - timedelta(minutes=i),
            )

        response = authenticated_client.get("/api/runs/?limit=10")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "meta" in response.data
        assert len(response.data["data"]) == 10
        assert response.data["meta"]["total"] == 15

    def test_list_runs_returns_empty_for_new_user(self, authenticated_client, user):
        """Test that a new user sees an empty list."""
        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 0
        assert response.data["meta"]["total"] == 0

    def test_list_runs_filters_by_status(self, authenticated_client, user):
        """Test that runs can be filtered by status."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        Run.objects.create(owner=user, graph_version=version, status="succeeded")
        Run.objects.create(owner=user, graph_version=version, status="failed")
        Run.objects.create(owner=user, graph_version=version, status="running")

        response = authenticated_client.get("/api/runs/?status=succeeded")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["status"] == "succeeded"

    def test_list_runs_with_multiple_graphs(self, authenticated_client, user):
        """Test listing runs from multiple graphs."""
        graph1 = Graph.objects.create(owner=user, name="Graph 1")
        version1 = GraphVersion.objects.create(
            graph=graph1, version=1, graph_json={"nodes": [], "edges": []}
        )
        graph2 = Graph.objects.create(owner=user, name="Graph 2")
        version2 = GraphVersion.objects.create(
            graph=graph2, version=1, graph_json={"nodes": [], "edges": []}
        )

        Run.objects.create(owner=user, graph_version=version1, status="succeeded")
        Run.objects.create(owner=user, graph_version=version2, status="failed")

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2
        graph_names = [run["graph_name"] for run in response.data["data"]]
        assert "Graph 1" in graph_names
        assert "Graph 2" in graph_names

    def test_list_runs_with_complex_timestamps(self, authenticated_client, user):
        """Test runs with various timestamp combinations."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()

        # Completed run
        Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=now - timedelta(hours=2),
            ended_at=now - timedelta(hours=1),
        )

        # Running run
        Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            started_at=now - timedelta(minutes=30),
        )

        # Pending run (no timestamps)
        Run.objects.create(owner=user, graph_version=version, status="pending")

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 3

        # Verify duration_ms is present
        for run_data in response.data["data"]:
            if run_data["status"] == "succeeded":
                assert run_data["duration_ms"] is not None
            elif run_data["status"] == "running":
                assert run_data["duration_ms"] is None
            elif run_data["status"] == "pending":
                assert run_data["duration_ms"] is None


class TestRunDetailEdgeCases:
    """Edge case tests for GET /api/runs/{run_id}"""

    def test_get_run_with_large_node_runs_payload(self, authenticated_client, user):
        """Test retrieving a run with many node runs."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        # Create 100 node runs
        for i in range(100):
            NodeRun.objects.create(
                run=run,
                node_id=f"node_{i}",
                node_type="prompt",
                status="succeeded",
                started_at=now + timedelta(seconds=i),
                ended_at=now + timedelta(seconds=i + 1),
                input_json={"iteration": i},
                output_json={"result": f"output_{i}"},
            )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["node_runs"]) == 100
        # Verify ordering
        for i, node_run in enumerate(response.data["data"]["node_runs"]):
            assert node_run["node_id"] == f"node_{i}"

    def test_get_run_with_null_node_run_timestamps(self, authenticated_client, user):
        """Test retrieving a run with node runs that have null timestamps."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        # Node run without timestamps (pending)
        NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="pending",
            started_at=None,
            ended_at=None,
        )

        # Node run with started_at but no ended_at (running)
        NodeRun.objects.create(
            run=run,
            node_id="node_2",
            node_type="http",
            status="running",
            started_at=timezone.now(),
            ended_at=None,
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["node_runs"]) == 2

        # Verify duration_ms is None for both
        for node_run in response.data["data"]["node_runs"]:
            assert node_run["duration_ms"] is None

    def test_get_run_with_multiple_attempts_for_same_node(self, authenticated_client, user):
        """Test retrieving a run with retried nodes."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()

        # First attempt (failed)
        NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="http",
            status="failed",
            attempt=1,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
            error_json={"message": "Timeout"},
        )

        # Second attempt (succeeded)
        NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="http",
            status="succeeded",
            attempt=2,
            started_at=now + timedelta(seconds=2),
            ended_at=now + timedelta(seconds=3),
            output_json={"success": True},
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["node_runs"]) == 2

        # Verify ordering: attempt 1 then attempt 2
        assert response.data["data"]["node_runs"][0]["attempt"] == 1
        assert response.data["data"]["node_runs"][0]["status"] == "failed"
        assert response.data["data"]["node_runs"][1]["attempt"] == 2
        assert response.data["data"]["node_runs"][1]["status"] == "succeeded"

    def test_get_run_with_large_json_fields(self, authenticated_client, user):
        """Test retrieving a run with large JSON payloads."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        large_input = {"data": ["item" for _ in range(1000)]}
        large_output = {"results": [{"id": i, "value": f"result_{i}"} for i in range(500)]}

        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            input_json=large_input,
            output_json=large_output,
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["input_json"]["data"]) == 1000
        assert len(response.data["data"]["output_json"]["results"]) == 500

    def test_get_run_with_invalid_uuid(self, authenticated_client):
        """Test retrieving a run with an invalid UUID format."""
        response = authenticated_client.get("/api/runs/not-a-uuid")

        # Django will return 404 for invalid UUID format
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST]


class TestRunStartEdgeCases:
    """Edge case tests for POST /api/runs/start"""

    def test_start_run_with_empty_input_json(self, authenticated_client, user):
        """Test starting a run with empty input_json."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["input_json"] == {}

    def test_start_run_without_input_json(self, authenticated_client, user):
        """Test starting a run without providing input_json."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start", {"graph_version_id": str(version.id)}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["input_json"] == {}

    def test_start_run_with_complex_input_json(self, authenticated_client, user):
        """Test starting a run with complex nested input_json."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        complex_input = {
            "config": {"model": "gpt-4", "temperature": 0.7, "max_tokens": 1000},
            "prompts": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
            ],
            "metadata": {"user_id": "123", "timestamp": "2024-01-01T00:00:00Z"},
        }

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": complex_input},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["input_json"] == complex_input

    def test_start_run_with_nonexistent_graph_version(self, authenticated_client):
        """Test starting a run with a non-existent graph version ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = authenticated_client.post(
            "/api/runs/start", {"graph_version_id": fake_id, "input_json": {}}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_start_run_with_invalid_uuid(self, authenticated_client):
        """Test starting a run with an invalid UUID format."""
        response = authenticated_client.post(
            "/api/runs/start", {"graph_version_id": "not-a-uuid", "input_json": {}}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_start_run_missing_required_field(self, authenticated_client):
        """Test starting a run without the required graph_version_id."""
        response = authenticated_client.post("/api/runs/start", {"input_json": {}}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_start_multiple_runs_for_same_graph_version(self, authenticated_client, user):
        """Test that multiple runs can be started for the same graph version."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        run_ids = []
        for _ in range(3):
            response = authenticated_client.post(
                "/api/runs/start",
                {"graph_version_id": str(version.id), "input_json": {}},
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED
            run_ids.append(response.data["data"]["id"])

        # All run IDs should be unique
        assert len(set(run_ids)) == 3

        # Verify all runs exist in database
        assert Run.objects.filter(graph_version=version).count() == 3


class TestRunCancelEdgeCases:
    """Edge case tests for POST /api/runs/{run_id}/cancel"""

    def test_cancel_pending_run_with_no_started_at(self, authenticated_client, user):
        """Test canceling a pending run that has no started_at timestamp."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="pending", started_at=None
        )

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.status == "canceled"
        assert run.started_at is not None  # Should be set during cancel
        assert run.ended_at is not None

    def test_cancel_run_with_node_runs(self, authenticated_client, user):
        """Test canceling a run that has associated node runs."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", started_at=timezone.now()
        )

        # Create some node runs
        NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="succeeded",
            started_at=timezone.now(),
        )
        NodeRun.objects.create(
            run=run, node_id="node_2", node_type="http", status="running", started_at=timezone.now()
        )

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["node_runs"]) == 2

        run.refresh_from_db()
        assert run.status == "canceled"

    def test_cancel_paused_run(self, authenticated_client, user):
        """Test canceling a paused run."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", started_at=timezone.now()
        )

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.status == "canceled"

    def test_cancel_run_preserves_existing_error_message(self, authenticated_client, user):
        """Test that canceling preserves an existing error message."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        existing_error = "Partial failure detected"
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            started_at=timezone.now(),
            error_message=existing_error,
        )

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.status == "canceled"
        # Should keep the existing error message
        assert run.error_message == existing_error
