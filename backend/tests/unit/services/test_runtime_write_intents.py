from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from application.services.run_snapshots import RunSnapshot, get_snapshot, set_snapshot
from application.services.runtime_write_intents import (
    RuntimeIntentEnvelope,
    apply_ack_run_resumed_intent,
    apply_node_completed_intent,
    apply_pause_run_intent,
    apply_set_run_status_intent,
    apply_store_checkpoint_intent,
    apply_upsert_node_run_intent,
)
from infrastructure.orm.models import (
    ApprovalTask,
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

pytestmark = pytest.mark.django_db


def _make_run(*, status: str = "running") -> Run:
    user = User.objects.create_user(
        email=f"runtime-intents-{uuid4().hex}@example.com",
        password="password123",
    )
    graph = Graph.objects.create(owner=user, name="Runtime Intent Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status=status,
        trace_id="trace-before",
    )


def _intent(
    *,
    run: Run,
    intent_type: str,
    payload: dict[str, object],
    attempt_id: str = "attempt-default",
    trace_id: str = "trace-intent",
    intent_id: UUID | None = None,
) -> RuntimeIntentEnvelope:
    return RuntimeIntentEnvelope(
        intent_id=intent_id or uuid4(),
        intent_type=intent_type,
        run_id=run.id,
        attempt_id=attempt_id,
        trace_id=trace_id,
        timestamp=timezone.now(),
        payload=payload,
    )


def _pause_intent(*, run: Run, intent_id: UUID | None = None) -> RuntimeIntentEnvelope:
    timestamp = timezone.now()
    return RuntimeIntentEnvelope(
        intent_id=intent_id or uuid4(),
        intent_type="pause_run",
        run_id=run.id,
        attempt_id="1",
        trace_id="trace-pause-1",
        timestamp=timestamp,
        payload={
            "node_id": "human_gate_1",
            "node_type": "human_gate",
            "node_name": "Human Review",
            "node_attempt": 1,
            "pause_payload": {
                "prompt_message": "Approve the draft",
                "required_fields": ["feedback"],
            },
            "checkpoint": {
                "node_id": "human_gate_1",
                "step_index": 7,
                "state_snapshot": {
                    "checkpoint_version": 2,
                    "state": {"approved": False},
                    "completed": ["start"],
                    "skipped": [],
                    "pending": {"human_gate_1": 0},
                    "visit_counts": {"start": 1},
                },
                "completed_nodes": ["start"],
                "skipped_nodes": [],
                "graph_json": {"nodes": [], "edges": []},
            },
            "pause_state": {
                "state_snapshot": {"approved": False},
                "completed_nodes": ["start"],
                "skipped_nodes": [],
                "graph_json": '{"nodes":[],"edges":[]}',
                "tenant_id": "tenant-1",
            },
        },
    )


@patch("application.services.runtime_write_intents.broadcast_decision_required")
@patch("application.services.runtime_write_intents.broadcast_run_updated")
def test_apply_pause_run_intent_persists_backend_owned_pause_state(
    broadcast_run_updated,
    broadcast_decision_required,
):
    run = _make_run()
    intent = _pause_intent(run=run)

    result = apply_pause_run_intent(intent=intent, stream_message_id="1700000000000-0")

    assert result == "processed"

    run.refresh_from_db()
    assert run.status == "paused"
    assert run.paused_node_id == "human_gate_1"
    assert run.pause_state_json is not None
    assert run.pause_state_json["tenant_id"] == "tenant-1"
    assert run.trace_id == "trace-pause-1"

    checkpoint = RunCheckpoint.objects.get(run=run)
    assert checkpoint.node_id == "human_gate_1"
    assert checkpoint.step_index == 7
    assert checkpoint.state_json["checkpoint_version"] == 2

    node_run = NodeRun.objects.get(run=run, node_id="human_gate_1", attempt=1)
    assert node_run.status == "waiting"
    assert node_run.output_json == {
        "pause_payload": {
            "prompt_message": "Approve the draft",
            "required_fields": ["feedback"],
        }
    }

    approval_task = ApprovalTask.objects.get(run=run, node_id="human_gate_1")
    assert approval_task.status == "pending"
    assert approval_task.payload == {
        "prompt_message": "Approve the draft",
        "required_fields": ["feedback"],
    }

    run_projection = RunEventProjection.objects.get(run=run)
    assert run_projection.status == "paused"
    assert run_projection.paused_node_id == "human_gate_1"

    node_projection = NodeRunEventProjection.objects.get(
        run=run,
        node_id="human_gate_1",
        attempt=1,
    )
    assert node_projection.status == "waiting"

    runtime_event = RunEvent.objects.get(run=run, external_id=str(intent.intent_id))
    assert runtime_event.event_type == "run.updated"
    assert runtime_event.payload["status"] == "paused"

    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "pause_run"
    assert processed.stream_message_id == "1700000000000-0"

    broadcast_run_updated.assert_called_once()
    broadcast_decision_required.assert_called_once()


@patch("application.services.runtime_write_intents.logger")
def test_stale_intent_is_ignored_and_logged(logger_mock):
    run = _make_run(status="running")
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node="node-current",
            next_node="node-next",
            attempt_id="attempt-b",
            updated_at=timezone.now(),
        )
    )
    intent = _pause_intent(run=run)
    intent = RuntimeIntentEnvelope(
        intent_id=intent.intent_id,
        intent_type=intent.intent_type,
        run_id=intent.run_id,
        attempt_id="attempt-a",
        trace_id=intent.trace_id,
        timestamp=intent.timestamp,
        payload=intent.payload,
    )

    result = apply_pause_run_intent(intent=intent, stream_message_id="1700000000000-stale")

    assert result == "ignored"
    run.refresh_from_db()
    assert run.status == "running"
    assert not RunCheckpoint.objects.filter(run=run).exists()
    assert not ProcessedRuntimeIntent.objects.filter(intent_id=intent.intent_id).exists()
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "intent_ignored_due_to_stale_attempt"
    assert logger_mock.warning.call_args.kwargs["extra"] == {
        "run_id": str(run.id),
        "intent_id": str(intent.intent_id),
        "intent_type": "pause_run",
        "intent_attempt_id": "attempt-a",
        "current_attempt_id": "attempt-b",
    }


