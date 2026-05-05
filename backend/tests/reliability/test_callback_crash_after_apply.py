from __future__ import annotations

import time

import pytest
from django.test import override_settings

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    MemoryObservation,
    ProcessedMemoryEvent,
    Run,
    RunEvent,
)

pytestmark = pytest.mark.django_db


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_memory_callback_retry_after_memory_apply_before_event_ack_does_not_drift(
    signed_engine_event_post,
    user,
) -> None:
    graph = Graph.objects.create(owner=user, name="Callback Memory Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(owner=user, graph_version=version, status="running")
    payload = {
        "event_id": "evt-memory-crash-before-ack",
        "idempotency_key": "evt-memory-crash-before-ack",
        "type": "memory_fact_extracted",
        "run_id": str(run.id),
        "tenant_id": str(user.default_organization_id),
        "timestamp": int(time.time() * 1000),
        "output": {
            "summary_id": "summary-crash",
            "facts": [{"key": "customer", "value": "Customer prefers concise approvals."}],
        },
    }

    first = signed_engine_event_post(payload)
    assert first.status_code == 200
    assert MemoryObservation.objects.filter(run_id=run.id, type="fact").count() == 1
    assert (
        ProcessedMemoryEvent.objects.filter(
            organization_id=user.default_organization_id,
            event_id="evt-memory-crash-before-ack",
        ).count()
        == 1
    )

    RunEvent.objects.filter(run=run, external_id="evt-memory-crash-before-ack").delete()

    second = signed_engine_event_post(payload)
    assert second.status_code == 200
    assert MemoryObservation.objects.filter(run_id=run.id, type="fact").count() == 1
    observation = MemoryObservation.objects.get(run_id=run.id, type="fact")
    assert observation.duplicate_count == 0
    assert observation.revision_count == 1
    assert RunEvent.objects.filter(run=run, external_id="evt-memory-crash-before-ack").count() == 1
