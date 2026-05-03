from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.task_lifecycle import (
    transition_task_lifecycle,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    Run,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _make_run(*, status: str = "running") -> Run:
    user = User.objects.create_user(
        email=f"task-lifecycle-{uuid4().hex}@example.com",
        password="password123",
    )
    ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Task Lifecycle Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "task_1", "type": "agent", "name": "Research"}],
            "edges": [],
        },
    )
    return Run.objects.create(
        owner=user,
        organization=user.default_organization,
        graph_version=version,
        status=status,
        dispatch_graph_json={"metadata": {"backend_attempt_id": "attempt-1"}},
    )


def test_duplicate_task_transition_returns_prior_state() -> None:
    run = _make_run()
    first = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:duplicate",
        reason="node started",
    )

    duplicate = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:duplicate",
        reason="node started again",
    )

    assert first.outcome == "accepted"
    assert duplicate.outcome == "duplicate"
    assert duplicate.duplicate is True
    assert duplicate.event.id == first.event.id
    assert TaskLifecycleEvent.objects.filter(idempotency_key="task:test:duplicate").count() == 1
    assert TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1").status == "running"


def test_out_of_order_transition_is_recorded_without_mutating_current_state() -> None:
    run = _make_run()

    result = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="completed",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:out-of-order",
        reason="completed before start",
    )

    task = TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1")
    assert result.outcome == "out_of_order"
    assert task.status == "created"
    assert result.event.to_status == "completed"
    assert result.event.outcome == "out_of_order"


def test_stale_attempt_transition_is_rejected_and_audited() -> None:
    run = _make_run()
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:attempt-1",
        reason="first attempt running",
    )
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=2,
        parent_attempt_number=1,
        source="test",
        idempotency_key="task:test:attempt-2",
        reason="retry attempt running",
    )

    result = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="completed",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:stale-attempt",
        reason="late completion from attempt 1",
    )

    task = TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1")
    assert result.outcome == "stale"
    assert task.status == "running"
    assert task.current_attempt == 2
    assert task.stale_event_count == 1
    assert result.event.outcome == "stale"


def test_task_cannot_complete_after_failed_run_without_late_marker() -> None:
    run = _make_run(status="failed")
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:running-before-late",
        reason="node started",
    )

    result = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="completed",
        attempt_number=1,
        source="test",
        idempotency_key="task:test:late-completion",
        reason="completion arrived after run failed",
    )

    task = TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1")
    assert result.outcome == "late"
    assert task.status == "running"
    assert task.late_event_count == 1
