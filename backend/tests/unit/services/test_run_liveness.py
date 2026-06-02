from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.run_liveness import (
    RECOVERY_POLICY_RESUME,
    RECOVERY_POLICY_RETRY,
    CheckpointContext,
    apply_recovery_policy,
    reconcile_stale_runs,
    recovery_state_for_status,
    touch_run_liveness,
)
from application.services.run_snapshots import RunSnapshot, set_snapshot
from infrastructure.orm.models import Graph, GraphVersion, Run, RunEvent, User

pytestmark = pytest.mark.django_db


def _make_run(*, status: str = "running", last_progress_at=None) -> Run:
    user = User.objects.create_user(
        email=f"run-liveness-{uuid4()}@example.com",
        password="password123",
    )
    graph = Graph.objects.create(owner=user, name="Liveness Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status=status,
        last_progress_at=last_progress_at,
    )


def test_touch_run_liveness_sets_progress_fields():
    run = _make_run(status="running")

    update_fields = touch_run_liveness(run, recovery_state=recovery_state_for_status("running"))

    assert "last_progress_at" in update_fields
    assert "last_heartbeat_at" in update_fields
    assert run.last_progress_at is not None
    assert run.last_heartbeat_at is not None
    assert run.recovery_state == "active"


def test_reconcile_stale_runs_fails_stuck_running_run():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="running", last_progress_at=stale_time)

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.recovery_state == "stalled_failed"
    assert run.recovery_reason == "engine_stalled"
    assert "Run stalled with no backend-observed progress" in run.error_message


def test_reconcile_stale_runs_detects_running_run_without_progress_timestamp():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="running", last_progress_at=None)
    run.started_at = stale_time
    run.save(update_fields=["started_at"])

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.recovery_reason == "engine_stalled"


@override_settings(RUN_ENGINE_STALLED_TIMEOUT_SECONDS=30, RUN_LIVENESS_TIMEOUT_SECONDS=300)
def test_reconcile_stale_runs_uses_engine_stalled_timeout_setting_by_default():
    stale_time = timezone.now() - timedelta(seconds=45)
    run = _make_run(status="running", last_progress_at=stale_time)

    result = reconcile_stale_runs(now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"


def test_run_recovery_policy_defaults_to_fail():
    run = _make_run(status="running")

    assert run.recovery_policy == "fail"


def test_apply_recovery_policy_records_checkpoint_context():
    run = _make_run(status="running", last_progress_at=timezone.now() - timedelta(minutes=10))
    checkpoint = RunSnapshot(
        run_id=run.id,
        last_completed_node="approval_gate",
        next_node="after_gate",
        attempt_id="attempt-4",
        updated_at=timezone.now(),
    )
    set_snapshot(checkpoint)
    checkpoint_context = CheckpointContext.from_run(run)

    applied = apply_recovery_policy(
        run,
        checkpoint_context=checkpoint_context,
        now=timezone.now(),
    )

    assert applied is True
    run.refresh_from_db()
    assert run.status == "failed"
    assert "checkpoint=node:approval_gate next:after_gate attempt:attempt-4" in run.error_message

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["recovery_policy"] == "fail"
    assert event.payload["checkpoint_available"] is True
    assert event.payload["checkpoint_node_id"] == "approval_gate"
    assert event.payload["checkpoint_next_node"] == "after_gate"
    assert event.payload["checkpoint_attempt_id"] == "attempt-4"
    assert event.payload["checkpoint_updated_at"] == checkpoint.updated_at.isoformat()


@override_settings(RUN_QUEUE_ENABLED=False)
def test_reconcile_stale_runs_fails_resume_policy_when_queue_is_disabled():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="running", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.save(update_fields=["recovery_policy"])

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert "requires RUN_QUEUE_ENABLED=true" in run.error_message
    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["checkpoint_available"] is False
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RESUME


@override_settings(RUN_QUEUE_ENABLED=True)
def test_reconcile_stale_runs_requeues_retry_policy_and_clears_checkpoint():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="running", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RETRY
    run.paused_node_id = "gate"
    run.pause_state_json = {"state_snapshot": {"foo": "bar"}}
    run.engine_instance_id = "engine-a"
    run.save(
        update_fields=[
            "recovery_policy",
            "paused_node_id",
            "pause_state_json",
            "engine_instance_id",
        ]
    )
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node="checkpoint_node",
            next_node="after_checkpoint",
            attempt_id="attempt-3",
            updated_at=timezone.now(),
        )
    )

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "pending"
    assert run.recovery_state == "stalled_retry_pending"
    assert run.recovery_reason == "engine_stalled"
    assert run.error_message == ""
    assert run.engine_instance_id == ""
    assert run.paused_node_id is None
    assert run.pause_state_json is None
    assert CheckpointContext.from_run(run).checkpoint_available is False

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RETRY
    assert event.payload["recovery_action"] == RECOVERY_POLICY_RETRY
    assert event.payload["recovery_reason"] == "engine_stalled"
    assert event.payload["checkpoint_cleared"] is True

    queue_entry = run.queue_entry
    assert queue_entry.status == "pending"


