"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


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
