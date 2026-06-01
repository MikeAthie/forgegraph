from __future__ import annotations

import time

import pytest
from django.test import override_settings

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    LLMUsage,
    MemoryObservation,
    NodeRun,
    ProcessedAccountingEvent,
    ProcessedMemoryEvent,
    Run,
    RunEvent,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
)
from tests.helpers.idempotency import assert_queryset_count

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


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_node_completed_retry_after_apply_before_event_ack_does_not_duplicate_state(
    signed_engine_event_post,
    user,
) -> None:
    graph = Graph.objects.create(owner=user, name="Callback Node Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [{"id": "prompt_1", "type": "prompt"}], "edges": []},
    )
    run = Run.objects.create(owner=user, graph_version=version, status="running")
    payload = {
        "event_id": "evt-node-crash-before-ack",
        "idempotency_key": "evt-node-crash-before-ack",
        "type": "node_completed",
        "run_id": str(run.id),
        "tenant_id": str(user.default_organization_id),
        "node_id": "prompt_1",
        "node_type": "prompt",
        "attempt": 1,
        "timestamp": int(time.time() * 1000),
        "output": {
            "answer": "ok",
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 25,
                "total_tokens": 75,
            },
        },
    }

    first = signed_engine_event_post(payload)
    assert first.status_code == 200
    assert_queryset_count(NodeRun.objects.filter(run=run, node_id="prompt_1"), 1, label="node run")
    assert_queryset_count(LLMUsage.objects.filter(run=run, node_id="prompt_1"), 1, label="usage")
    assert_queryset_count(
        TaskLifecycleRecord.objects.filter(run=run, source_node_id="prompt_1"),
        1,
        label="task lifecycle",
    )
    assert_queryset_count(
        TaskLifecycleEvent.objects.filter(
            idempotency_key="task:evt-node-crash-before-ack:prompt_1:succeeded:1"
        ),
        1,
        label="task lifecycle event",
    )

    RunEvent.objects.filter(run=run, external_id="evt-node-crash-before-ack").delete()

    second = signed_engine_event_post(payload)
    assert second.status_code == 200
    assert_queryset_count(NodeRun.objects.filter(run=run, node_id="prompt_1"), 1, label="node run")
    assert_queryset_count(LLMUsage.objects.filter(run=run, node_id="prompt_1"), 1, label="usage")
    assert_queryset_count(
        ProcessedAccountingEvent.objects.filter(
            organization=user.default_organization,
            event_type="llm_usage",
        ),
        1,
        label="processed accounting event",
    )
    assert_queryset_count(
        TaskLifecycleRecord.objects.filter(run=run, source_node_id="prompt_1"),
        1,
        label="task lifecycle",
    )
    assert_queryset_count(
        TaskLifecycleEvent.objects.filter(
            idempotency_key="task:evt-node-crash-before-ack:prompt_1:succeeded:1"
        ),
        1,
        label="task lifecycle event",
    )
    assert_queryset_count(
        RunEvent.objects.filter(run=run, external_id="evt-node-crash-before-ack"),
        1,
        label="run event after retry",
    )