@patch("application.services.runtime_write_intents.broadcast_decision_required")
@patch("application.services.runtime_write_intents.broadcast_run_updated")
def test_missing_snapshot_does_not_block_intent_processing(
    broadcast_run_updated,
    broadcast_decision_required,
):
    run = _make_run(status="running")
    intent = _pause_intent(run=run)

    result = apply_pause_run_intent(intent=intent, stream_message_id="1700000000000-nosnapshot")

    assert result == "processed"
    run.refresh_from_db()
    assert run.status == "paused"
    assert RunCheckpoint.objects.filter(run=run).exists()
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent.intent_id).exists()
    broadcast_run_updated.assert_called_once()
    broadcast_decision_required.assert_called_once()


@patch("application.services.runtime_write_intents.broadcast_decision_required")
@patch("application.services.runtime_write_intents.broadcast_run_updated")
def test_apply_pause_run_intent_is_idempotent_for_duplicate_intent_id(
    broadcast_run_updated,
    broadcast_decision_required,
):
    run = _make_run()
    intent = _pause_intent(run=run)

    first = apply_pause_run_intent(intent=intent, stream_message_id="1700000000000-0")
    second = apply_pause_run_intent(intent=intent, stream_message_id="1700000000001-0")

    assert first == "processed"
    assert second == "duplicate"
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent.intent_id).count() == 1
    assert RunEvent.objects.filter(run=run).count() == 1
    assert ApprovalTask.objects.filter(run=run, node_id="human_gate_1").count() == 1

    broadcast_run_updated.assert_called_once()
    broadcast_decision_required.assert_called_once()


