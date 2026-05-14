"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


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
