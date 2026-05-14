"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestEngineRunEvents:
    """Tests for POST /api/runs/engine-events (S2S)."""

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_callback_invalid_schema_returns_reject_invalid_decision(
        self, signed_engine_event_post, user
    ):
        response = signed_engine_event_post(
            {
                "event_id": "evt-invalid-schema",
                "type": "run_started",
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["decision"] == "reject_invalid"
        assert response.data["safe_to_discard"] is True

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_callback_missing_run_requires_retry(self, signed_engine_event_post, user):
        missing_run_id = uuid4()

        response = signed_engine_event_post(
            {
                "event_id": "evt-missing-run",
                "type": "run_started",
                "run_id": str(missing_run_id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
            }
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["decision"] == "retry_required"
        assert response.data["safe_to_discard"] is False
        assert response.data["conflict_code"] == "404_UNKNOWN_ENTITY"

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
        assert duplicate_response.data["data"]["decision"] == "duplicate"
        assert duplicate_response.data["data"]["safe_to_discard"] is True
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
    def test_engine_run_resumed_event_is_idempotent_after_resume_ack_intent(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Acked Resume Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={"nodes": [{"id": "human_gate_1", "type": "human_gate"}], "edges": []},
        )
        resume_attempt_id = uuid4()
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            paused_node_id=None,
            pause_state_json=None,
            resume_requested_at=None,
            resume_attempt_id=None,
        )
        set_snapshot(
            RunSnapshot(
                run_id=run.id,
                last_completed_node="human_gate_1",
                next_node="final_output",
                attempt_id=str(resume_attempt_id),
                updated_at=timezone.now(),
            )
        )

        response = signed_engine_event_post(
            {
                "event_id": "evt-resume-acked-idempotent",
                "type": "run_resumed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
                "attempt_id": str(resume_attempt_id),
                "output": {
                    "approved": True,
                    "resume_attempt_id": str(resume_attempt_id),
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.status == "running"
        assert run.paused_node_id is None
        assert run.pause_state_json is None
        assert run.resume_attempt_id is None
        assert RunEvent.objects.filter(run=run, event_type="run_resumed").exists()

    @override_settings(ENGINE_CALLBACK_SECRET="test-secret")
    def test_engine_run_resumed_rejects_missing_resume_attempt(
        self, signed_engine_event_post, user
    ):
        graph = Graph.objects.create(owner=user, name="Missing Resume Attempt Graph")
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
                "event_id": "evt-resume-missing-attempt",
                "type": "run_resumed",
                "run_id": str(run.id),
                "tenant_id": str(user.default_organization_id),
                "timestamp": int(time.time() * 1000),
                "output": {"approved": True},
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "resume_attempt_id" in response.data["detail"]
        assert response.data["decision"] == "stale_superseded"
        assert response.data["safe_to_discard"] is True
        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.resume_attempt_id is not None

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
        assert response.data["decision"] == "retry_required"
        assert response.data["safe_to_discard"] is False
        assert response.data["conflict_code"] == "409_ORDERING_CONFLICT"
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
