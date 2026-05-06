from __future__ import annotations

import pytest
from django.utils import timezone

from application.projections import agents as agent_projection
from application.services.domain_events import record_domain_event, record_node_run_domain_event
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import AgentRegistryEntry, Graph, GraphVersion, NodeRun, Run

pytestmark = pytest.mark.django_db


def test_node_run_projection_updates_existing_agent_entry_without_graph_rebuild(
    user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Agent Projection")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [
                {"id": "agent_1", "type": "agent", "name": "Primary Agent"},
                {"id": "agent_2", "type": "agent", "name": "Secondary Agent"},
            ],
            "edges": [],
        },
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )
    process_pending_projection_events(organization_id=organization.id)

    assert AgentRegistryEntry.objects.filter(organization=organization).count() == 2

    def fail_graph_rebuild(graph_version_id: str) -> None:
        raise AssertionError(f"unexpected graph-wide agent projection for {graph_version_id}")

    monkeypatch.setattr(agent_projection, "_project_graph_version", fail_graph_rebuild)

    node_run = NodeRun.objects.create(
        run=run,
        node_id="agent_1",
        node_type="agent",
        status="running",
        started_at=timezone.now(),
    )
    record_node_run_domain_event(node_run, created=True)

    process_pending_projection_events(organization_id=organization.id)

    primary = AgentRegistryEntry.objects.get(
        organization=organization,
        source_workflow=graph,
        source_node_id="agent_1",
    )
    secondary = AgentRegistryEntry.objects.get(
        organization=organization,
        source_workflow=graph,
        source_node_id="agent_2",
    )
    assert primary.status == "active"
    assert primary.last_execution == run
    assert primary.last_seen_at == node_run.started_at
    assert secondary.last_execution is None
    assert AgentRegistryEntry.objects.filter(organization=organization).count() == 2


def test_node_run_projection_creates_single_missing_agent_entry_without_graph_rebuild(
    user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Missing Agent")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [
                {"id": "agent_1", "type": "agent", "name": "Primary Agent"},
                {"id": "agent_2", "type": "agent", "name": "Secondary Agent"},
            ],
            "edges": [],
        },
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )
    node_run = NodeRun.objects.create(
        run=run,
        node_id="agent_1",
        node_type="agent",
        status="running",
        started_at=timezone.now(),
    )
    event = record_domain_event(
        organization=organization,
        aggregate_type="node_run",
        aggregate_id=node_run.id,
        event_type="node_run.updated",
        idempotency_key=f"agent-projection-missing-entry:{node_run.id}",
        payload={
            "node_run_id": str(node_run.id),
            "run_id": str(run.id),
            "node_id": "agent_1",
            "node_type": "agent",
            "status": "running",
        },
    ).event

    def fail_graph_rebuild(graph_version_id: str) -> None:
        raise AssertionError(f"unexpected graph-wide agent projection for {graph_version_id}")

    monkeypatch.setattr(agent_projection, "_project_graph_version", fail_graph_rebuild)

    agent_projection.apply(event)

    entry = AgentRegistryEntry.objects.get(
        organization=organization,
        source_workflow=graph,
        source_node_id="agent_1",
    )
    assert entry.display_name == "Primary Agent"
    assert entry.status == "active"
    assert entry.last_execution == run
    assert AgentRegistryEntry.objects.filter(organization=organization).count() == 1
