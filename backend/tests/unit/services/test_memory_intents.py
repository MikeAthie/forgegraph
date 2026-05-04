from __future__ import annotations

import pytest

from application.services.memory_intents import BackendMemoryIntentService
from infrastructure.orm.models import Graph, GraphVersion, MemoryObservation, Run

pytestmark = pytest.mark.django_db


def _create_run(user) -> Run:
    graph = Graph.objects.create(owner=user, name="Backend Memory Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(owner=user, graph_version=version, status="running")


def test_summary_created_intent_creates_backend_owned_memory_observation(user) -> None:
    run = _create_run(user)

    result = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="summary_created",
        payload={
            "summary_id": "summary-1",
            "content": "The run discovered that vendor payments need approval.",
        },
        event_id="evt-summary-1",
    )

    assert result.observation_count == 1
    observation = MemoryObservation.objects.get(run_id=run.id)
    assert observation.tenant_id == user.default_organization_id
    assert observation.graph_id == run.graph_version.graph_id
    assert observation.type == "summary"
    assert observation.scope == "run"
    assert observation.topic_key == "engine-summary-summary-1"

    duplicate = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="summary_created",
        payload={
            "summary_id": "summary-1",
            "content": "The run discovered that vendor payments need approval.",
        },
        event_id="evt-summary-1",
    )

    assert duplicate.observation_count == 1
    assert MemoryObservation.objects.filter(run_id=run.id, type="summary").count() == 1


def test_memory_fact_extracted_intent_requires_structured_facts(user) -> None:
    run = _create_run(user)

    result = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload={
            "summary_id": "summary-2",
            "facts": [
                {"key": "approval threshold", "value": "Payments above threshold need review."}
            ],
        },
        event_id="evt-fact-1",
    )

    assert result.observation_count == 1
    observation = MemoryObservation.objects.get(run_id=run.id, type="fact")
    assert observation.topic_key == "engine-fact-summary-2-approval-threshold"
    assert observation.content == "Payments above threshold need review."

    with pytest.raises(ValueError, match="facts array"):
        BackendMemoryIntentService().apply_engine_memory_intent(
            run=run,
            event_type="memory_fact_extracted",
            payload={"summary_id": "summary-2", "facts": "not-a-list"},
            event_id="evt-fact-bad",
        )
