from __future__ import annotations

import copy
import json
import time
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status

from application.services.run_queue import RunQueueSettings, enqueue_run
from application.services.run_snapshots import RunSnapshot, get_snapshot, set_snapshot
from application.services.runtime_write_intents import process_runtime_intent_message
from infrastructure.orm.management.commands import process_run_queue
from infrastructure.orm.management.commands.process_run_queue import (
    Command as ProcessRunQueueCommand,
)
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    NodeRun,
    NodeRunEventProjection,
    ProcessedRuntimeIntent,
    Run,
    RunCheckpoint,
    RunEvent,
    RunEventProjection,
    User,
)
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


class _RecordingEngineClient:
    def __init__(self) -> None:
        self.start_calls: list[dict[str, object]] = []

    def __enter__(self) -> _RecordingEngineClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def start_run(self, **kwargs):
        self.start_calls.append(kwargs)


def _make_run(
    user: User,
    *,
    status: str = "running",
    graph_json: dict[str, object] | None = None,
    **run_fields: object,
) -> Run:
    graph = Graph.objects.create(owner=user, name=f"Runtime Invariant Graph {uuid4().hex[:8]}")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json=graph_json or {"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status=status,
        **run_fields,
    )


def _activate_attempt(
    run: Run,
    attempt_id: str,
    *,
    last_completed_node: str = "node_prev",
    next_node: str = "node_next",
) -> None:
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node=last_completed_node,
            next_node=next_node,
            attempt_id=attempt_id,
            updated_at=timezone.now(),
        )
    )


def _runtime_intent_fields(
    *,
    run: Run,
    intent_type: str,
    payload: dict[str, object],
    attempt_id: str,
    trace_id: str = "trace-runtime-intent",
    intent_id: UUID | None = None,
) -> tuple[UUID, dict[str, str]]:
    resolved_intent_id = intent_id or uuid4()
    return resolved_intent_id, {
        "intent": json.dumps(
            {
                "intent_id": str(resolved_intent_id),
                "intent_type": intent_type,
                "run_id": str(run.id),
                "attempt_id": attempt_id,
                "trace_id": trace_id,
                "timestamp": timezone.now().isoformat(),
                "payload": payload,
            }
        )
    }


def _signed_json_request(secret: str, payload: dict[str, object]) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    timestamp_ms = str(int(time.time() * 1000))
    signature = s2s.build_signature(secret, timestamp_ms, body.encode("utf-8"))
    return body, {
        "HTTP_X_FORGEGRAPH_TIMESTAMP": timestamp_ms,
        "HTTP_X_FORGEGRAPH_SIGNATURE": signature,
    }


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_stale_attempt_cannot_complete_run_via_engine_event(signed_engine_event_post, user):
    run = _make_run(user, status="running")
    _activate_attempt(run, "attempt-b")

    signed_engine_event_post(
        {
            "event_id": "evt-stale-run-completed",
            "type": "run_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "attempt_id": "attempt-a",
            "timestamp": int(time.time() * 1000),
            "output": {"result": "stale-finish"},
        }
    )

    run.refresh_from_db()
    snapshot = get_snapshot(run.id)

    assert run.status == "running"
    assert run.ended_at is None
    assert run.output_json is None
    assert snapshot is not None
    assert snapshot.attempt_id == "attempt-b"
    assert not RunEvent.objects.filter(run=run, external_id="evt-stale-run-completed").exists()
    assert not RunEvent.objects.filter(run=run, event_type="run.updated").exists()
    assert not RunEventProjection.objects.filter(run=run).exists()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_stale_attempt_cannot_fail_run_via_engine_event(signed_engine_event_post, user):
    run = _make_run(user, status="running")
    _activate_attempt(run, "attempt-b")

    signed_engine_event_post(
        {
            "event_id": "evt-stale-run-failed",
            "type": "run_failed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "attempt_id": "attempt-a",
            "timestamp": int(time.time() * 1000),
            "error": "stale failure",
        }
    )

    run.refresh_from_db()
    snapshot = get_snapshot(run.id)

    assert run.status == "running"
    assert run.ended_at is None
    assert run.error_message == ""
    assert snapshot is not None
    assert snapshot.attempt_id == "attempt-b"
    assert not RunEvent.objects.filter(run=run, external_id="evt-stale-run-failed").exists()
    assert not RunEvent.objects.filter(run=run, event_type="run.updated").exists()
    assert not RunEventProjection.objects.filter(run=run).exists()


