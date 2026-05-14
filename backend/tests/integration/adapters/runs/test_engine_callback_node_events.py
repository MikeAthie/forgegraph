"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestEngineRunEvents:
    """Tests for POST /api/runs/engine-events (S2S)."""

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
