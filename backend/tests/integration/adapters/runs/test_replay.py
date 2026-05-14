"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


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
        source_context_pack = ContextPack.objects.create(
            organization=graph.organization,
            company=graph,
            operation=source_run,
            scope_json={"source": "historical"},
            asset_refs_json=[{"asset_id": "historical-source-context"}],
            created_for="operation_planning",
        )
        source_run.dispatch_graph_json = {
            **graph_json,
            "metadata": {
                "context_pack_id": str(source_context_pack.id),
                "context_pack_mode": "fresh_at_dispatch",
            },
        }
        source_run.save(update_fields=["dispatch_graph_json"])

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
        assert replay_event.payload["context_pack_mode"] == "fresh_at_replay"
        assert replay_event.payload["context_pack_id"] != str(source_context_pack.id)

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        assert start_calls[0][1]["run_id"] == replay_run.id
        assert start_calls[0][1]["input_json"] == {"query": "hello"}
        assert isinstance(replay_run.dispatch_graph_json, dict)
        replay_metadata = replay_run.dispatch_graph_json.get("metadata")
        assert isinstance(replay_metadata, dict)
        assert "backend_attempt_id" not in replay_metadata
        assert replay_metadata["context_pack_mode"] == "fresh_at_replay"
        assert replay_metadata["context_pack_id"] != str(source_context_pack.id)
        assert "backend_attempt_id" in start_calls[0][1]["graph_json"]["metadata"]
        assert start_calls[0][1]["graph_json"]["metadata"]["context_pack_mode"] == "fresh_at_replay"

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
