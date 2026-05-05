from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from application.services.os_projection_rebuild import rebuild_os_projections_for_organization
from application.services.task_lifecycle import transition_task_lifecycle
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    CostAggregate,
    CostLedgerEntry,
    DecisionRecord,
    Graph,
    GraphVersion,
    LLMUsage,
    MemoryObservation,
    NodeRun,
    Run,
    TaskRecord,
)

pytestmark = pytest.mark.django_db


def test_os_projection_rebuild_replays_backend_domain_events(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Replay Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "ops_agent", "type": "agent", "name": "Ops Agent"}],
            "edges": [],
        },
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
        node_id="ops_agent",
        node_type="agent",
        status="waiting",
        attempt=1,
        started_at=timezone.now(),
    )
    lifecycle_task = transition_task_lifecycle(
        run=run,
        node_id="ops_agent",
        node_type="agent",
        to_status="waiting_for_decision",
        source="test",
        idempotency_key=f"task:{run.id}:ops_agent:waiting:1",
        node_run=node_run,
    ).lifecycle_task
    ApprovalTask.objects.create(
        run=run,
        node_id="ops_agent",
        assignee=user,
        status="pending",
        task_lifecycle=lifecycle_task,
        payload={"prompt_message": "Approve vendor payment"},
    )
    LLMUsage.objects.create(
        tenant_id=organization.id,
        run=run,
        node_id="ops_agent",
        provider="openai",
        model="gpt-4.1-mini",
        total_tokens=150,
        cost_usd=Decimal("0.750000"),
    )
    MemoryObservation.objects.create(
        tenant_id=organization.id,
        graph_id=graph.id,
        run_id=run.id,
        type="fact",
        title="Vendor threshold",
        content="Vendor payments above threshold require approval.",
        scope="run",
        topic_key="vendor-approval-threshold",
    )

    first = rebuild_os_projections_for_organization(organization)
    first_counts = first.read_model_counts

    AgentRegistryEntry.objects.filter(organization=organization).delete()
    TaskRecord.objects.filter(organization=organization).delete()
    DecisionRecord.objects.filter(organization=organization).delete()
    CostLedgerEntry.objects.filter(organization=organization).delete()
    CostAggregate.objects.filter(organization=organization).delete()

    second = rebuild_os_projections_for_organization(organization)

    assert second.read_model_counts == first_counts
    assert first_counts["agents"] == 1
    assert first_counts["tasks"] == 1
    assert first_counts["decisions"] == 1
    assert first_counts["ledger"] == 1
    assert first_counts["cost_aggregates"] == 2
