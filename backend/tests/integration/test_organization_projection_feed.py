from __future__ import annotations

import pytest
from django.utils import timezone

from application.services.task_lifecycle import transition_task_lifecycle
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    OrganizationStateFeedEvent,
    Run,
)

pytestmark = pytest.mark.django_db


def test_projection_worker_emits_organization_state_notifications(user) -> None:
    organization = user.default_organization
    graph = Graph.objects.create(owner=user, organization=organization, name="Live Command Ops")
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

    event_types = set(
        OrganizationStateFeedEvent.objects.filter(organization=organization).values_list(
            "type",
            flat=True,
        )
    )
    assert "task.updated" in event_types
    assert "overview.updated" in event_types


def test_organization_state_feed_is_notification_only_for_overview(user) -> None:
    organization = user.default_organization
    record = OrganizationStateFeedEvent.objects.create(
        organization=organization,
        event_id="notification-only",
        state_version=1,
        type="overview.updated",
        resource_type="overview",
        resource_id=str(organization.id),
        requires_refetch=True,
        message={
            "type": "overview.updated",
            "event_type": "overview.updated",
            "event_id": "notification-only",
            "organization_id": str(organization.id),
            "state_version": 1,
            "requires_refetch": True,
            "resource": {"type": "overview", "id": str(organization.id)},
            "occurred_at": timezone.now().isoformat(),
            "payload": {"summary": {"active_task_count": 9999}},
        },
    )

    assert record.message["payload"]["summary"]["active_task_count"] == 9999
    assert not hasattr(record, "active_task_count")
