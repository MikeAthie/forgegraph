from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.run_liveness import (
    reconcile_stale_runs,
    recovery_state_for_status,
    touch_run_liveness,
)
from infrastructure.orm.models import Graph, GraphVersion, Run, User


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
