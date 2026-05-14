"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestEngineRunEvents:
    """Tests for POST /api/runs/engine-events (S2S)."""

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

        second_timestamp_ms = timestamp_ms + 1
        payload["timestamp"] = second_timestamp_ms
        second_body = json.dumps(payload)
        second_signature = s2s.build_signature(
            "test-secret", str(second_timestamp_ms), second_body.encode("utf-8")
        )
        second_headers = {
            "HTTP_X_FORGEGRAPH_TIMESTAMP": str(second_timestamp_ms),
            "HTTP_X_FORGEGRAPH_SIGNATURE": second_signature,
        }
        response = api_client.post(
            "/api/runs/engine-events",
            data=second_body,
            content_type="application/json",
            **second_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["duplicate"] is True
        assert RunEvent.objects.filter(run=run, external_id=event_id).count() == 1

        run.refresh_from_db()
        assert run.status == "running"
        assert run.started_at == started_at

    @override_settings(
        ENGINE_CALLBACK_SECRET="test-secret",
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "adapters.api.authentication.RevocableJWTAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.IsAuthenticated",
            ],
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.AnonRateThrottle",
            ],
            "DEFAULT_THROTTLE_RATES": {"anon": "1/min"},
        },
    )
    def test_engine_events_endpoint_is_not_throttled_for_signed_s2s_callbacks(
        self,
        signed_engine_event_post,
        user,
    ):
        graph = Graph.objects.create(owner=user, name="Callback Throttle Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")
        tenant_id = str(user.default_organization_id)
        timestamp_ms = int(time.time() * 1000)

        payloads = [
            {
                "event_id": "evt-throttle-run-started",
                "type": "run_started",
                "run_id": str(run.id),
                "tenant_id": tenant_id,
                "timestamp": timestamp_ms,
            },
            {
                "event_id": "evt-throttle-node-started",
                "type": "node_started",
                "run_id": str(run.id),
                "tenant_id": tenant_id,
                "node_id": "agent-1",
                "node_type": "agent",
                "timestamp": timestamp_ms + 1,
            },
            {
                "event_id": "evt-throttle-node-stream",
                "type": "node_stream_chunk",
                "run_id": str(run.id),
                "tenant_id": tenant_id,
                "node_id": "agent-1",
                "node_type": "agent",
                "output": {"chunk": "partial"},
                "timestamp": timestamp_ms + 2,
            },
        ]

        for payload in payloads:
            response = signed_engine_event_post(payload)
            assert response.status_code == status.HTTP_200_OK

        assert RunEvent.objects.filter(
            run=run,
            external_id__in=[str(payload["event_id"]) for payload in payloads],
        ).count() == len(payloads)

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
        assert response.data["decision"] == "retry_required"
        assert response.data["safe_to_discard"] is False
        assert response.data["conflict_code"] == "409_ORDERING_CONFLICT"
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
        assert response.data["decision"] == "reject_invalid"
        assert response.data["safe_to_discard"] is False
        assert RunEvent.objects.filter(run=run).count() == 0

        run.refresh_from_db()
        assert run.status == "pending"
