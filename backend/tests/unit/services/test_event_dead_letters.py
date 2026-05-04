from __future__ import annotations

import pytest

from application.services.event_dead_letters import record_event_dead_letter
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import EventDeadLetterRecord, Graph, GraphVersion, Run, User

pytestmark = pytest.mark.django_db


def _make_run(user: User) -> Run:
    ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Dead Letter Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    return Run.objects.create(
        owner=user,
        organization=user.default_organization,
        graph_version=version,
        status="running",
    )


def test_record_event_dead_letter_dedupes_by_backend_event_id(user: User) -> None:
    run = _make_run(user)

    first = record_event_dead_letter(
        source="engine_callback",
        run=run,
        organization=run.organization,
        event_id="evt-1",
        event_type="run_completed",
        reason="run state ordering conflict",
        payload={"event_id": "evt-1", "api_key": "secret"},
    )
    second = record_event_dead_letter(
        source="engine_callback",
        run=run,
        organization=run.organization,
        event_id="evt-1",
        event_type="run_completed",
        reason="run state ordering conflict",
        payload={"event_id": "evt-1", "api_key": "updated-secret"},
    )

    assert second.id == first.id
    assert second.retry_count == 2
    assert EventDeadLetterRecord.objects.filter(run=run, event_id="evt-1").count() == 1
    assert second.payload["api_key"] == "***REDACTED***"
