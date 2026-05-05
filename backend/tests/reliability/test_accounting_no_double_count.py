from __future__ import annotations

import time

import pytest
from django.test import override_settings

from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    CostLedgerEntry,
    Graph,
    GraphVersion,
    LLMUsage,
    ProcessedAccountingEvent,
    Run,
)

pytestmark = pytest.mark.django_db


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_duplicate_usage_callback_does_not_double_count_cost(
    signed_engine_event_post,
    user,
) -> None:
    graph = Graph.objects.create(owner=user, name="Accounting Idempotency Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(owner=user, graph_version=version, status="running")
    payload = {
        "event_id": "evt-usage-1",
        "type": "node_completed",
        "run_id": str(run.id),
        "tenant_id": str(user.default_organization_id),
        "node_id": "prompt_1",
        "node_type": "prompt",
        "attempt": 1,
        "timestamp": int(time.time() * 1000),
        "output": {
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
    second = signed_engine_event_post(payload)
    process_pending_projection_events(
        organization_id=user.default_organization_id,
        projection_names=("accounting",),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data["data"]["duplicate"] is True
    assert LLMUsage.objects.filter(run=run, node_id="prompt_1").count() == 1
    assert (
        ProcessedAccountingEvent.objects.filter(
            organization=user.default_organization,
            event_type="llm_usage",
        ).count()
        == 1
    )
    assert CostLedgerEntry.objects.filter(organization=user.default_organization).count() == 1
