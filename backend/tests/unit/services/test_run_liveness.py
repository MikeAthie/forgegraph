from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.run_liveness import (
    RECOVERY_POLICY_RESUME,
    CheckpointContext,
    apply_recovery_policy,
    reconcile_stale_runs,
    recovery_state_for_status,
    touch_run_liveness,
)
from infrastructure.orm.models import Graph, GraphVersion, Run, RunCheckpoint, RunEvent, User

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
    assert "Run stalled with no backend-observed progress" in run.error_message


def test_run_recovery_policy_defaults_to_fail():
    run = _make_run(status="running")

    assert run.recovery_policy == "fail"


def test_apply_recovery_policy_records_checkpoint_context():
    run = _make_run(status="running", last_progress_at=timezone.now() - timedelta(minutes=10))
    checkpoint = RunCheckpoint.objects.create(
        run=run,
        node_id="approval_gate",
        step_index=4,
        state_json={"state": "snapshot"},
        completed_nodes=["draft"],
        skipped_nodes=[],
        graph_json={"nodes": [], "edges": []},
    )
    checkpoint_context = CheckpointContext.from_run(run)

    applied = apply_recovery_policy(
        run,
        checkpoint_context=checkpoint_context,
        now=timezone.now(),
    )

    assert applied is True
    run.refresh_from_db()
    assert run.status == "failed"
    assert "checkpoint=node:approval_gate step:4" in run.error_message

    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["recovery_policy"] == "fail"
    assert event.payload["checkpoint_available"] is True
    assert event.payload["checkpoint_node_id"] == "approval_gate"
    assert event.payload["checkpoint_step_index"] == 4
    assert event.payload["checkpoint_updated_at"] == checkpoint.updated_at.isoformat()


def test_reconcile_stale_runs_fails_unimplemented_resume_policy_and_marks_context():
    stale_time = timezone.now() - timedelta(minutes=10)
    run = _make_run(status="running", last_progress_at=stale_time)
    run.recovery_policy = RECOVERY_POLICY_RESUME
    run.save(update_fields=["recovery_policy"])

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 1
    assert result.reconciled == 1
    run.refresh_from_db()
    assert run.status == "failed"
    assert "recovery policy 'resume' is not implemented" in run.error_message
    event = RunEvent.objects.get(run=run, event_type="run.updated")
    assert event.payload["checkpoint_available"] is False
    assert event.payload["recovery_policy"] == RECOVERY_POLICY_RESUME


def test_reconcile_stale_runs_skips_paused_runs():
    stale_time = timezone.now() - timedelta(minutes=10)
    _make_run(status="paused", last_progress_at=stale_time)

    result = reconcile_stale_runs(stale_after_seconds=60, now=timezone.now())

    assert result.scanned == 0
    assert result.reconciled == 0
