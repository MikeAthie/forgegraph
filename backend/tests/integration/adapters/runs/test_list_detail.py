"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


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
