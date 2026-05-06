from __future__ import annotations

from uuid import uuid4

import pytest
from django.utils import timezone

from application.projections.dispatcher import PROJECTION_NAMES, projection_names_for_event
from application.services.domain_events import record_domain_event
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    OrganizationStateFeedEvent,
    ProcessedProjectionEvent,
    ProjectionCursor,
    Run,
    TaskLifecycleRecord,
)

pytestmark = pytest.mark.django_db


def test_observability_run_event_is_excluded_from_os_projection_cursor(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="run",
        aggregate_id=uuid4(),
        event_type="run_event.node_stream.chunk",
        idempotency_key="projection-routing-run-event",
        payload={"run_id": str(uuid4()), "chunk": "debug"},
    ).event

    result = process_pending_projection_events(organization_id=organization.id)

    assert result.events_selected == 0
    assert result.processed == 0
    assert result.noop == 0
    assert not ProcessedProjectionEvent.objects.filter(event=event).exists()
    assert not OrganizationStateFeedEvent.objects.filter(
        organization=organization,
        event_id__startswith=f"os-projection:{event.id}",
    ).exists()
    assert not ProjectionCursor.objects.filter(organization=organization).exists()


def test_task_event_routes_only_to_task_projection_and_advances_other_cursors(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="task",
        aggregate_id=uuid4(),
        event_type="task.lifecycle_transitioned",
        idempotency_key="projection-routing-task-event",
        payload={"task_lifecycle_id": str(uuid4()), "run_id": str(uuid4())},
    ).event

    result = process_pending_projection_events(organization_id=organization.id)

    assert result.processed == 1
    assert result.noop == len(PROJECTION_NAMES) - 1
    assert list(
        ProcessedProjectionEvent.objects.filter(event=event).values_list(
            "projection_name",
            flat=True,
        )
    ) == ["tasks"]
    assert set(
        ProjectionCursor.objects.filter(organization=organization).values_list(
            "projection_name",
            "last_sequence",
        )
    ) == {(name, event.sequence) for name in PROJECTION_NAMES}


def test_run_status_event_notifies_without_agent_registry_rebuild(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="run",
        aggregate_id=uuid4(),
        event_type="run.updated",
        idempotency_key="projection-routing-run-status-event",
        payload={
            "run_id": str(uuid4()),
            "status": "succeeded",
            "graph_version_id": str(uuid4()),
        },
    ).event

    result = process_pending_projection_events(organization_id=organization.id)

    assert result.processed == 0
    assert result.noop == len(PROJECTION_NAMES)
    assert not ProcessedProjectionEvent.objects.filter(event=event).exists()
    assert OrganizationStateFeedEvent.objects.filter(
        organization=organization,
        type="overview.updated",
        event_id=f"os-projection:{event.id}:overview.updated",
    ).exists()
    assert set(
        ProjectionCursor.objects.filter(organization=organization).values_list(
            "projection_name",
            "last_sequence",
        )
    ) == {(name, event.sequence) for name in PROJECTION_NAMES}


def test_node_run_event_skips_task_projection_when_lifecycle_record_exists(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(owner=user, organization=organization, name="Task Routed")
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
    TaskLifecycleRecord.objects.create(
        organization=organization,
        run=run,
        source_node_id="agent_1",
        node_type="agent",
        external_key=f"{run.id}:agent_1",
        title="Agent task",
        status="running",
        started_at=timezone.now(),
    )
    event = record_domain_event(
        organization=organization,
        aggregate_type="node_run",
        aggregate_id=uuid4(),
        event_type="node_run.updated",
        idempotency_key="projection-routing-node-run-backed-by-lifecycle",
        payload={
            "run_id": str(run.id),
            "node_id": "agent_1",
            "node_type": "agent",
            "status": "running",
        },
    ).event

    assert projection_names_for_event(event) == ("agents",)


def test_memory_event_notifies_without_projection_handler_fanout(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="memory_observation",
        aggregate_id=uuid4(),
        event_type="memory.observation_created",
        idempotency_key="projection-routing-memory-event",
        payload={"memory_observation_id": str(uuid4())},
    ).event

    result = process_pending_projection_events(organization_id=organization.id)

    assert result.processed == 0
    assert result.noop == len(PROJECTION_NAMES)
    assert not ProcessedProjectionEvent.objects.filter(event=event).exists()
    event_types = set(
        OrganizationStateFeedEvent.objects.filter(organization=organization).values_list(
            "type",
            flat=True,
        )
    )
    assert "memory.created" in event_types