@override_settings(RUN_QUEUE_ENABLED=True)
def test_reconcile_stale_runs_requeues_stale_resume_requested_run_from_checkpoint():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="resume_requested", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.engine_instance_id = "engine-a"
    run.resume_requested_at = stale_time
    run.save(update_fields=["recovery_policy", "engine_instance_id", "resume_requested_at"])
    checkpoint = RunSnapshot(
        run_id=run.id,
        last_completed_node="resume_gate",
        next_node="after_resume_gate",
        attempt_id="attempt-7",
        updated_at=timezone.now(),
    )
    set_snapshot(checkpoint)

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "pending"
    assert run.recovery_state == "stalled_resume_pending"
    assert run.recovery_reason == "resume_timeout"
    assert run.engine_instance_id == ""
    assert run.resume_requested_at is None
    assert run.resume_attempt_id is None

    assert CheckpointContext.from_run(run).checkpoint_node_id == "resume_gate"

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RESUME
    assert event.payload["recovery_action"] == RECOVERY_POLICY_RESUME
    assert event.payload["recovery_reason"] == "resume_timeout"
    assert event.payload["checkpoint_cleared"] is False
    assert event.payload["checkpoint_available"] is True

    queue_entry = run.queue_entry
    assert queue_entry.status == "pending"


@override_settings(RUN_QUEUE_ENABLED=True)
def test_reconcile_stale_resume_uses_backend_checkpoint_not_resume_attempt_state():
    stale_time = timezone.now() - timedelta(minutes=10)
    active_resume_attempt_id = uuid4()
    run = _make_run(status="resume_requested", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.engine_instance_id = "engine-with-stale-memory"
    run.resume_requested_at = stale_time
    run.resume_attempt_id = active_resume_attempt_id
    run.paused_node_id = "client_resume_gate"
    run.pause_state_json = {
        "resume_attempt_id": str(active_resume_attempt_id),
        "next_node": "client_claimed_next_node",
    }
    run.save(
        update_fields=[
            "recovery_policy",
            "engine_instance_id",
            "resume_requested_at",
            "resume_attempt_id",
            "paused_node_id",
            "pause_state_json",
        ]
    )
    checkpoint = RunSnapshot(
        run_id=run.id,
        last_completed_node="backend_approved_gate",
        next_node="backend_owned_next_node",
        attempt_id="backend-snapshot-attempt",
        updated_at=timezone.now(),
    )
    set_snapshot(checkpoint)

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "pending"
    assert run.recovery_state == "stalled_resume_pending"
    assert run.recovery_reason == "resume_timeout"
    assert run.engine_instance_id == ""
    assert run.resume_requested_at is None
    assert run.resume_attempt_id is None
    assert run.paused_node_id is None
    assert run.pause_state_json is None

    checkpoint_context = CheckpointContext.from_run(run)
    assert checkpoint_context.checkpoint_node_id == "backend_approved_gate"
    assert checkpoint_context.checkpoint_next_node == "backend_owned_next_node"
    assert checkpoint_context.checkpoint_attempt_id == "backend-snapshot-attempt"
    assert checkpoint_context.checkpoint_attempt_id != str(active_resume_attempt_id)

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RESUME
    assert event.payload["recovery_action"] == RECOVERY_POLICY_RESUME
    assert event.payload["recovery_reason"] == "resume_timeout"
    assert event.payload["checkpoint_cleared"] is False
    assert event.payload["checkpoint_available"] is True
    assert event.payload["checkpoint_node_id"] == "backend_approved_gate"
    assert event.payload["checkpoint_next_node"] == "backend_owned_next_node"
    assert event.payload["checkpoint_attempt_id"] == "backend-snapshot-attempt"
    assert str(active_resume_attempt_id) not in event.payload["recovery_message"]

    queue_entry = run.queue_entry
    assert queue_entry.status == "pending"


@override_settings(RUN_QUEUE_ENABLED=True)
def test_reconcile_stale_runs_fails_resume_policy_without_checkpoint():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="resume_requested", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.resume_requested_at = stale_time
    run.save(update_fields=["recovery_policy", "resume_requested_at"])

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.recovery_reason == "missing_checkpoint"
    assert "requires a backend-owned checkpoint" in run.error_message


@override_settings(RUN_QUEUE_ENABLED=True)
def test_reconcile_stale_runs_fails_resume_policy_when_snapshot_store_unavailable(monkeypatch):
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="resume_requested", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.resume_requested_at = stale_time
    run.save(update_fields=["recovery_policy", "resume_requested_at"])

    def _raise_snapshot_unavailable(_run_id):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        "application.services.run_liveness.get_snapshot", _raise_snapshot_unavailable
    )

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.recovery_reason == "missing_checkpoint"
    assert "requires a backend-owned checkpoint" in run.error_message

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["checkpoint_available"] is False
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RESUME


def test_reconcile_stale_runs_skips_paused_runs():
    stale_time = timezone.now() - timedelta(minutes=10)
    _make_run(status="paused", last_progress_at=stale_time)

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 0
    assert result.reconciled == 0
