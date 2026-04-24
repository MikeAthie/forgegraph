"""
Integration tests for Run APIs.

Tests run history and run detail endpoints for Phase 4 observability MVP.
"""

import json
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status

from application.services.run_liveness import reconcile_stale_runs
from application.services.run_snapshots import RunSnapshot, get_snapshot, set_snapshot
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    Graph,
    GraphVersion,
    LLMBudget,
    LLMQuota,
    LLMUsage,
    MemoryConfiguration,
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    NodeRun,
    NodeRunEventProjection,
    PromptTemplate,
    Run,
    RunCheckpoint,
    RunEvent,
    RunEventProjection,
    RunQueueEntry,
    User,
)
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


def _create_openai_credential(user: User) -> APIKey:
    organization = user.default_organization
    assert organization is not None
    return APIKey.objects.create(
        organization=organization,
        user=user,
        provider="openai",
        name=f"OpenAI {uuid4()}",
        encrypted_key=b"test-key",
    )


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

    def test_list_runs_includes_trace_id(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Trace Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            trace_id="0123456789abcdef0123456789abcdef",
        )

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        run_data = next(item for item in response.data["data"] if item["id"] == str(run.id))
        assert run_data["trace_id"] == run.trace_id

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

    def test_list_runs_includes_curated_memory_summary(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Memory Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        NodeRun.objects.create(
            run=run,
            node_id="obs_save",
            node_type="observation_save",
            status="succeeded",
            output_json={
                "saved": True,
                "scope": "session",
                "observation": {
                    "id": "obs-1",
                    "title": "Customer preference",
                    "content": "Customer prefers SMS updates.",
                },
            },
        )
        NodeRun.objects.create(
            run=run,
            node_id="prompt_1",
            node_type="prompt",
            status="succeeded",
            output_json={
                "response": "Will use memory.",
                "memory_context": {
                    "curated_context_paths": ["node.obs_ctx.output"],
                    "curated_observation_count": 1,
                    "curated_degraded": False,
                    "curated_strategies": ["fts"],
                    "curated_observations": [
                        {
                            "id": "obs-1",
                            "title": "Customer preference",
                            "content": "Customer prefers SMS updates.",
                        }
                    ],
                },
            },
        )

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        run_data = next(item for item in response.data["data"] if item["id"] == str(run.id))
        assert run_data["memory_activity"]["has_activity"] is True
        assert run_data["memory_activity"]["save_node_count"] == 1
        assert run_data["memory_activity"]["saved_observation_count"] == 1
        assert run_data["memory_activity"]["influenced_node_count"] == 1
        assert run_data["memory_activity"]["influenced_observation_count"] == 1

    def test_list_runs_includes_wrapped_curated_memory_operations(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Wrapped Memory Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        NodeRun.objects.create(
            run=run,
            node_id="obs_ctx",
            node_type="observation_context",
            status="succeeded",
            output_json={
                "output": {
                    "query": "What should I remember about Jackie before answering?",
                    "count": 1,
                    "degraded": True,
                    "strategies": ["fts", "timeline"],
                    "observations": [
                        {
                            "id": "obs-ctx-1",
                            "title": "Jackie preference",
                            "content": "Jackie prefers concise planning updates.",
                            "scope": "graph",
                            "topic_key": "jackie-memory",
                        }
                    ],
                }
            },
        )
        NodeRun.objects.create(
            run=run,
            node_id="obs_save",
            node_type="observation_save",
            status="succeeded",
            output_json={
                "output": {
                    "saved": True,
                    "scope": "graph",
                    "observation": {
                        "id": "obs-save-1",
                        "title": "Jackie preference",
                        "content": "Jackie prefers concise planning updates.",
                        "scope": "graph",
                        "topic_key": "jackie-memory",
                    },
                }
            },
        )

        response = authenticated_client.get("/api/runs/")

        assert response.status_code == status.HTTP_200_OK
        run_data = next(item for item in response.data["data"] if item["id"] == str(run.id))
        assert run_data["memory_activity"]["has_activity"] is True
        assert run_data["memory_activity"]["save_node_count"] == 1
        assert run_data["memory_activity"]["saved_observation_count"] == 1
        assert run_data["memory_activity"]["retrieval_node_count"] == 1
        assert run_data["memory_activity"]["retrieved_observation_count"] == 1
        assert run_data["memory_activity"]["degraded"] is True


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

    def test_get_run_expands_dotted_node_input_payloads(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Replay Input Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        node_run = NodeRun.objects.create(
            run=run,
            node_id="strategy_agent",
            node_type="transform",
            status="running",
            input_json={
                "input.goal": "Launch a replayable AI digital marketing campaign for ForgeGraph.",
                "vars.execution_state": {
                    "goal": "Launch a replayable AI digital marketing campaign for ForgeGraph.",
                    "iteration": 0,
                    "strategy": None,
                    "content_assets": [],
                    "distribution_plan": None,
                    "analytics": None,
                },
            },
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        returned = next(
            item for item in response.data["data"]["node_runs"] if item["id"] == str(node_run.id)
        )
        assert returned["input_json"]["input"]["goal"] == (
            "Launch a replayable AI digital marketing campaign for ForgeGraph."
        )
        assert returned["input_json"]["vars"]["execution_state"]["goal"] == (
            "Launch a replayable AI digital marketing campaign for ForgeGraph."
        )
        assert returned["input_json"]["vars"]["execution_state"]["iteration"] == 0

    def test_get_run_includes_backend_attempt_and_status_history(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Replay Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [],
                "edges": [],
                "metadata": {"backend_attempt_id": "attempt-backend-1"},
            },
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            dispatch_graph_json={
                "nodes": [],
                "edges": [],
                "metadata": {"backend_attempt_id": "attempt-backend-1"},
            },
        )
        RunEvent.objects.create(run=run, event_type="run_started", payload={"status": "running"})
        RunEvent.objects.create(
            run=run,
            event_type="run_completed",
            payload={"status": "succeeded"},
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["backend_attempt_id"] == "attempt-backend-1"
        assert response.data["data"]["status_history"] == ["pending", "running", "succeeded"]

    def test_get_run_returns_traceable_timeline(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Timeline Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            trace_id="feedfacefeedfacefeedfacefeedface",
        )

        RunEvent.objects.create(
            run=run,
            event_type="run_started",
            payload={"status": "running"},
            trace_id=run.trace_id,
        )
        RunEvent.objects.create(
            run=run,
            event_type="node_failed",
            payload={
                "node_id": "draft_reply",
                "status": "failed",
                "error": "Provider timed out",
                "duration_ms": 2100,
            },
            trace_id=run.trace_id,
        )
        RunEvent.objects.create(
            run=run,
            event_type="node_stream.chunk",
            payload={"node_id": "draft_reply", "chunk": "partial"},
            trace_id=run.trace_id,
        )
        approval = ApprovalTask.objects.create(
            run=run,
            node_id="approval_1",
            assignee=user,
            status="approved",
            payload={"prompt_message": "Approve the draft."},
            result={"approved": True},
            resolved_at=timezone.now(),
        )
        usage = LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=run,
            node_id="draft_reply",
            provider="openai",
            model="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
            cost_usd=Decimal("1.250000"),
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["trace_id"] == run.trace_id

        timeline = data["timeline"]
        event_types = [entry["event_type"] for entry in timeline]
        assert "run_started" in event_types
        assert "node_failed" in event_types
        assert "decision_required" in event_types
        assert "decision_resolved" in event_types
        assert "cost_updated" in event_types
        assert "node_stream.chunk" not in event_types

        decision_required = next(
            entry for entry in timeline if entry["event_type"] == "decision_required"
        )
        assert decision_required["decision_id"] == str(approval.id)
        assert decision_required["trace_id"] == run.trace_id

        cost_update = next(entry for entry in timeline if entry["event_type"] == "cost_updated")
        assert cost_update["node_id"] == usage.node_id
        assert cost_update["cost_usd"] == float(usage.cost_usd)

    def test_get_run_returns_agent_trace_state(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Agent Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        node_run = NodeRun.objects.create(
            run=run,
            node_id="agent_1",
            node_type="agent",
            status="succeeded",
            attempt=1,
            started_at=timezone.now(),
            ended_at=timezone.now() + timedelta(milliseconds=200),
            output_json={
                "output": {
                    "final_output": "Customer is active.",
                    "stop_reason": "final_answer",
                    "step_count": 2,
                    "tool_call_count": 1,
                    "steps": [
                        {
                            "step_index": 1,
                            "action": "tool_call",
                            "tool": "crm_lookup",
                            "tool_output": {"status": "active"},
                        },
                        {
                            "step_index": 2,
                            "action": "final_answer",
                            "final_answer": "Customer is active.",
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 8,
                        "total_tokens": 28,
                    },
                }
            },
        )
        RunEvent.objects.create(
            run=run,
            event_type="agent.step.started",
            payload={
                "event": "agent.step.started",
                "node_id": "agent_1",
                "node_type": "agent",
                "attempt": 1,
                "step_index": 1,
                "chunk_index": 1,
            },
        )
        RunEvent.objects.create(
            run=run,
            event_type="agent.tool.completed",
            payload={
                "event": "agent.tool.completed",
                "node_id": "agent_1",
                "node_type": "agent",
                "attempt": 1,
                "step_index": 1,
                "tool": "crm_lookup",
                "status": "ok",
                "chunk_index": 3,
            },
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert len(data["agent_events"]) == 2
        returned_node_run = next(
            item for item in data["node_runs"] if item["id"] == str(node_run.id)
        )
        assert returned_node_run["agent_trace"]["stop_reason"] == "final_answer"
        assert returned_node_run["agent_trace"]["tool_call_count"] == 1
        assert len(returned_node_run["agent_trace"]["steps"]) == 2
        assert len(returned_node_run["agent_trace"]["events"]) == 2

    def test_get_run_returns_paused_agent_trace_from_pause_payload(
        self, authenticated_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Paused Agent Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            paused_node_id="agent_1",
        )

        node_run = NodeRun.objects.create(
            run=run,
            node_id="agent_1",
            node_type="agent",
            status="waiting",
            attempt=1,
            started_at=timezone.now(),
            output_json={
                "pause_payload": {
                    "prompt_message": "Approve agent tool call 'send_email'",
                    "tool": "send_email",
                    "agent_trace": {
                        "final_output": "",
                        "stop_reason": "approval_required",
                        "step_count": 1,
                        "tool_call_count": 0,
                        "approval_pending": True,
                        "steps": [
                            {
                                "step_index": 1,
                                "action": "tool_call",
                                "tool": "send_email",
                                "approval_required": True,
                            }
                        ],
                    },
                }
            },
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        returned_node_run = next(
            item for item in data["node_runs"] if item["id"] == str(node_run.id)
        )
        assert returned_node_run["agent_trace"]["stop_reason"] == "approval_required"
        assert returned_node_run["agent_trace"]["approval_pending"] is True
        assert returned_node_run["agent_trace"]["steps"][0]["tool"] == "send_email"

    def test_get_run_returns_curated_memory_activity_summary(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Curated Memory Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        NodeRun.objects.create(
            run=run,
            node_id="obs_save",
            node_type="observation_save",
            status="succeeded",
            attempt=1,
            output_json={
                "saved": True,
                "scope": "session",
                "observation": {
                    "id": "obs-1",
                    "type": "fact",
                    "title": "Snack preference",
                    "content": "Customer prefers sweet snacks during meetings.",
                    "scope": "session",
                    "topic_key": "snacks",
                },
            },
        )
        NodeRun.objects.create(
            run=run,
            node_id="obs_search",
            node_type="observation_search",
            status="succeeded",
            attempt=1,
            output_json={
                "query": "sweet snacks",
                "scope": "session",
                "count": 1,
                "observations": [
                    {
                        "id": "obs-1",
                        "title": "Snack preference",
                        "content": "Customer prefers sweet snacks during meetings.",
                    }
                ],
            },
        )
        NodeRun.objects.create(
            run=run,
            node_id="obs_context",
            node_type="observation_context",
            status="succeeded",
            attempt=1,
            output_json={
                "query": "meeting prep",
                "count": 1,
                "degraded": True,
                "strategies": ["fts"],
                "observations": [
                    {
                        "id": "obs-1",
                        "title": "Snack preference",
                        "content": "Customer prefers sweet snacks during meetings.",
                    }
                ],
            },
        )
        NodeRun.objects.create(
            run=run,
            node_id="prompt_1",
            node_type="prompt",
            status="succeeded",
            attempt=1,
            output_json={
                "response": "Bring sweet snacks.",
                "memory_context": {
                    "curated_context_paths": ["node.obs_context.output"],
                    "curated_observation_count": 1,
                    "curated_degraded": True,
                    "curated_strategies": ["fts"],
                    "curated_observations": [
                        {
                            "id": "obs-1",
                            "type": "fact",
                            "title": "Snack preference",
                            "content": "Customer prefers sweet snacks during meetings.",
                            "scope": "session",
                            "topic_key": "snacks",
                        }
                    ],
                },
            },
        )

        response = authenticated_client.get(f"/api/runs/{run.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["memory_activity"]["has_activity"] is True
        assert data["memory_activity"]["save_node_count"] == 1
        assert data["memory_activity"]["saved_observation_count"] == 1
        assert data["memory_activity"]["retrieval_node_count"] == 2
        assert data["memory_activity"]["retrieved_observation_count"] == 2
        assert data["memory_activity"]["influenced_node_count"] == 1
        assert data["memory_activity"]["influenced_observation_count"] == 1
        assert data["memory_activity"]["degraded"] is True
        assert len(data["memory_activity"]["operations"]) == 4

        save_node = next(item for item in data["node_runs"] if item["node_id"] == "obs_save")
        assert save_node["memory_activity"]["category"] == "save"
        assert save_node["memory_activity"]["observation"]["title"] == "Snack preference"

        context_node = next(item for item in data["node_runs"] if item["node_id"] == "obs_context")
        assert context_node["memory_activity"]["operation"] == "context"
        assert context_node["memory_activity"]["degraded"] is True

        prompt_node = next(item for item in data["node_runs"] if item["node_id"] == "prompt_1")
        assert prompt_node["memory_activity"]["category"] == "influence"
        assert prompt_node["memory_activity"]["observation_count"] == 1

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
        assert call_payload["tenant_id"] == str(user.default_organization_id)

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

    def test_start_run_resolves_prompt_id_to_template(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Support Prompt",
            category="other",
            content="You are a helpful support agent.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Prompt Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {
                            "prompt_id": str(prompt.id),
                            "credential_id": str(credential.id),
                        },
                    },
                    {"id": "out", "type": "output", "name": "Output", "config": {}},
                ],
                "edges": [{"id": "e1", "from": "prompt1", "to": "out"}],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"q": "hi"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        sent_graph = start_calls[0][1]["graph_json"]
        prompt_node = next(node for node in sent_graph["nodes"] if node["id"] == "prompt1")
        assert prompt_node["config"]["prompt_template"] == "You are a helpful support agent."

    def test_start_run_rejects_inaccessible_prompt_id(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Private Prompt",
            category="other",
            content="Restricted prompt.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Prompt Access Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {
                            "prompt_id": str(prompt.id),
                            "credential_id": str(credential.id),
                        },
                    }
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert "not accessible" in response.data["error"]["message"]
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_rejects_prompt_without_template_or_prompt_id(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        graph = Graph.objects.create(owner=user, name="Prompt Validation Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {"credential_id": str(credential.id)},
                    }
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert "prompt_template" in response.data["error"]["message"]
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_blocked_when_quota_exceeded(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Quota Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        usage_run = Run.objects.create(owner=user, graph_version=version, status="succeeded")
        LLMQuota.objects.create(tenant_id=user.default_organization_id, monthly_token_limit=100)
        LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=usage_run,
            node_id="prompt-1",
            provider="openai",
            model="gpt-4",
            prompt_tokens=50,
            completion_tokens=50,
            total_tokens=100,
            cost_usd=Decimal("0.50"),
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "QUOTA_EXCEEDED"
        assert response.data["error"]["details"][0]["reason"] == "quota"
        assert response.data["error"]["details"][0]["scope"] == "tenant_monthly_tokens"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_blocked_when_budget_exceeded(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Budget Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        usage_run = Run.objects.create(owner=user, graph_version=version, status="succeeded")
        LLMBudget.objects.create(
            tenant_id=user.default_organization_id,
            monthly_limit_usd=Decimal("1.00"),
            warning_threshold_pct=Decimal("0.80"),
        )
        LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=usage_run,
            node_id="prompt-1",
            provider="openai",
            model="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
            cost_usd=Decimal("1.00"),
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "budget"}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "BUDGET_EXCEEDED"
        assert response.data["error"]["details"][0]["reason"] == "budget"
        assert response.data["error"]["details"][0]["scope"] == "tenant_monthly_spend"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    @override_settings(
        RUN_START_RATE_LIMIT_PER_MIN=1,
        RUN_RATE_LIMIT_WINDOW_SECONDS=60,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rate-limit-start",
            }
        },
    )
    def test_start_run_rate_limited(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Rate Limit Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        first = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )
        assert first.status_code == status.HTTP_201_CREATED

        second = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )
        assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert second.data["error"]["code"] == "RATE_LIMITED"
        assert second.data["error"]["details"][0]["limit"] == 1

    @override_settings(RUN_QUEUE_ENABLED=True)
    def test_start_run_queues_when_enabled(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="Queued Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "queue"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["meta"]["queued"] is True
        run_data = response.data["data"]
        assert run_data["status"] == "pending"
        assert run_data["queue_status"] == "pending"
        assert run_data["queue_attempts"] == 0
        assert run_data["queue_available_at"] is not None

        run = Run.objects.get(id=run_data["id"])
        assert isinstance(run.dispatch_graph_json, dict)
        assert run.dispatch_graph_json["nodes"] == []
        assert "tool_resolution" in run.dispatch_graph_json["metadata"]
        entry = RunQueueEntry.objects.get(run=run)
        assert entry.status == "pending"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_persists_backend_selected_tool_snapshot(
        self, authenticated_client, mock_engine_client, user
    ):
        package = NodeRegistryPackage.objects.create(
            slug="crm-lookup",
            name="CRM Lookup",
            summary="Lookup CRM records",
            category="crm",
        )
        release = NodeRegistryRelease.objects.create(
            package=package,
            version="1.2.0",
            status="approved",
            package_kind="runtime_tool",
            execution_node_type="tool",
            manifest_version=2,
            config_defaults={"tool": "crm_lookup"},
            runtime_manifest={
                "name": "crm_lookup",
                "version": "1.2.0",
                "category": "crm",
                "visibility": "public",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/crm", "method": "POST"},
                },
                "side_effects": {"type": "read", "idempotent": True},
            },
        )
        NodePackageInstallation.objects.create(
            organization=user.default_organization,
            package=package,
            release=release,
            install_metadata={},
        )

        internal_package = NodeRegistryPackage.objects.create(
            slug="crm-internal",
            name="CRM Internal",
            summary="Internal CRM helper",
            category="crm",
        )
        internal_release = NodeRegistryRelease.objects.create(
            package=internal_package,
            version="1.0.0",
            status="approved",
            package_kind="runtime_tool",
            execution_node_type="tool",
            manifest_version=2,
            config_defaults={"tool": "crm_internal"},
            runtime_manifest={
                "name": "crm_internal",
                "version": "1.0.0",
                "category": "crm",
                "visibility": "internal",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/internal", "method": "POST"},
                },
                "side_effects": {"type": "read", "idempotent": True},
            },
        )
        NodePackageInstallation.objects.create(
            organization=user.default_organization,
            package=internal_package,
            release=internal_release,
            install_metadata={},
        )

        graph = Graph.objects.create(owner=user, name="Backend Selected Tool Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "agent_1",
                        "type": "agent",
                        "name": "Agent",
                        "config": {
                            "tool_selection": {"categories": ["crm"], "max_tools": 5},
                            "approval_required_tools": ["crm_lookup"],
                        },
                    },
                    {
                        "id": "tool_1",
                        "type": "tool",
                        "name": "Lookup",
                        "config": {"tool": "crm_lookup"},
                    },
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"customer_id": "cust_123"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        run = Run.objects.get(id=response.data["data"]["id"])
        assert isinstance(run.dispatch_graph_json, dict)

        agent_node = next(
            node for node in run.dispatch_graph_json["nodes"] if node["id"] == "agent_1"
        )
        tool_node = next(
            node for node in run.dispatch_graph_json["nodes"] if node["id"] == "tool_1"
        )
        tool_resolution = run.dispatch_graph_json["metadata"]["tool_resolution"]

        assert agent_node["config"]["tools"] == ["crm_lookup"]
        assert agent_node["config"]["tool_versions"] == {"crm_lookup": "1.2.0"}
        assert tool_node["config"]["version"] == "1.2.0"
        assert [tool["name"] for tool in tool_resolution["pinned_tools"]] == ["crm_lookup"]
        assert tool_resolution["agent_nodes"]["agent_1"]["tools"] == ["crm_lookup"]
        assert tool_resolution["manifest_version"] == 2
        assert "backend_attempt_id" not in run.dispatch_graph_json["metadata"]
        assert "tool_execution_id" not in tool_node["config"]

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        payload_graph = start_calls[0][1]["graph_json"]
        payload_tool_node = next(node for node in payload_graph["nodes"] if node["id"] == "tool_1")
        assert payload_graph["metadata"]["tool_resolution"] == tool_resolution
        assert "backend_attempt_id" in payload_graph["metadata"]
        assert payload_tool_node["config"]["tool_execution_id"]
        assert payload_tool_node["config"]["idempotency_key"]


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
        assert isinstance(new_run.dispatch_graph_json, dict)

        new_checkpoint = new_run.checkpoint
        assert new_checkpoint.state_json["input.query"] == "hi"

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        assert "backend_attempt_id" not in (new_run.dispatch_graph_json.get("metadata") or {})
        assert "backend_attempt_id" in start_calls[0][1]["graph_json"]["metadata"]
        assert start_calls[0][1]["run_id"] == new_run.id

    def test_invoke_resolves_prompt_id_into_checkpoint_and_engine_payload(
        self, authenticated_client, mock_engine_client, user
    ):
        credential = _create_openai_credential(user)
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Thread Prompt",
            category="other",
            content="Threaded prompt template.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Invoke Prompt Graph")
        graph_json = {
            "nodes": [
                {
                    "id": "prompt1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {
                        "prompt_id": str(prompt.id),
                        "credential_id": str(credential.id),
                    },
                },
                {"id": "out", "type": "output", "name": "Output", "config": {}},
            ],
            "edges": [{"id": "e1", "from": "prompt1", "to": "out"}],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        thread_id = uuid4()
        previous_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            thread_id=thread_id,
            started_at=timezone.now(),
            input_json={"initial": "state"},
        )
        RunCheckpoint.objects.create(
            run=previous_run,
            node_id="out",
            step_index=2,
            state_json={"input.initial": "state"},
            completed_nodes=["prompt1", "out"],
            skipped_nodes=[],
            graph_json=json.dumps(graph_json),
        )

        response = authenticated_client.post(
            "/api/runs/invoke",
            {"thread_id": str(thread_id), "input_json": {"query": "hello"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        invoked_run = Run.objects.get(id=response.data["data"]["id"])
        checkpoint_graph_json = invoked_run.checkpoint.graph_json
        checkpoint_graph = (
            json.loads(checkpoint_graph_json)
            if isinstance(checkpoint_graph_json, str)
            else checkpoint_graph_json
        )
        prompt_node = next(node for node in checkpoint_graph["nodes"] if node["id"] == "prompt1")
        assert prompt_node["config"]["prompt_template"] == "Threaded prompt template."

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        payload_graph = start_calls[0][1]["graph_json"]
        payload_prompt = next(node for node in payload_graph["nodes"] if node["id"] == "prompt1")
        assert payload_prompt["config"]["prompt_template"] == "Threaded prompt template."

    def test_invoke_rejects_invalid_prompt_template_reference(
        self, authenticated_client, mock_engine_client, user
    ):
        credential = _create_openai_credential(user)
        other_user = User.objects.create_user(
            email="other-invoke@example.com", password="password123"
        )
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Hidden Prompt",
            category="other",
            content="Do not access",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Invoke Invalid Prompt Graph")
        graph_json = {
            "nodes": [
                {
                    "id": "prompt1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {
                        "prompt_id": str(prompt.id),
                        "credential_id": str(credential.id),
                    },
                }
            ],
            "edges": [],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        thread_id = uuid4()
        previous_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            thread_id=thread_id,
            started_at=timezone.now(),
            input_json={"initial": "state"},
        )
        RunCheckpoint.objects.create(
            run=previous_run,
            node_id="seed",
            step_index=1,
            state_json={"input.initial": "state"},
            completed_nodes=[],
            skipped_nodes=[],
            graph_json=json.dumps(graph_json),
        )

        response = authenticated_client.post(
            "/api/runs/invoke",
            {"thread_id": str(thread_id), "input_json": {"query": "hello"}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    @override_settings(
        RUN_INVOKE_RATE_LIMIT_PER_MIN=1,
        RUN_RATE_LIMIT_WINDOW_SECONDS=60,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rate-limit-invoke",
            }
        },
    )
    def test_invoke_rate_limited(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="Invoke Graph")
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
            state_json={"input.initial": "state"},
            completed_nodes=["step"],
            skipped_nodes=[],
            graph_json=json.dumps(version.graph_json),
        )

        first = authenticated_client.post(
            "/api/runs/invoke",
            {"thread_id": str(thread_id), "input_json": {"query": "hi"}},
            format="json",
        )
        assert first.status_code == status.HTTP_201_CREATED

        second = authenticated_client.post(
            "/api/runs/invoke",
            {"thread_id": str(thread_id), "input_json": {"query": "again"}},
            format="json",
        )
        assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert second.data["error"]["code"] == "RATE_LIMITED"


class TestRunReplay:
    """Tests for POST /api/runs/{run_id}/replay."""

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_replay_from_node_prunes_checkpoint_scope(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Replay Graph")
        graph_json = {
            "nodes": [
                {"id": "start", "type": "transform", "name": "Start"},
                {"id": "branch", "type": "transform", "name": "Branch"},
                {"id": "left", "type": "transform", "name": "Left"},
                {"id": "right", "type": "transform", "name": "Right"},
                {"id": "output", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "e1", "from": "start", "to": "branch"},
                {"id": "e2", "from": "branch", "to": "left"},
                {"id": "e3", "from": "branch", "to": "right"},
                {"id": "e4", "from": "left", "to": "output"},
                {"id": "e5", "from": "right", "to": "output"},
            ],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        source_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=timezone.now() - timedelta(minutes=2),
            ended_at=timezone.now() - timedelta(minutes=1),
            input_json={"query": "hello"},
            output_json={"result": "from-source"},
        )
        RunCheckpoint.objects.create(
            run=source_run,
            node_id="output",
            step_index=8,
            state_json={
                "input.query": "hello",
                "vars.shared": "keep",
                "node.start.output": {"ok": True},
                "node.branch.output": {"route": "left"},
                "node.left.output": {"value": "left"},
                "node.right.output": {"value": "right"},
                "node.output.output": {"result": "from-source"},
            },
            completed_nodes=["start", "branch", "left", "right", "output"],
            skipped_nodes=["right"],
            graph_json=graph_json,
        )

        response = authenticated_client.post(
            f"/api/runs/{source_run.id}/replay",
            {"node_id": "branch"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        replay_run = Run.objects.get(id=response.data["data"]["id"])
        replay_checkpoint = replay_run.checkpoint

        assert replay_run.status == "running"
        assert replay_run.input_json == source_run.input_json

        # Downstream replay from "branch" should remove node.* state for branch descendants.
        assert replay_checkpoint.state_json["input.query"] == "hello"
        assert replay_checkpoint.state_json["vars.shared"] == "keep"
        assert replay_checkpoint.state_json["node.start.output"] == {"ok": True}
        assert "node.branch.output" not in replay_checkpoint.state_json
        assert "node.left.output" not in replay_checkpoint.state_json
        assert "node.right.output" not in replay_checkpoint.state_json
        assert "node.output.output" not in replay_checkpoint.state_json

        # Completed/skipped should exclude the replay scope.
        assert replay_checkpoint.completed_nodes == ["start"]
        assert replay_checkpoint.skipped_nodes == []

        replay_event = RunEvent.objects.get(run=replay_run, event_type="run.replay")
        assert replay_event.payload["source_run_id"] == str(source_run.id)
        assert replay_event.payload["from_node_id"] == "branch"
        assert replay_event.payload["checkpoint_step"] == 8

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        assert start_calls[0][1]["run_id"] == replay_run.id
        assert start_calls[0][1]["input_json"] == {"query": "hello"}
        assert isinstance(replay_run.dispatch_graph_json, dict)
        replay_metadata = replay_run.dispatch_graph_json.get("metadata")
        assert isinstance(replay_metadata, dict)
        assert "backend_attempt_id" not in replay_metadata
        assert "backend_attempt_id" in start_calls[0][1]["graph_json"]["metadata"]

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_replay_resolves_prompt_id_into_checkpoint_and_engine_payload(
        self, authenticated_client, mock_engine_client, user
    ):
        credential = _create_openai_credential(user)
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Replay Prompt",
            category="other",
            content="Replay prompt template.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Replay Prompt Graph")
        graph_json = {
            "nodes": [
                {
                    "id": "prompt1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {
                        "prompt_id": str(prompt.id),
                        "credential_id": str(credential.id),
                    },
                },
                {"id": "out", "type": "output", "name": "Output", "config": {}},
            ],
            "edges": [{"id": "e1", "from": "prompt1", "to": "out"}],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        source_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=timezone.now() - timedelta(minutes=2),
            ended_at=timezone.now() - timedelta(minutes=1),
            input_json={"query": "resume"},
            output_json={"result": "ok"},
        )
        RunCheckpoint.objects.create(
            run=source_run,
            node_id="out",
            step_index=3,
            state_json={"input.query": "resume", "node.out.output": {"result": "ok"}},
            completed_nodes=["prompt1", "out"],
            skipped_nodes=[],
            graph_json=json.dumps(graph_json),
        )

        response = authenticated_client.post(
            f"/api/runs/{source_run.id}/replay",
            {},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        replay_run = Run.objects.get(id=response.data["data"]["id"])
        replay_checkpoint_graph_json = replay_run.checkpoint.graph_json
        replay_checkpoint_graph = (
            json.loads(replay_checkpoint_graph_json)
            if isinstance(replay_checkpoint_graph_json, str)
            else replay_checkpoint_graph_json
        )
        checkpoint_prompt = next(
            node for node in replay_checkpoint_graph["nodes"] if node["id"] == "prompt1"
        )
        assert checkpoint_prompt["config"]["prompt_template"] == "Replay prompt template."

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        payload_prompt = next(
            node for node in start_calls[0][1]["graph_json"]["nodes"] if node["id"] == "prompt1"
        )
        assert payload_prompt["config"]["prompt_template"] == "Replay prompt template."

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_replay_rejects_invalid_prompt_template_reference(
        self, authenticated_client, mock_engine_client, user
    ):
        credential = _create_openai_credential(user)
        other_user = User.objects.create_user(
            email="other-replay@example.com", password="password123"
        )
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Replay Hidden Prompt",
            category="other",
            content="No access",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Replay Invalid Prompt Graph")
        graph_json = {
            "nodes": [
                {
                    "id": "prompt1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {
                        "prompt_id": str(prompt.id),
                        "credential_id": str(credential.id),
                    },
                },
                {"id": "out", "type": "output", "name": "Output", "config": {}},
            ],
            "edges": [{"id": "e1", "from": "prompt1", "to": "out"}],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        source_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=timezone.now() - timedelta(minutes=2),
            ended_at=timezone.now() - timedelta(minutes=1),
            input_json={"query": "resume"},
            output_json={"result": "ok"},
        )
        RunCheckpoint.objects.create(
            run=source_run,
            node_id="out",
            step_index=3,
            state_json={"input.query": "resume", "node.out.output": {"result": "ok"}},
            completed_nodes=["prompt1", "out"],
            skipped_nodes=[],
            graph_json=json.dumps(graph_json),
        )

        response = authenticated_client.post(
            f"/api/runs/{source_run.id}/replay",
            {},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_replay_engine_events_materialize_expected_state_and_output_equivalence(
        self, authenticated_client, signed_engine_event_post, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Replay Graph Events")
        graph_json = {
            "nodes": [
                {"id": "start", "type": "transform", "name": "Start"},
                {"id": "output", "type": "output", "name": "Output"},
            ],
            "edges": [
                {"id": "e1", "from": "start", "to": "output"},
            ],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        source_output = {"answer": 42, "meta": {"model": "mock"}}
        source_run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=timezone.now() - timedelta(minutes=3),
            ended_at=timezone.now() - timedelta(minutes=2),
            input_json={"query": "life"},
            output_json=source_output,
        )
        RunCheckpoint.objects.create(
            run=source_run,
            node_id="output",
            step_index=3,
            state_json={"input.query": "life", "node.start.output": {"progress": "done"}},
            completed_nodes=["start", "output"],
            skipped_nodes=[],
            graph_json=graph_json,
        )

        replay_response = authenticated_client.post(
            f"/api/runs/{source_run.id}/replay",
            {},
            format="json",
        )
        assert replay_response.status_code == status.HTTP_201_CREATED
        replay_run = Run.objects.get(id=replay_response.data["data"]["id"])

        tenant_id = str(user.default_organization_id)
        response = signed_engine_event_post(
            {
                "event_id": f"evt-replay-{replay_run.id}-run-started",
                "type": "run_started",
                "run_id": str(replay_run.id),
                "tenant_id": tenant_id,
            }
        )
        assert response.status_code == status.HTTP_200_OK

        response = signed_engine_event_post(
            {
                "event_id": f"evt-replay-{replay_run.id}-node-started",
                "type": "node_started",
                "run_id": str(replay_run.id),
                "tenant_id": tenant_id,
                "node_id": "output",
                "node_type": "output",
                "attempt": 1,
            }
        )
        assert response.status_code == status.HTTP_200_OK

        response = signed_engine_event_post(
            {
                "event_id": f"evt-replay-{replay_run.id}-node-completed",
                "type": "node_completed",
                "run_id": str(replay_run.id),
                "tenant_id": tenant_id,
                "node_id": "output",
                "node_type": "output",
                "attempt": 1,
                "output": {"output": source_output},
            }
        )
        assert response.status_code == status.HTTP_200_OK

        response = signed_engine_event_post(
            {
                "event_id": f"evt-replay-{replay_run.id}-run-completed",
                "type": "run_completed",
                "run_id": str(replay_run.id),
                "tenant_id": tenant_id,
                "output": source_output,
            }
        )
        assert response.status_code == status.HTTP_200_OK

        replay_run.refresh_from_db()
        assert replay_run.status == "succeeded"
        assert replay_run.output_json == source_output

        # Replay output should be equivalent to source output under same completion payload.
        source_run.refresh_from_db()
        assert replay_run.output_json == source_run.output_json

        event_types = list(
            RunEvent.objects.filter(run=replay_run).values_list("event_type", flat=True)
        )
        assert event_types.count("run.replay") == 1
        assert event_types.count("run.updated") >= 2
        assert event_types.count("node_run.updated") == 2

        node_statuses = set(
            RunEvent.objects.filter(run=replay_run, event_type="node_run.updated").values_list(
                "payload__status", flat=True
            )
        )
        assert node_statuses == {"running", "succeeded"}

        run_statuses = set(
            RunEvent.objects.filter(run=replay_run, event_type="run.updated").values_list(
                "payload__status", flat=True
            )
        )
        assert run_statuses == {"running", "succeeded"}

        node_run = NodeRun.objects.get(run=replay_run, node_id="output", attempt=1)
        assert node_run.status == "succeeded"
        assert node_run.output_json == {"output": source_output}


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


class TestEngineRunEvents:
    """Tests for POST /api/runs/engine-events (S2S)."""

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_paused_event_projects_waiting_state_and_approval_task(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Approval Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        payload = {
            "event_id": "evt-pause-1",
            "type": "run_paused",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "human_gate_1",
            "node_type": "human_gate",
            "attempt": 1,
            "timestamp": int(time.time() * 1000),
            "output": {
                "prompt_message": "Approve customer email draft",
                "required_fields": ["ticket", "reason"],
            },
        }

        response = signed_engine_event_post(payload)

        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "paused"
        assert run.paused_node_id == "human_gate_1"
        assert run.pause_state_json is None

        waiting_node = NodeRun.objects.get(run=run, node_id="human_gate_1", attempt=1)
        assert waiting_node.status == "waiting"
        assert waiting_node.output_json == {"pause_payload": payload["output"]}

        run_projection = RunEventProjection.objects.get(run=run)
        assert run_projection.status == "paused"
        assert run_projection.paused_node_id == "human_gate_1"
        assert run_projection.pause_state_json is None
        assert run_projection.last_event_id == "evt-pause-1"
        assert run_projection.last_event_type == "run_paused"

        node_projection = NodeRunEventProjection.objects.get(
            run=run, node_id="human_gate_1", attempt=1
        )
        assert node_projection.status == "waiting"
        assert node_projection.node_type == "human_gate"
        assert node_projection.output_json == {"pause_payload": payload["output"]}
        assert node_projection.last_event_type == "run_paused"

        approval_task = ApprovalTask.objects.get(run=run, node_id="human_gate_1", status="pending")
        assert approval_task.assignee == user
        assert approval_task.payload == {
            "prompt_message": "Approve customer email draft",
            "required_fields": ["ticket", "reason"],
        }

        duplicate_response = signed_engine_event_post(payload)
        assert duplicate_response.status_code == status.HTTP_200_OK
        assert duplicate_response.data["data"]["duplicate"] is True
        assert (
            ApprovalTask.objects.filter(run=run, node_id="human_gate_1", status="pending").count()
            == 1
        )
        assert NodeRun.objects.filter(run=run, node_id="human_gate_1", attempt=1).count() == 1
        assert RunEventProjection.objects.filter(run=run).count() == 1
        assert (
            NodeRunEventProjection.objects.filter(
                run=run, node_id="human_gate_1", attempt=1
            ).count()
            == 1
        )

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_paused_event_preserves_durable_pause_state(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Approval Graph Durable State")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "human_gate_1", "type": "human_gate"}], "edges": []},
        )
        durable_pause_state = {
            "state_snapshot": {"input.ticket": "FG-123"},
            "completed_nodes": [],
            "skipped_nodes": [],
            "graph_json": json.dumps(version.graph_json),
            "tenant_id": str(user.default_organization_id),
        }
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            pause_state_json=durable_pause_state,
        )

        payload = {
            "event_id": "evt-pause-2",
            "type": "run_paused",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "human_gate_1",
            "node_type": "human_gate",
            "attempt": 1,
            "timestamp": int(time.time() * 1000),
            "output": {
                "prompt_message": "Approve customer email draft",
                "required_fields": ["ticket", "reason"],
            },
        }

        response = signed_engine_event_post(payload)

        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "paused"
        assert run.paused_node_id == "human_gate_1"
        assert run.pause_state_json == durable_pause_state

        run_projection = RunEventProjection.objects.get(run=run)
        assert run_projection.status == "paused"
        assert run_projection.paused_node_id == "human_gate_1"
        assert run_projection.pause_state_json == durable_pause_state

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_resumed_event_clears_resume_requested_tracking(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Resume Requested Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "human_gate_1", "type": "human_gate"}], "edges": []},
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="resume_requested",
            paused_node_id="human_gate_1",
            pause_state_json={"prompt_message": "Approve draft"},
            resume_requested_at=timezone.now() - timedelta(minutes=2),
            resume_attempt_id=uuid4(),
        )

        payload = {
            "event_id": "evt-resume-1",
            "type": "run_resumed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "timestamp": int(time.time() * 1000),
            "output": {
                "approved": True,
                "resume_attempt_id": str(run.resume_attempt_id),
            },
        }

        response = signed_engine_event_post(payload)

        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "running"
        assert run.paused_node_id is None
        assert run.pause_state_json is None
        assert run.resume_requested_at is None
        assert run.resume_attempt_id is None
        assert run.recovery_state == "active"

        run_projection = RunEventProjection.objects.get(run=run)
        assert run_projection.status == "running"
        assert run_projection.paused_node_id is None
        assert run_projection.pause_state_json is None

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_resumed_rejects_invalid_transition_from_paused(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Invalid Resume Transition Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "human_gate_1", "type": "human_gate"}], "edges": []},
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            paused_node_id="human_gate_1",
        )

        response = signed_engine_event_post(
            {
                "event_id": "evt-resume-invalid-transition",
                "type": "run_resumed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
                "output": {"resume_attempt_id": str(uuid4())},
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "invalid run event transition" in response.data["detail"].lower()
        run.refresh_from_db()
        assert run.status == "paused"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_resumed_rejects_stale_resume_attempt(self, signed_engine_event_post, user):
        graph = Graph.objects.create(owner=user, name="Stale Resume Ack Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "human_gate_1", "type": "human_gate"}], "edges": []},
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="resume_requested",
            paused_node_id="human_gate_1",
            pause_state_json={"prompt_message": "Approve draft"},
            resume_requested_at=timezone.now() - timedelta(minutes=2),
            resume_attempt_id=uuid4(),
        )

        response = signed_engine_event_post(
            {
                "event_id": "evt-resume-stale-attempt",
                "type": "run_resumed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
                "output": {"resume_attempt_id": str(uuid4())},
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "resume_attempt_id" in response.data["detail"]
        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.resume_attempt_id is not None

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_build_shadow_state_for_run_and_node_lifecycle(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Lifecycle Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        base_timestamp = int(time.time() * 1000)
        events = [
            {
                "event_id": "evt-shadow-run-start",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": base_timestamp,
            },
            {
                "event_id": "evt-shadow-node-start",
                "type": "node_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "node_id": "prompt_1",
                "node_type": "prompt",
                "attempt": 1,
                "timestamp": base_timestamp + 10,
            },
            {
                "event_id": "evt-shadow-node-complete",
                "type": "node_completed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "node_id": "prompt_1",
                "node_type": "prompt",
                "attempt": 1,
                "timestamp": base_timestamp + 20,
                "output": {"text": "done"},
            },
            {
                "event_id": "evt-shadow-run-complete",
                "type": "run_completed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": base_timestamp + 30,
                "output": {"result": "ok"},
            },
        ]

        for payload in events:
            response = signed_engine_event_post(payload)
            assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "succeeded"
        assert run.output_json == {"result": "ok"}

        run_projection = RunEventProjection.objects.get(run=run)
        assert run_projection.status == "succeeded"
        assert run_projection.output_json == {"result": "ok"}
        assert run_projection.started_at is not None
        assert run_projection.ended_at is not None
        assert run_projection.last_event_id == "evt-shadow-run-complete"
        assert run_projection.last_event_type == "run_completed"

        node_run = NodeRun.objects.get(run=run, node_id="prompt_1", attempt=1)
        assert node_run.status == "succeeded"
        assert node_run.output_json == {"text": "done"}

        node_projection = NodeRunEventProjection.objects.get(run=run, node_id="prompt_1", attempt=1)
        assert node_projection.status == "succeeded"
        assert node_projection.node_type == "prompt"
        assert node_projection.output_json == {"text": "done"}
        assert node_projection.started_at is not None
        assert node_projection.ended_at is not None
        assert node_projection.last_event_id == "evt-shadow-node-complete"
        assert node_projection.last_event_type == "node_completed"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_node_started_persists_input_payload(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Node Input Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        base_timestamp = int(time.time() * 1000)
        run_started = signed_engine_event_post(
            {
                "event_id": "evt-input-run-start",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": base_timestamp,
            }
        )
        assert run_started.status_code == status.HTTP_200_OK

        node_started = signed_engine_event_post(
            {
                "event_id": "evt-input-node-start",
                "type": "node_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "node_id": "strategy_agent",
                "node_type": "transform",
                "attempt": 1,
                "timestamp": base_timestamp + 10,
                "input": {
                    "goal": "Launch a replayable marketing loop.",
                    "vars": {"execution_state": {"iteration": 0}},
                },
            }
        )
        assert node_started.status_code == status.HTTP_200_OK

        node_run = NodeRun.objects.get(run=run, node_id="strategy_agent", attempt=1)
        assert node_run.input_json == {
            "goal": "Launch a replayable marketing loop.",
            "vars": {"execution_state": {"iteration": 0}},
        }

    @override_settings(
        ENGINE_CALLBACK_SECRET="test-secret",
        ENGINE_EVENT_STATE_MUTATION_ENABLED=False,
    )
    def test_engine_events_only_update_shadow_state_when_authoritative_mutation_disabled(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Intent Owned Lifecycle Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        run_started = signed_engine_event_post(
            {
                "event_id": "evt-intent-owned-run-start",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
            }
        )
        assert run_started.status_code == status.HTTP_200_OK
        assert run_started.data["data"]["authoritative_state_updated"] is False

        node_started = signed_engine_event_post(
            {
                "event_id": "evt-intent-owned-node-start",
                "type": "node_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "node_id": "prompt_1",
                "node_type": "prompt",
                "attempt": 1,
                "timestamp": int(time.time() * 1000) + 10,
            }
        )
        assert node_started.status_code == status.HTTP_200_OK
        assert node_started.data["data"]["authoritative_state_updated"] is False

        run.refresh_from_db()
        assert run.status == "pending"
        assert NodeRun.objects.filter(run=run, node_id="prompt_1", attempt=1).count() == 0

        run_projection = RunEventProjection.objects.get(run=run)
        assert run_projection.status == "running"
        assert run_projection.last_event_type == "run_started"

        node_projection = NodeRunEventProjection.objects.get(
            run=run,
            node_id="prompt_1",
            attempt=1,
        )
        assert node_projection.status == "running"
        assert node_projection.last_event_type == "node_started"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_idempotent_by_event_id(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        timestamp_ms = int(time.time() * 1000)
        event_id = "evt-123"
        payload = {
            "event_id": event_id,
            "type": "run_started",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "timestamp": timestamp_ms,
        }
        body = json.dumps(payload)
        signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))
        headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
        }

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert RunEvent.objects.filter(run=run, external_id=event_id).count() == 1

        run.refresh_from_db()
        started_at = run.started_at
        assert run.status == "running"

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["duplicate"] is True
        assert RunEvent.objects.filter(run=run, external_id=event_id).count() == 1

        run.refresh_from_db()
        assert run.status == "running"
        assert run.started_at == started_at

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_first_callback_assigns_engine_and_normalizes_category(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Assignment Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        response = signed_engine_event_post(
            {
                "event_id": "evt-engine-assignment-1",
                "type": "run_started",
                "category": "observability",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "engine_instance_id": "engine-a",
                "timestamp": int(time.time() * 1000),
            }
        )

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.engine_instance_id == "engine-a"
        assert run.last_progress_at is not None
        event = RunEvent.objects.get(run=run, external_id="evt-engine-assignment-1")
        assert event.payload["category"] == "state"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_reject_engine_instance_mismatch(self, signed_engine_event_post, user):
        graph = Graph.objects.create(owner=user, name="Assignment Guard Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="pending",
            engine_instance_id="engine-a",
        )

        response = signed_engine_event_post(
            {
                "event_id": "evt-engine-assignment-2",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "engine_instance_id": "engine-b",
                "timestamp": int(time.time() * 1000),
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "engine instance" in response.data["detail"].lower()
        assert RunEvent.objects.filter(run=run, external_id="evt-engine-assignment-2").count() == 0

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_observability_event_cannot_establish_engine_assignment(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Observability Assignment Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = signed_engine_event_post(
            {
                "event_id": "evt-observability-assignment-1",
                "type": "node_stream_chunk",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "engine_instance_id": "engine-a",
                "node_id": "prompt_1",
                "node_type": "prompt",
                "attempt": 1,
                "timestamp": int(time.time() * 1000),
                "output": {
                    "chunk": "hello",
                    "chunk_index": 1,
                },
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "must not mutate runtime state" in response.data["detail"].lower()
        run.refresh_from_db()
        assert run.engine_instance_id == ""
        assert run.last_progress_at is None
        assert (
            RunEvent.objects.filter(run=run, external_id="evt-observability-assignment-1").count()
            == 0
        )

    def test_reconcile_stale_runs_persists_checkpoint_diagnostics(self, user):
        graph = Graph.objects.create(owner=user, name="Stale Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            last_progress_at=timezone.now() - timedelta(minutes=10),
        )
        snapshot = RunSnapshot(
            run_id=run.id,
            last_completed_node="human_gate_1",
            next_node="resume_after_gate",
            attempt_id="attempt-7",
            updated_at=timezone.now(),
        )
        set_snapshot(snapshot)

        result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

        assert result.reconciled == 1
        run.refresh_from_db()
        assert run.status == "failed"

        event = RunEvent.objects.get(run=run, event_type="run.updated")
        assert event.payload["checkpoint_available"] is True
        assert event.payload["checkpoint_node_id"] == "human_gate_1"
        assert event.payload["checkpoint_next_node"] == "resume_after_gate"
        assert event.payload["checkpoint_attempt_id"] == "attempt-7"
        assert event.payload["checkpoint_updated_at"] == snapshot.updated_at.isoformat()

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_reject_tenant_mismatch(self, signed_engine_event_post, user):
        graph = Graph.objects.create(owner=user, name="Tenant Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        response = signed_engine_event_post(
            {
                "event_id": "evt-tenant-mismatch",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": str(uuid4()),
                "timestamp": int(time.time() * 1000),
            }
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert RunEvent.objects.filter(run=run).count() == 0

        run.refresh_from_db()
        assert run.status == "pending"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_node_stream_chunk_broadcasts(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        timestamp_ms = int(time.time() * 1000)
        payload = {
            "event_id": "evt-stream-1",
            "type": "node_stream_chunk",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "prompt_1",
            "node_type": "prompt",
            "attempt": 1,
            "timestamp": timestamp_ms,
            "output": {
                "chunk": "Hello",
                "chunk_index": 1,
            },
        }
        body = json.dumps(payload)
        signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))
        headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
        }

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["type"] == "node_stream.chunk"
        assert response.data["data"]["node_stream"]["chunk"] == "Hello"
        run.refresh_from_db()
        assert run.last_progress_at is None
        assert run.engine_instance_id == ""
        assert RunEvent.objects.filter(
            run=run, event_type="node_stream.chunk", payload__chunk="Hello"
        ).exists()

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_schema_validation_is_observability_only(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Schema Observability Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = signed_engine_event_post(
            {
                "event_id": "evt-schema-observability-1",
                "type": "run.schema_validation",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
                "output": {
                    "errors": [{"message": "value must be a number"}],
                    "mode": "strict",
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.status == "running"
        assert run.last_progress_at is None
        event = RunEvent.objects.get(run=run, external_id="evt-schema-observability-1")
        assert event.payload["category"] == "observability"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_agent_stream_chunk_persists_structured_agent_event(
        self, api_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Agent Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        timestamp_ms = int(time.time() * 1000)
        payload = {
            "event_id": "evt-agent-stream-1",
            "type": "node_stream_chunk",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "agent_1",
            "node_type": "agent",
            "attempt": 1,
            "timestamp": timestamp_ms,
            "output": {
                "chunk": json.dumps(
                    {
                        "event": "agent.step.started",
                        "step_index": 1,
                    }
                ),
                "chunk_index": 1,
            },
        }
        body = json.dumps(payload)
        signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))
        headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
        }

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["node_stream"]["agent_event"]["event"] == "agent.step.started"
        assert RunEvent.objects.filter(
            run=run,
            event_type="agent.step.started",
            payload__node_id="agent_1",
            payload__step_index=1,
        ).exists()

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_node_failed_persists_structured_error_payload(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        timestamp_ms = int(time.time() * 1000)
        payload = {
            "event_id": "evt-node-failed-structured",
            "type": "node_failed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "http_1",
            "node_type": "http",
            "attempt": 2,
            "error": "max retries exceeded: transient upstream failure",
            "timestamp": timestamp_ms,
            "output": {
                "error": {
                    "message": "transient upstream failure",
                    "type": "retryable_error",
                    "attempt": 2,
                    "max_attempts": 2,
                    "retryable": True,
                    "on_error_action": "skip",
                }
            },
        }
        body = json.dumps(payload)
        signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))
        headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
        }

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == status.HTTP_200_OK

        node_run = NodeRun.objects.get(run=run, node_id="http_1", attempt=2)
        assert node_run.status == "failed"
        assert node_run.error_json is not None
        assert node_run.error_json["type"] == "retryable_error"
        assert node_run.error_json["on_error_action"] == "skip"
        assert node_run.error_json["attempt"] == 2
        assert node_run.error_json["error"] == payload["error"]

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_node_failed_does_not_advance_snapshot(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Failure Snapshot Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        snapshot_updated_at = timezone.now()
        set_snapshot(
            RunSnapshot(
                run_id=run.id,
                last_completed_node="node_1",
                next_node="node_2",
                attempt_id="attempt-1",
                updated_at=snapshot_updated_at,
            )
        )

        response = signed_engine_event_post(
            {
                "event_id": "evt-node-failed-does-not-advance-snapshot",
                "type": "node_failed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "node_id": "node_2",
                "node_type": "http",
                "attempt": 1,
                "timestamp": int(time.time() * 1000),
                "error": "downstream failure",
                "output": {
                    "error": {
                        "message": "downstream failure",
                        "type": "retryable_error",
                        "attempt": 1,
                        "retryable": True,
                    }
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK

        snapshot = get_snapshot(run.id)
        assert snapshot is not None
        assert snapshot.last_completed_node == "node_1"
        assert snapshot.next_node == "node_2"
        assert snapshot.attempt_id == "attempt-1"
        assert snapshot.updated_at == snapshot_updated_at

        node_run = NodeRun.objects.get(run=run, node_id="node_2", attempt=1)
        assert node_run.status == "failed"

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_agent_completed_records_llm_usage(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="Agent Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        timestamp_ms = int(time.time() * 1000)
        payload = {
            "event_id": "evt-agent-complete-1",
            "type": "node_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "agent_1",
            "node_type": "agent",
            "attempt": 1,
            "timestamp": timestamp_ms,
            "output": {
                "output": {
                    "final_output": "done",
                    "stop_reason": "final_answer",
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "usage": {
                        "prompt_tokens": 42,
                        "completion_tokens": 18,
                        "total_tokens": 60,
                    },
                }
            },
        }
        body = json.dumps(payload)
        signature = s2s.build_signature("test-secret", str(timestamp_ms), body.encode("utf-8"))
        headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
        }

        response = api_client.post(
            "/api/runs/engine-events",
            data=body,
            content_type="application/json",
            **headers,
        )

        assert response.status_code == status.HTTP_200_OK
        usage = LLMUsage.objects.get(run=run, node_id="agent_1")
        assert usage.provider == "openai"
        assert usage.model == "gpt-4.1-mini"
        assert usage.prompt_tokens == 42
        assert usage.completion_tokens == 18
        assert usage.total_tokens == 60

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_events_node_completed_is_idempotent_for_llm_usage(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Cost Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        payload = {
            "event_id": "evt-node-complete-idempotent",
            "type": "node_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "prompt_1",
            "node_type": "prompt",
            "attempt": 1,
            "timestamp": int(time.time() * 1000),
            "output": {
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 25,
                    "total_tokens": 75,
                },
                "answer": "hello",
            },
        }

        first = signed_engine_event_post(payload)
        second = signed_engine_event_post(payload)

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["duplicate"] is True
        assert LLMUsage.objects.filter(run=run, node_id="prompt_1").count() == 1

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

        with TestCase.captureOnCommitCallbacks(execute=True):
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
        assert isinstance(resume_calls[0][1]["resume_attempt_id"], str)

        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.recovery_state == "resume_requested"
        assert run.resume_requested_at is not None
        assert run.resume_attempt_id is not None
        assert resume_calls[0][1]["resume_attempt_id"] == str(run.resume_attempt_id)

        # Task updated
        task.refresh_from_db()
        assert task.status == "approved"
        assert task.result == input_json
        assert task.resolved_at is not None

    def test_resume_updates_snapshot_attempt_before_dispatch(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Resume Snapshot Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            paused_node_id="gate",
        )
        previous_snapshot = RunSnapshot(
            run_id=run.id,
            last_completed_node="node_1",
            next_node="gate",
            attempt_id="attempt-a",
            updated_at=timezone.now() - timedelta(minutes=1),
        )
        set_snapshot(previous_snapshot)

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1

        run.refresh_from_db()
        snapshot = get_snapshot(run.id)
        assert snapshot is not None
        assert snapshot.last_completed_node == "node_1"
        assert snapshot.next_node == "gate"
        assert snapshot.attempt_id == str(run.resume_attempt_id)
        assert snapshot.attempt_id != previous_snapshot.attempt_id
        assert resume_calls[0][1]["resume_attempt_id"] == snapshot.attempt_id

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

        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.resume_requested_at is not None
        assert run.resume_attempt_id is not None

        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1
        assert resume_calls[0][1]["resume_attempt_id"] == str(run.resume_attempt_id)

        task.refresh_from_db()
        assert task.status == "rejected"
        assert task.result == input_json
        assert task.resolved_at is not None

    def test_resume_is_idempotent_for_duplicate_decision_payload(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )

        input_json = {"approved": True, "feedback": "Ship it"}
        first = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )
        second = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["duplicate"] is True

        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1

    def test_resume_rejects_when_budget_exceeded(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Budget Resume Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )
        usage_run = Run.objects.create(owner=user, graph_version=version, status="succeeded")
        LLMBudget.objects.create(
            tenant_id=user.default_organization_id,
            monthly_limit_usd=Decimal("1.00"),
            warning_threshold_pct=Decimal("0.80"),
        )
        LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=usage_run,
            node_id="prompt-1",
            provider="openai",
            model="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
            cost_usd=Decimal("1.00"),
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "BUDGET_EXCEEDED"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)


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
