from __future__ import annotations

import pytest

from application.services.state_feed import record_state_feed_event, replay_state_feed_events
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, Run, StateFeedEvent, User

pytestmark = pytest.mark.django_db


def _create_run(user: User) -> Run:
    graph = Graph.objects.create(owner=user, name="State Feed Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(owner=user, graph_version=version, status="running")


def test_record_state_feed_event_assigns_monotonic_versions_and_replays(user) -> None:
    run = _create_run(user)

    first = record_state_feed_event(
        run=run,
        message={
            "type": "run.updated",
            "run_id": str(run.id),
            "event_id": "evt-1",
            "run": {"id": str(run.id), "status": "running"},
        },
    )
    second = record_state_feed_event(
        run=run,
        message={
            "type": "run.updated",
            "run_id": str(run.id),
            "event_id": "evt-2",
            "run": {"id": str(run.id), "status": "succeeded"},
        },
    )

    assert first["state_version"] == 1
    assert second["state_version"] == 2
    assert first["tenant_id"] == str(user.default_organization_id)
    assert StateFeedEvent.objects.filter(run=run).count() == 2

    replay = replay_state_feed_events(
        run_id=str(run.id),
        organization_id=str(user.default_organization_id),
        after_state_version=1,
        event_types={"run_completed"},
        event_level="minimal",
    )

    assert replay.full_resync_required is False
    assert replay.latest_state_version == 2
    assert [event["event_id"] for event in replay.events] == ["evt-2"]
    assert replay.events[0]["type"] == "run_completed"


def test_replay_state_feed_requires_tenant_visibility(user) -> None:
    other = User.objects.create_user(email="state-feed-other@example.com", password="pw")
    ensure_default_organization(other)
    other_run = _create_run(other)

    replay = replay_state_feed_events(
        run_id=str(other_run.id),
        organization_id=str(user.default_organization_id),
        after_state_version=1,
    )

    assert replay.full_resync_required is True
    assert replay.reason == "run_not_visible"
