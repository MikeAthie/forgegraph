"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


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