@patch("application.services.runtime_write_intents.broadcast_decision_resolved")
@patch("application.services.runtime_write_intents.broadcast_run_updated")
def test_apply_ack_run_resumed_intent_clears_pause_state_and_resume_tracking(
    broadcast_run_updated,
    broadcast_decision_resolved,
):
    resume_attempt_id = uuid4()
    run = _make_run(status="resume_requested")
    run.paused_node_id = "human_gate_1"
    run.pause_state_json = {"prompt_message": "Approve", "required_fields": ["feedback"]}
    run.resume_requested_at = timezone.now()
    run.resume_attempt_id = resume_attempt_id
    run.save(
        update_fields=[
            "paused_node_id",
            "pause_state_json",
            "resume_requested_at",
            "resume_attempt_id",
        ]
    )
    intent = _intent(
        run=run,
        intent_type="ack_run_resumed",
        attempt_id=str(resume_attempt_id),
        trace_id="trace-resume",
        payload={
            "node_id": "human_gate_1",
            "resolution": {"approved": True, "feedback": "ship it"},
        },
    )

    result = apply_ack_run_resumed_intent(intent=intent, stream_message_id="1700000000002-0")

    assert result == "processed"
    run.refresh_from_db()
    assert run.status == "running"
    assert run.paused_node_id is None
    assert run.pause_state_json is None
    assert run.resume_requested_at is None
    assert run.resume_attempt_id is None
    assert run.trace_id == "trace-resume"

    run_projection = RunEventProjection.objects.get(run=run)
    assert run_projection.status == "running"
    assert run_projection.paused_node_id is None

    runtime_event = RunEvent.objects.get(run=run, external_id=str(intent.intent_id))
    assert runtime_event.payload["status"] == "running"

    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "ack_run_resumed"

    broadcast_run_updated.assert_called_once()
    broadcast_decision_resolved.assert_called_once()


@patch("application.services.runtime_write_intents.logger")
def test_apply_store_checkpoint_intent_persists_checkpoint_without_run_status_change(logger_mock):
    run = _make_run(status="running")
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node="node_1",
            next_node="node_2",
            attempt_id="11",
            updated_at=timezone.now(),
        )
    )
    intent = _intent(
        run=run,
        intent_type="store_checkpoint",
        attempt_id="11",
        payload={
            "node_id": "node_2",
            "step_index": 11,
            "state_snapshot": {"checkpoint_version": 2, "state": {"foo": "bar"}},
            "completed_nodes": ["node_1"],
            "skipped_nodes": [],
            "graph_json": {"nodes": [{"id": "node_1"}], "edges": []},
        },
    )

    result = apply_store_checkpoint_intent(intent=intent, stream_message_id="1700000000003-0")

    assert result == "processed"
    run.refresh_from_db()
    assert run.status == "running"

    checkpoint = RunCheckpoint.objects.get(run=run)
    assert checkpoint.node_id == "node_2"
    assert checkpoint.step_index == 11
    assert checkpoint.state_json["state"]["foo"] == "bar"

    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "store_checkpoint"
    logger_mock.warning.assert_not_called()


def test_apply_node_completed_intent_does_not_write_snapshot_when_transaction_rolls_back():
    run = _make_run(status="running")
    NodeRun.objects.create(
        run=run,
        node_id="node_rollback",
        node_type="transform",
        status="succeeded",
        attempt=1,
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={"output": {"ok": True}},
    )
    intent = _intent(
        run=run,
        intent_type="node_completed",
        attempt_id="resume-attempt-rollback",
        payload={
            "node_id": "node_rollback",
            "attempt": 1,
            "next_node": "node_after_rollback",
        },
    )

    with pytest.raises(RuntimeError, match="force rollback"):
        with TestCase.captureOnCommitCallbacks(execute=True) as callbacks:
            with transaction.atomic():
                result = apply_node_completed_intent(
                    intent=intent,
                    stream_message_id="1700000000003-rollback",
                )
                assert result == "processed"
                raise RuntimeError("force rollback")

    assert callbacks == []
    assert get_snapshot(run.id) is None
    assert not ProcessedRuntimeIntent.objects.filter(intent_id=intent.intent_id).exists()


