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


def test_memory_event_retry_returns_same_observation_without_duplicate_drift(user) -> None:
    graph = Graph.objects.create(owner=user, name="Memory Idempotency Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(owner=user, graph_version=version, status="running")
    payload = {
        "summary_id": "summary-1",
        "facts": [{"key": "approval threshold", "value": "Payments need approval."}],
    }

    first = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-memory-fact-1",
    )
    second = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-memory-fact-1",
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert [observation.id for observation in second.observations] == [
        observation.id for observation in first.observations
    ]
    observation = MemoryObservation.objects.get(run_id=run.id, type="fact")
    assert observation.duplicate_count == 0
    assert observation.revision_count == 1
    assert (
        ProcessedMemoryEvent.objects.filter(
            organization_id=user.default_organization_id,
            event_id="evt-memory-fact-1",
        ).count()
        == 1
    )
