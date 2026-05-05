from __future__ import annotations

import pytest
from django.utils import timezone

from application.projections import tasks
from application.services.task_lifecycle import transition_task_lifecycle
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    DomainEvent,
    Graph,
    GraphVersion,
    ProjectionCursor,
    Run,
    TaskRecord,
)

pytestmark = pytest.mark.django_db


def test_projection_worker_recovers_after_apply_before_cursor_update(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Crash Recovery")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )
    lifecycle_task = transition_task_lifecycle(
        run=run,
        node_id="node_1",
        node_type="prompt",
        to_status="running",
        source="test",
        idempotency_key=f"task:{run.id}:node_1:running:1",
    ).lifecycle_task
    event = DomainEvent.objects.get(
        organization=organization,
        event_type="task.lifecycle_transitioned",
        payload__task_lifecycle_id=str(lifecycle_task.id),
    )

    tasks.apply(event)
    assert TaskRecord.objects.filter(organization=organization).count() == 1
    assert not ProjectionCursor.objects.filter(
        organization=organization, projection_name="tasks"
    ).exists()

    process_pending_projection_events(organization_id=organization.id)

    assert TaskRecord.objects.filter(organization=organization).count() == 1
    cursor = ProjectionCursor.objects.get(organization=organization, projection_name="tasks")
    assert cursor.last_sequence >= event.sequence
