from __future__ import annotations

import pytest

from application.services.memory_intents import BackendMemoryIntentService
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    MemoryObservation,
    ProcessedMemoryEvent,
    Run,
)

pytestmark = pytest.mark.django_db


def test_memory_write_idempotency_returns_same_fact_without_counter_drift(user) -> None:
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Memory Write Idempotency Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=user.default_organization,
        graph_version=version,
        status="running",
    )
    payload = {
        "summary_id": "summary-1",
        "facts": [{"key": "handoff", "value": "Human handoff requires backend approval."}],
    }

    first = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-memory-write-1",
    )
    second = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-memory-write-1",
    )

    observation = MemoryObservation.objects.get(run_id=run.id, type="fact")
    assert second.duplicate is True
    assert [item.id for item in second.observations] == [item.id for item in first.observations]
    assert observation.duplicate_count == 0
    assert observation.revision_count == 1
    assert (
        ProcessedMemoryEvent.objects.filter(
            organization=user.default_organization,
            event_id="evt-memory-write-1",
        ).count()
        == 1
    )
