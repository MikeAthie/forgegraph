from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from application.services.os_projections import (
    organization_state_summary,
    refresh_phase1_projections,
    sync_accounting_for_organization,
    sync_decision_records_for_organization,
)
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


def _create_run(user, *, status: str = "running") -> Run:
    graph = Graph.objects.create(owner=user, name="Projection Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status=status,
        started_at=timezone.now(),
    )


def _normalized_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    normalized.pop("generated_at", None)
    return normalized


def test_sync_decision_records_materializes_approval_state_idempotently(user) -> None:
    organization = user.default_organization
    assert organization is not None
    run = _create_run(user, status="paused")
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="human_gate_1",
        assignee=user,
        status="pending",
        payload={"prompt_message": "Approve order", "required_fields": ["reason"]},
    )

    decisions = sync_decision_records_for_organization(organization)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.source_approval_task == approval
    assert decision.status == "pending"
    assert decision.decision_type == "human_approval"
    assert decision.context_json == approval.payload
    assert DecisionRecord.objects.filter(organization=organization).count() == 1

    approval.status = "approved"
    approval.result = {"approved": True, "reason": "looks good"}
    approval.resolved_at = timezone.now()
    approval.save(update_fields=["status", "result", "resolved_at"])

    decisions = sync_decision_records_for_organization(organization)

    assert len(decisions) == 1
    decision.refresh_from_db()
    assert decision.status == "approved"
    assert decision.resolution_json == approval.result
    assert DecisionRecord.objects.filter(organization=organization).count() == 1


def test_sync_accounting_projects_usage_into_ledger_and_aggregates_idempotently(user) -> None:
    organization = user.default_organization
    assert organization is not None
    run = _create_run(user)
    LLMUsage.objects.create(
        tenant_id=organization.id,
        run=run,
        node_id="prompt_1",
        provider="openai",
        model="gpt-4.1-mini",
        prompt_tokens=240,
        completion_tokens=60,
        total_tokens=300,
        cost_usd=Decimal("1.500000"),
    )

    ledger = sync_accounting_for_organization(organization)

    assert len(ledger) == 1
    entry = ledger[0]
    assert entry.total_cost_usd == Decimal("1.500000")
    assert entry.quantity == Decimal("300")
    assert CostLedgerEntry.objects.filter(organization=organization).count() == 1
    assert CostAggregate.objects.filter(organization=organization).count() == 2

    sync_accounting_for_organization(organization)

    assert CostLedgerEntry.objects.filter(organization=organization).count() == 1
    daily_aggregate = CostAggregate.objects.get(organization=organization, grain="daily")
    hourly_aggregate = CostAggregate.objects.get(organization=organization, grain="hourly")
    assert daily_aggregate.total_cost_usd == Decimal("1.500000")
    assert hourly_aggregate.total_cost_usd == Decimal("1.500000")
    assert daily_aggregate.entry_count == 1
    assert hourly_aggregate.entry_count == 1


def test_refresh_phase1_projections_rebuilds_control_plane_state_from_materialized_events(
    user,
) -> None:
    organization = user.default_organization
    assert organization is not None

    graph = Graph.objects.create(owner=user, name="Projection Replay Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [
                {"id": "ops_agent", "type": "agent", "name": "Ops Agent"},
                {"id": "output", "type": "output", "name": "Output"},
            ],
            "edges": [{"id": "e1", "from": "ops_agent", "to": "output"}],
        },
    )
    run = Run.objects.create(
        owner=user,
        graph_version=version,
        status="paused",
        started_at=timezone.now(),
        paused_node_id="ops_agent",
        pause_state_json={"snapshot": "state"},
    )
    node_run = NodeRun.objects.create(
        run=run,
        node_id="ops_agent",
        node_type="agent",
        status="waiting",
        attempt=1,
        started_at=timezone.now(),
        input_json={"task": "review payment"},
        output_json={"summary": "Waiting on approval"},
    )
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="ops_agent",
        assignee=user,
        status="pending",
        payload={"prompt_message": "Approve vendor payment", "required_fields": ["reason"]},
    )
    usage = LLMUsage.objects.create(
        tenant_id=organization.id,
        run=run,
        node_id="ops_agent",
        provider="openai",
        model="gpt-4.1-mini",
        prompt_tokens=120,
        completion_tokens=30,
        total_tokens=150,
        cost_usd=Decimal("0.750000"),
    )
    observation = MemoryObservation.objects.create(
        tenant_id=organization.id,
        graph_id=graph.id,
        run_id=run.id,
        agent_id=None,
        type="fact",
        title="Vendor risk threshold",
        content="Vendor payments above threshold require approval.",
        scope="run",
        topic_key="vendor-approval-threshold",
    )

    refresh_phase1_projections(user)
    first_summary = _normalized_summary(organization_state_summary(organization))

    assert AgentRegistryEntry.objects.filter(organization=organization).count() == 1
    assert TaskRecord.objects.filter(organization=organization).count() == 1
    assert DecisionRecord.objects.filter(organization=organization).count() == 1
    assert CostLedgerEntry.objects.filter(organization=organization).count() == 1
    assert CostAggregate.objects.filter(organization=organization).count() == 2

    AgentRegistryEntry.objects.filter(organization=organization).delete()
    TaskRecord.objects.filter(organization=organization).delete()
    DecisionRecord.objects.filter(organization=organization).delete()
    CostLedgerEntry.objects.filter(organization=organization).delete()
    CostAggregate.objects.filter(organization=organization).delete()

    refresh_phase1_projections(user)
    second_summary = _normalized_summary(organization_state_summary(organization))

    assert second_summary["summary"] == first_summary["summary"]
    assert second_summary["memory"] == first_summary["memory"]
    assert second_summary["policy"] == first_summary["policy"]
    assert [agent["display_name"] for agent in second_summary["active_agents"]] == [
        agent["display_name"] for agent in first_summary["active_agents"]
    ]
    assert [task["source_node_id"] for task in second_summary["active_tasks"]] == [
        task["source_node_id"] for task in first_summary["active_tasks"]
    ]
    assert [decision["decision_type"] for decision in second_summary["pending_decisions"]] == [
        decision["decision_type"] for decision in first_summary["pending_decisions"]
    ]
    assert (
        second_summary["accounting"]["total_cost_usd"]
        == first_summary["accounting"]["total_cost_usd"]
    )
    assert (
        second_summary["accounting"]["cost_by_type"] == first_summary["accounting"]["cost_by_type"]
    )
    rebuilt_agent = AgentRegistryEntry.objects.get(organization=organization)
    rebuilt_task = TaskRecord.objects.get(organization=organization)
    rebuilt_decision = DecisionRecord.objects.get(organization=organization)
    rebuilt_ledger = CostLedgerEntry.objects.get(organization=organization)

    assert rebuilt_agent.source_workflow == graph
    assert rebuilt_task.execution == run
    assert rebuilt_task.current_step == node_run
    assert rebuilt_decision.source_approval_task == approval
    assert rebuilt_ledger.execution == run
    assert rebuilt_ledger.total_cost_usd == usage.cost_usd
    assert MemoryObservation.objects.filter(id=observation.id, tenant_id=organization.id).exists()
