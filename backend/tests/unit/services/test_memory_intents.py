from __future__ import annotations

from uuid import uuid4

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


def test_canonical_memory_fact_event_records_provenance_and_fact_hash(user) -> None:
    run = _create_run(user)

    result = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory.fact_extracted",
        payload={
            "tenant_id": str(user.default_organization_id),
            "organization_id": str(user.default_organization_id),
            "run_id": str(run.id),
            "fact": "Customer prefers concise approvals.",
            "source_span": "turn-12",
            "confidence": 0.91,
            "ttl_seconds": 86400,
            "cost_usd": "0.010000",
            "total_tokens": 42,
        },
        event_id="evt-canonical-fact",
    )

    assert result.observation_count == 1
    observation = MemoryObservation.objects.get(run_id=run.id, type="fact")
    assert observation.source_event_id == "evt-canonical-fact"
    assert observation.source_event_type == "memory_fact_extracted"
    assert len(observation.fact_hash) == 64
    assert observation.provenance_json == {
        "source": "engine_memory_intent",
        "backend_owner": "memory_service",
        "event_id": "evt-canonical-fact",
        "event_type": "memory_fact_extracted",
        "memory_kind": "fact",
        "summary_id": "evt-canonical-fact",
        "fact_key": "fact",
        "source_span": "turn-12",
        "confidence": 0.91,
        "fact_hash": observation.fact_hash,
    }
    assert observation.cost_metadata_json == {
        "cost_usd": "0.010000",
        "currency": "USD",
        "total_tokens": 42,
    }
    assert observation.retention_policy_json == {
        "source": "backend_memory_service",
        "ttl_seconds": 86400,
    }


def test_duplicate_fact_hash_does_not_create_second_observation(user) -> None:
    run = _create_run(user)
    payload = {
        "summary_id": "summary-dup",
        "facts": [{"key": "owner", "value": "Ava owns approvals."}],
    }

    first = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-fact-a",
    )
    second = BackendMemoryIntentService().apply_engine_memory_intent(
        run=run,
        event_type="memory_fact_extracted",
        payload=payload,
        event_id="evt-fact-b",
    )

    assert first.observations[0].id == second.observations[0].id
    observation = MemoryObservation.objects.get(id=first.observations[0].id)
    assert observation.duplicate_count == 1
    assert MemoryObservation.objects.filter(run_id=run.id, type="fact").count() == 1


def test_memory_intent_rejects_cross_tenant_payload(user) -> None:
    run = _create_run(user)

    with pytest.raises(ValueError, match="tenant_id does not match"):
        BackendMemoryIntentService().apply_engine_memory_intent(
            run=run,
            event_type="memory.fact_extracted",
            payload={
                "tenant_id": str(uuid4()),
                "fact": "Should not cross tenants.",
            },
            event_id="evt-cross-tenant",
        )
