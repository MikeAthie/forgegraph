from __future__ import annotations

import pytest
from django.utils import timezone

from application.services.task_lifecycle import transition_task_lifecycle
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import ApprovalTask, DecisionRecord, Graph, GraphVersion, Run

pytestmark = pytest.mark.django_db


def test_decision_projection_updates_approval_idempotently(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Decision Projection")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [{"id": "gate", "type": "human_gate", "name": "Gate"}], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="paused",
        started_at=timezone.now(),
    )
    lifecycle_task = transition_task_lifecycle(
        run=run,
        node_id="gate",
        node_type="human_gate",
        to_status="waiting_for_decision",
        source="test",
        idempotency_key=f"task:{run.id}:gate:waiting:1",
    ).lifecycle_task
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="gate",
        assignee=user,
        status="pending",
        task_lifecycle=lifecycle_task,
        payload={"prompt_message": "Approve", "required_fields": []},
    )

    process_pending_projection_events(organization_id=organization.id)
    assert DecisionRecord.objects.filter(organization=organization).count() == 1

    approval.status = "approved"
    approval.result = {"approved": True}
    approval.resolved_at = timezone.now()
    approval.save(update_fields=["status", "result", "resolved_at"])

    process_pending_projection_events(organization_id=organization.id)
    process_pending_projection_events(organization_id=organization.id)

    decision = DecisionRecord.objects.get(
        organization=organization, external_key=f"approval:{approval.id}"
    )
    assert decision.status == "approved"
    assert decision.resolution_json == {"approved": True}
    assert DecisionRecord.objects.filter(organization=organization).count() == 1