def test_apply_node_completed_intent_writes_snapshot_after_commit():
    run = _make_run(status="running")
    NodeRun.objects.create(
        run=run,
        node_id="node_2",
        node_type="transform",
        status="succeeded",
        attempt=2,
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={"output": {"ok": True}},
    )
    intent = _intent(
        run=run,
        intent_type="node_completed",
        attempt_id="resume-attempt-7",
        payload={
            "node_id": "node_2",
            "attempt": 2,
            "next_node": "node_3",
        },
    )

    with TestCase.captureOnCommitCallbacks(execute=True):
        result = apply_node_completed_intent(intent=intent, stream_message_id="1700000000003-1")

    assert result == "processed"
    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "node_completed"

    snapshot = get_snapshot(run.id)
    assert snapshot is not None
    assert str(snapshot.run_id) == str(run.id)
    assert snapshot.last_completed_node == "node_2"
    assert snapshot.next_node == "node_3"
    assert snapshot.attempt_id == "resume-attempt-7"


@patch("application.services.runtime_write_intents.logger")
def test_new_attempt_supersedes_old_snapshot_attempt(logger_mock):
    run = _make_run(status="running")
    NodeRun.objects.create(
        run=run,
        node_id="node_2",
        node_type="transform",
        status="succeeded",
        attempt=1,
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={"output": {"ok": True}},
    )
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node="node_1",
            next_node="node_2",
            attempt_id="attempt-b",
            updated_at=timezone.now(),
        )
    )
    stale_intent = _intent(
        run=run,
        intent_type="node_completed",
        attempt_id="attempt-a",
        payload={
            "node_id": "node_2",
            "attempt": 1,
            "next_node": "node_3",
        },
    )
    fresh_intent = _intent(
        run=run,
        intent_type="node_completed",
        attempt_id="attempt-b",
        payload={
            "node_id": "node_2",
            "attempt": 1,
            "next_node": "node_3",
        },
    )

    stale_result = apply_node_completed_intent(
        intent=stale_intent,
        stream_message_id="1700000000003-stale",
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        fresh_result = apply_node_completed_intent(
            intent=fresh_intent,
            stream_message_id="1700000000003-fresh",
        )

    assert stale_result == "ignored"
    assert fresh_result == "processed"
    assert not ProcessedRuntimeIntent.objects.filter(intent_id=stale_intent.intent_id).exists()
    assert ProcessedRuntimeIntent.objects.filter(intent_id=fresh_intent.intent_id).exists()
    snapshot = get_snapshot(run.id)
    assert snapshot is not None
    assert snapshot.attempt_id == "attempt-b"
    assert snapshot.last_completed_node == "node_2"
    logger_mock.warning.assert_called_once()


@patch("application.services.runtime_write_intents.safe_delete_snapshot")
@patch("application.services.runtime_write_intents.broadcast_run_updated")
def test_apply_set_run_status_intent_updates_run_and_clears_pause_state_for_terminal_status(
    broadcast_run_updated,
    delete_snapshot_mock,
):
    run = _make_run(status="running")
    run.paused_node_id = "human_gate_1"
    run.pause_state_json = {"tenant_id": "tenant-1"}
    run.resume_requested_at = timezone.now()
    run.resume_attempt_id = uuid4()
    run.save(
        update_fields=[
            "paused_node_id",
            "pause_state_json",
            "resume_requested_at",
            "resume_attempt_id",
        ]
    )
    ended_at = timezone.now()
    intent = _intent(
        run=run,
        intent_type="set_run_status",
        attempt_id=str(run.resume_attempt_id),
        trace_id="trace-terminal",
        payload={
            "status": "failed",
            "ended_at": ended_at.isoformat(),
            "error_message": "node exploded",
            "output_json": {"partial": True},
        },
    )

    with TestCase.captureOnCommitCallbacks(execute=True):
        result = apply_set_run_status_intent(intent=intent, stream_message_id="1700000000004-0")

    assert result == "processed"
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.ended_at == ended_at
    assert run.error_message == "node exploded"
    assert run.output_json == {"partial": True}
    assert run.paused_node_id is None
    assert run.pause_state_json is None
    assert run.resume_requested_at is None
    assert run.resume_attempt_id is None

    projection = RunEventProjection.objects.get(run=run)
    assert projection.status == "failed"
    assert projection.error_message == "node exploded"

    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "set_run_status"

    delete_snapshot_mock.assert_called_once_with(run.id)
    broadcast_run_updated.assert_called_once()


@patch("application.services.run_snapshots.logger")
@patch("application.services.run_snapshots.set_snapshot")
def test_apply_node_completed_intent_snapshot_write_failure_does_not_break_commit(
    set_snapshot_mock,
    logger_mock,
):
    run = _make_run(status="running")
    NodeRun.objects.create(
        run=run,
        node_id="node_redis_failure",
        node_type="transform",
        status="succeeded",
        attempt=1,
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={"output": {"ok": True}},
    )
    set_snapshot_mock.side_effect = RuntimeError("redis unavailable")
    intent = _intent(
        run=run,
        intent_type="node_completed",
        attempt_id="resume-attempt-redis-failure",
        payload={
            "node_id": "node_redis_failure",
            "attempt": 1,
            "next_node": "node_after_redis_failure",
        },
    )

    with TestCase.captureOnCommitCallbacks(execute=True):
        result = apply_node_completed_intent(intent=intent, stream_message_id="1700000000003-2")

    assert result == "processed"
    run.refresh_from_db()
    assert run.status == "running"
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent.intent_id).exists()
    assert get_snapshot(run.id) is None
    set_snapshot_mock.assert_called_once()
    logger_mock.error.assert_called_once()
    assert logger_mock.error.call_args.args[0] == "snapshot_write_failed"
    assert logger_mock.error.call_args.kwargs["extra"] == {
        "run_id": str(run.id),
        "node_id": "node_redis_failure",
        "next_node": "node_after_redis_failure",
        "attempt_id": "resume-attempt-redis-failure",
    }


