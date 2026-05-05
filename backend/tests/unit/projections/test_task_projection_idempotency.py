from __future__ import annotations

import pytest
from django.utils import timezone

from application.services.task_lifecycle import transition_task_lifecycle
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import Graph, GraphVersion, Run, TaskRecord

pytestmark = pytest.mark.django_db


def test_task_projection_replays_idempotently(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Task Projection")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [{"id": "agent_1", "type": "agent", "name": "Agent"}], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )

    transition_task_lifecycle(
        run=run,
        node_id="agent_1",
        node_type="agent",
        to_status="running",
        source="test",
        idempotency_key=f"task:{run.id}:agent_1:running:1",
    )

    process_pending_projection_events(organization_id=organization.id)
    process_pending_projection_events(organization_id=organization.id)

    task = TaskRecord.objects.get(organization=organization, external_key=f"{run.id}:agent_1")
    assert task.status == "running"
    assert TaskRecord.objects.filter(organization=organization).count() == 1