def test_stale_attempt_cannot_store_checkpoint_via_runtime_intent(user):
    run = _make_run(user, status="running")
    _activate_attempt(run, "attempt-b")
    intent_id, fields = _runtime_intent_fields(
        run=run,
        intent_type="store_checkpoint",
        attempt_id="attempt-a",
        payload={
            "node_id": "node_stale",
            "step_index": 9,
            "state_snapshot": {"checkpoint_version": 2, "state": {"stale": True}},
            "completed_nodes": ["node_prev"],
            "skipped_nodes": [],
            "graph_json": {"nodes": [{"id": "node_stale"}], "edges": []},
        },
    )

    result = process_runtime_intent_message(
        stream_message_id="1700000000000-stale-checkpoint",
        fields=fields,
    )

    run.refresh_from_db()
    snapshot = get_snapshot(run.id)

    assert result == "ignored"
    assert snapshot is not None
    assert snapshot.attempt_id == "attempt-b"
    assert not RunCheckpoint.objects.filter(run=run).exists()
    assert not ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).exists()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_stale_attempt_cannot_update_node_state_via_engine_event(signed_engine_event_post, user):
    run = _make_run(user, status="running")
    _activate_attempt(run, "attempt-b")
    node_run = NodeRun.objects.create(
        run=run,
        node_id="node_1",
        node_type="prompt",
        status="running",
        attempt=1,
        started_at=timezone.now(),
    )

    signed_engine_event_post(
        {
            "event_id": "evt-stale-node-completed",
            "type": "node_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "node_1",
            "node_type": "prompt",
            "attempt": 1,
            "attempt_id": "attempt-a",
            "timestamp": int(time.time() * 1000),
            "output": {"answer": "stale"},
        }
    )

    node_run.refresh_from_db()
    run.refresh_from_db()

    assert run.status == "running"
    assert node_run.status == "running"
    assert node_run.ended_at is None
    assert node_run.output_json is None
    assert not RunEvent.objects.filter(run=run, external_id="evt-stale-node-completed").exists()
    assert not RunEvent.objects.filter(run=run, event_type="node_run.updated").exists()
    assert not NodeRunEventProjection.objects.filter(run=run, node_id="node_1", attempt=1).exists()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_active_attempt_can_update_node_state_via_engine_event(signed_engine_event_post, user):
    run = _make_run(user, status="running")
    _activate_attempt(run, "attempt-b")
    node_run = NodeRun.objects.create(
        run=run,
        node_id="node_1",
        node_type="prompt",
        status="running",
        attempt=1,
        started_at=timezone.now(),
    )

    response = signed_engine_event_post(
        {
            "event_id": "evt-active-node-completed",
            "type": "node_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "node_id": "node_1",
            "node_type": "prompt",
            "attempt": 1,
            "attempt_id": "attempt-b",
            "timestamp": int(time.time() * 1000),
            "output": {"answer": "fresh"},
        }
    )

    node_run.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert node_run.status == "succeeded"
    assert node_run.output_json == {"answer": "fresh"}
    assert (
        NodeRunEventProjection.objects.get(
            run=run,
            node_id="node_1",
            attempt=1,
        ).status
        == "succeeded"
    )
    assert RunEvent.objects.filter(run=run, external_id="evt-active-node-completed").exists()


def test_runtime_intent_snapshot_write_redis_failure_fails_closed(monkeypatch, user):
    run = _make_run(user, status="running")
    NodeRun.objects.create(
        run=run,
        node_id="node_redis",
        node_type="transform",
        status="succeeded",
        attempt=1,
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={"ok": True},
    )
    intent_id = uuid4()
    intent_id, fields = _runtime_intent_fields(
        run=run,
        intent_type="node_completed",
        attempt_id="attempt-1",
        intent_id=intent_id,
        payload={
            "node_id": "node_redis",
            "attempt": 1,
            "next_node": "node_after_redis",
        },
    )

    monkeypatch.setattr(
        "application.services.runtime_write_intents.set_snapshot",
        lambda snapshot: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
    )

    with pytest.raises(RuntimeError, match="redis unavailable"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            process_runtime_intent_message(
                stream_message_id="1700000000000-redis-failure",
                fields=fields,
            )

    run.refresh_from_db()

    assert run.last_progress_at is None
    assert get_snapshot(run.id) is None
    assert not ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).exists()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_duplicate_engine_event_id_is_idempotent_for_terminal_transition(
    signed_engine_event_post, user
):
    run = _make_run(user, status="running")
    payload = {
        "event_id": "evt-terminal-duplicate",
        "type": "run_completed",
        "run_id": str(run.id),
        "tenant_id": str(user.default_organization_id),
        "timestamp": int(time.time() * 1000),
        "output": {"result": "done"},
    }

    first = signed_engine_event_post(payload)
    second = signed_engine_event_post(payload)

    run.refresh_from_db()

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert run.status == "succeeded"
    assert RunEvent.objects.filter(run=run, external_id="evt-terminal-duplicate").count() == 1