@patch("application.services.runtime_write_intents.broadcast_node_run_updated")
def test_apply_upsert_node_run_intent_upserts_node_run_and_projection(
    broadcast_node_run_updated,
):
    run = _make_run(status="running")
    started_at = timezone.now()
    ended_at = timezone.now()
    intent = _intent(
        run=run,
        intent_type="upsert_node_run",
        attempt_id="2",
        trace_id="trace-node",
        payload={
            "id": str(uuid4()),
            "node_id": "node_7",
            "node_type": "prompt",
            "status": "succeeded",
            "attempt": 2,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "input_json": {"prompt": "hello"},
            "output_json": {"answer": "world"},
            "trace_id": "trace-node",
            "span_id": "span-node",
        },
    )

    result = apply_upsert_node_run_intent(intent=intent, stream_message_id="1700000000005-0")

    assert result == "processed"

    node_run = NodeRun.objects.get(run=run, node_id="node_7", attempt=2)
    assert node_run.status == "succeeded"
    assert node_run.node_type == "prompt"
    assert node_run.started_at == started_at
    assert node_run.ended_at == ended_at
    assert node_run.input_json == {"prompt": "hello"}
    assert node_run.output_json == {"answer": "world"}
    assert node_run.trace_id == "trace-node"
    assert node_run.span_id == "span-node"

    projection = NodeRunEventProjection.objects.get(run=run, node_id="node_7", attempt=2)
    assert projection.status == "succeeded"
    assert projection.output_json == {"answer": "world"}

    processed = ProcessedRuntimeIntent.objects.get(intent_id=intent.intent_id)
    assert processed.intent_type == "upsert_node_run"

    broadcast_node_run_updated.assert_called_once()
