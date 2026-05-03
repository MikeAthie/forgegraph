from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.tenancy import ensure_default_organization
from application.services.task_lifecycle import record_retry_operation, transition_task_lifecycle
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    RetryOperation,
    Run,
    TaskDeadLetterRecord,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _make_run() -> Run:
    user = User.objects.create_user(
        email=f"retry-ops-{uuid4().hex}@example.com",
        password="password123",
    )
    ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Retry Operation Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "task_1", "type": "agent", "name": "Research"}],
            "edges": [],
        },
    )
    return Run.objects.create(
        owner=user,
        organization=user.default_organization,
        graph_version=version,
        status="running",
        dispatch_graph_json={"metadata": {"backend_attempt_id": "attempt-1"}},
    )


def test_retry_attempt_requires_parent_attempt() -> None:
    run = _make_run()
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="engine",
        idempotency_key="task:test:retry-parent-attempt-1",
        reason="node started",
    )

    result = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="retry_scheduled",
        attempt_number=3,
        source="engine",
        idempotency_key="task:test:retry-without-parent",
        reason="retry without parent",
    )

    task = TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1")
    assert result.outcome == "invalid"
    assert task.status == "running"
    assert TaskLifecycleEvent.objects.get(idempotency_key="task:test:retry-without-parent").outcome == "invalid"


def test_retry_exhaustion_creates_dead_letter_with_diagnostics() -> None:
    run = _make_run()
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="engine",
        idempotency_key="task:test:running",
        reason="node started",
    )

    retry = record_retry_operation(
        run=run,
        operation_type="llm_call",
        idempotency_key="retry:test:exhausted",
        attempt_number=1,
        max_attempts=1,
        retry_delay_ms=0,
        retry_reason="LLM queue saturated",
        last_error="provider timeout",
        owning_component="engine",
        retry_class="llm_backpressure",
        terminal_fallback="dead_letter",
        node_id="task_1",
        node_type="agent",
    )

    retry.refresh_from_db()
    task = TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1")
    dead_letter = TaskDeadLetterRecord.objects.get(lifecycle_task=task)

    assert retry.status == "dead_lettered"
    assert task.status == "dead_lettered"
    assert dead_letter.reason == "LLM queue saturated"
    assert dead_letter.attempt_count == 1
    assert dead_letter.last_error == "provider timeout"
    assert "replay_intent" in dead_letter.recovery_options


def test_duplicate_retry_operation_returns_prior_record() -> None:
    run = _make_run()
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="engine",
        idempotency_key="task:test:running-duplicate-retry",
        reason="node started",
    )

    first = record_retry_operation(
        run=run,
        operation_type="transport",
        idempotency_key="retry:test:duplicate",
        attempt_number=1,
        max_attempts=3,
        retry_delay_ms=250,
        retry_reason="HTTP timeout",
        last_error="timeout",
        owning_component="engine",
        retry_class="transport",
        terminal_fallback="fail_run",
        node_id="task_1",
        node_type="agent",
    )
    second = record_retry_operation(
        run=run,
        operation_type="transport",
        idempotency_key="retry:test:duplicate",
        attempt_number=1,
        max_attempts=3,
        retry_delay_ms=250,
        retry_reason="HTTP timeout",
        last_error="timeout",
        owning_component="engine",
        retry_class="transport",
        terminal_fallback="fail_run",
        node_id="task_1",
        node_type="agent",
    )

    assert second.id == first.id
    assert RetryOperation.objects.filter(idempotency_key="retry:test:duplicate").count() == 1