def test_duplicate_runtime_intent_id_is_idempotent_for_checkpoint_write(user):
    run = _make_run(user, status="running")
    intent_id, fields = _runtime_intent_fields(
        run=run,
        intent_type="store_checkpoint",
        attempt_id="attempt-1",
        payload={
            "node_id": "node_checkpoint",
            "step_index": 4,
            "state_snapshot": {"checkpoint_version": 2, "state": {"x": 1}},
            "completed_nodes": ["seed"],
            "skipped_nodes": [],
            "graph_json": {"nodes": [{"id": "node_checkpoint"}], "edges": []},
        },
    )

    first = process_runtime_intent_message(
        stream_message_id="1700000000000-dup-1",
        fields=fields,
    )
    second = process_runtime_intent_message(
        stream_message_id="1700000000000-dup-2",
        fields=fields,
    )

    checkpoint = RunCheckpoint.objects.get(run=run)

    assert first == "processed"
    assert second == "duplicate"
    assert checkpoint.node_id == "node_checkpoint"
    assert checkpoint.step_index == 4
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).count() == 1


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_malformed_engine_event_is_rejected_without_state_mutation(signed_engine_event_post, user):
    run = _make_run(user, status="running")

    response = signed_engine_event_post(
        {
            "event_id": "evt-malformed-node-completed",
            "type": "node_completed",
            "run_id": str(run.id),
            "tenant_id": str(user.default_organization_id),
            "timestamp": int(time.time() * 1000),
            "output": {"answer": "bad"},
        }
    )

    run.refresh_from_db()

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert run.status == "running"
    assert not NodeRun.objects.filter(run=run).exists()
    assert not RunEvent.objects.filter(run=run).exists()


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_direct_run_patch_cannot_mutate_authoritative_state(api_client, user):
    run = _make_run(user, status="pending")
    body, headers = _signed_json_request(
        "test-secret",
        {
            "status": "running",
            "trace_id": "trace-direct-engine-write",
            "output_json": {"direct": True},
        },
    )

    response = api_client.generic(
        "PATCH",
        f"/api/engine/runs/{run.id}",
        body,
        content_type="application/json",
        **headers,
    )

    run.refresh_from_db()

    assert response.status_code >= 400
    assert run.status == "pending"
    assert run.trace_id == ""
    assert run.output_json is None


def test_process_run_queue_enriches_persisted_dispatch_graph_without_mutating_source_object(
    monkeypatch, user
):
    graph = Graph.objects.create(owner=user, name="Queued Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "source", "type": "transform", "name": "Source"}],
            "edges": [],
        },
    )
    persisted_graph = {
        "nodes": [{"id": "agent_1", "type": "agent", "name": "Agent"}],
        "edges": [],
        "metadata": {
            "tool_resolution": {
                "manifest_version": 2,
                "manifest_checksum": "pinned-checksum",
            }
        },
    }
    original_persisted_graph = copy.deepcopy(persisted_graph)
    run = Run.objects.create(
        owner=user,
        graph_version=version,
        status="pending",
        input_json={"hello": "queue"},
        dispatch_graph_json=copy.deepcopy(persisted_graph),
    )
    entry = enqueue_run(run, tenant_id=str(user.default_organization_id))
    engine_client = _RecordingEngineClient()

    monkeypatch.setattr(
        process_run_queue,
        "prepare_graph_for_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "prepare_graph_for_engine should not run for persisted dispatch_graph_json"
            )
        ),
    )
    monkeypatch.setattr(process_run_queue, "validate_prompt_credentials", lambda graph, owner: [])
    monkeypatch.setattr(
        process_run_queue, "resolve_engine_callback_url", lambda run_id: "http://callback"
    )
    monkeypatch.setattr(
        process_run_queue,
        "select_engine_target",
        lambda run_id: SimpleNamespace(host="localhost", port=50051, engine_id="engine-1"),
    )
    monkeypatch.setattr(
        process_run_queue, "get_engine_client", lambda *args, **kwargs: engine_client
    )
    monkeypatch.setattr(process_run_queue, "broadcast_run_updated", lambda run: None)
    monkeypatch.setattr(process_run_queue, "record_run_started", lambda: None)

    ProcessRunQueueCommand()._process_entry(
        entry,
        RunQueueSettings(
            max_per_tenant=1,
            lock_timeout_seconds=300,
            retry_delay_seconds=30,
        ),
    )

    run.refresh_from_db()

    outbound_graph = cast(dict[str, Any], engine_client.start_calls[0]["graph_json"])
    outbound_metadata = cast(dict[str, Any], outbound_graph["metadata"])
    persisted_metadata = cast(dict[str, Any], original_persisted_graph["metadata"])

    assert persisted_graph == original_persisted_graph
    assert run.dispatch_graph_json == original_persisted_graph
    assert "backend_attempt_id" not in persisted_metadata
    assert outbound_metadata["tool_resolution"] == persisted_metadata["tool_resolution"]
    assert "backend_attempt_id" in outbound_metadata
