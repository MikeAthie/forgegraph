from __future__ import annotations

import pytest
from django.utils import timezone

from application.services.os_projection_rebuild import rebuild_os_projections_for_organization
from application.services.task_lifecycle import transition_task_lifecycle
from infrastructure.orm.models import (
    ApprovalTask,
    DecisionRecord,
    Graph,
    GraphVersion,
    NodeRun,
    Run,
    TaskRecord,
)

pytestmark = pytest.mark.django_db


def test_projection_incremental_replay_rebuilds_visible_task_and_decision_state(user) -> None:
    organization = user.default_organization
    graph = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Incremental Replay Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [{"id": "agent_1", "type": "agent", "name": "Agent 1"}], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="paused",
        started_at=timezone.now(),
    )
    node_run = NodeRun.objects.create(
        run=run,
        node_id="agent_1",
        node_type="agent",
        status="waiting",
        attempt=1,
        started_at=timezone.now(),
    )
    lifecycle_task = transition_task_lifecycle(
        run=run,
        node_id="agent_1",
        node_type="agent",
        to_status="waiting_for_decision",
        source="test",
        idempotency_key=f"projection-replay:{run.id}:agent_1:waiting",
        node_run=node_run,
    ).lifecycle_task
    ApprovalTask.objects.create(
        run=run,
        node_id="agent_1",
        assignee=user,
        status="pending",
        task_lifecycle=lifecycle_task,
        payload={"prompt_message": "Approve?"},
    )

    first = rebuild_os_projections_for_organization(organization)
    TaskRecord.objects.filter(organization=organization).delete()
    DecisionRecord.objects.filter(organization=organization).delete()
    second = rebuild_os_projections_for_organization(organization)

    assert first.read_model_counts["tasks"] == 1
    assert first.read_model_counts["decisions"] == 1
    assert second.read_model_counts["tasks"] == 1
    assert second.read_model_counts["decisions"] == 1
    assert TaskRecord.objects.get(organization=organization).status == "waiting_for_decision"
    assert DecisionRecord.objects.get(organization=organization).status == "pending"
