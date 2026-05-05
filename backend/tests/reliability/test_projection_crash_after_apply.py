from __future__ import annotations

import pytest

from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    DomainEvent,
    Graph,
    GraphVersion,
    ProcessedProjectionEvent,
    ProjectionCursor,
    Run,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
)

pytestmark = pytest.mark.django_db


def test_projection_replay_after_cursor_loss_does_not_drift_task_read_model(user) -> None:
    graph = Graph.objects.create(owner=user, name="Projection Crash Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(owner=user, graph_version=version, status="running")
    lifecycle_task = TaskLifecycleRecord.objects.create(
        organization=user.default_organization,
        run=run,
        source_node_id="node_1",
        node_type="agent",
        title="Node 1",
        status="running",
        external_key=f"{run.id}:node_1",
    )
    event = TaskLifecycleEvent.objects.create(
        organization=user.default_organization,
        lifecycle_task=lifecycle_task,
        run=run,
        event_type="task.running",
        source="test",
        from_status="queued",
        to_status="running",
        idempotency_key="projection-crash-task-running",
        outcome="accepted",
    )
    domain_event = DomainEvent.objects.get(
        idempotency_key=f"task-lifecycle-event:{event.id}",
    )

    first = process_pending_projection_events(
        organization_id=user.default_organization_id,
        projection_names=("tasks",),
    )
    ProjectionCursor.objects.filter(
        organization=user.default_organization,
        projection_name="tasks",
    ).update(last_sequence=0, last_event_id=None)
    second = process_pending_projection_events(
        organization_id=user.default_organization_id,
        projection_names=("tasks",),
    )

    assert first.processed >= 1
    assert second.skipped >= 1
    assert (
        ProcessedProjectionEvent.objects.filter(
            projection_name="tasks",
            event=domain_event,
        ).count()
        == 1
    )
    assert (
        TaskLifecycleRecord.objects.filter(
            organization=user.default_organization,
            external_key=f"{run.id}:node_1",
        ).count()
        == 1
    )
