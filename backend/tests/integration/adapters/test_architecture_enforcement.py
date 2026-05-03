from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone
from rest_framework import status

from application.services.runtime_write_intents import (
    RuntimeIntentEnvelope,
    RuntimeIntentError,
    process_runtime_intent_message,
)
from application.services.task_lifecycle import dead_letter_task, transition_task_lifecycle
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    ApprovalTask,
    AuditLog,
    DecisionRecord,
    Graph,
    GraphVersion,
    Run,
    RunCheckpoint,
    RuntimeIntentOutcome,
    TaskDeadLetterRecord,
    TaskLifecycleRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _make_run(user: User | None = None, *, status_value: str = "running") -> Run:
    if user is None:
        user = User.objects.create_user(
            email=f"architecture-{uuid4().hex}@example.com",
            password="password123",
        )
        ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name=f"Architecture Graph {uuid4().hex[:8]}",
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
        status=status_value,
        dispatch_graph_json={"metadata": {"backend_attempt_id": "attempt-1"}},
        trace_id="trace-architecture",
    )


def _intent_fields(intent: RuntimeIntentEnvelope) -> dict[str, str]:
    return {
        "intent": json.dumps(
            {
                "intent_id": str(intent.intent_id),
                "intent_type": intent.intent_type,
                "run_id": str(intent.run_id),
                "attempt_id": intent.attempt_id,
                "trace_id": intent.trace_id,
                "timestamp": intent.timestamp.isoformat(),
                "payload": intent.payload,
            }
        )
    }


def test_state_mutation_runtime_intent_requires_explicit_idempotency_key() -> None:
    run = _make_run()
    intent = RuntimeIntentEnvelope(
        intent_id=uuid4(),
        intent_type="task_lifecycle_transition",
        run_id=run.id,
        attempt_id="attempt-1",
        trace_id="trace-architecture",
        timestamp=timezone.now(),
        payload={
            "node_id": "task_1",
            "node_type": "agent",
            "status": "running",
            "attempt_number": 1,
        },
    )

    with pytest.raises(RuntimeIntentError, match="idempotency_key"):
        process_runtime_intent_message(
            stream_message_id="1700000100000-0",
            fields=_intent_fields(intent),
        )

    outcome = RuntimeIntentOutcome.objects.get(intent_id=intent.intent_id)
    assert outcome.outcome == "invalid"
    assert "idempotency_key" in outcome.reason
    assert TaskLifecycleRecord.objects.filter(run=run, source_node_id="task_1").first() is None


def test_duplicate_event_aggregation_does_not_mutate_state_twice() -> None:
    run = _make_run()
    intent_id = uuid4()
    payload = {
        "node_id": "task_1",
        "node_type": "agent",
        "status": "running",
        "attempt_number": 1,
        "idempotency_key": "architecture:task-running",
    }
    intent = RuntimeIntentEnvelope(
        intent_id=intent_id,
        intent_type="task_lifecycle_transition",
        run_id=run.id,
        attempt_id="attempt-1",
        trace_id="trace-architecture",
        timestamp=timezone.now(),
        payload=payload,
    )

    first = process_runtime_intent_message(
        stream_message_id="1700000100001-0",
        fields=_intent_fields(intent),
    )
    second = process_runtime_intent_message(
        stream_message_id="1700000100002-0",
        fields=_intent_fields(intent),
    )

    assert first == "processed"
    assert second == "duplicate"
    assert TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1").status == "running"
    assert run.task_lifecycle_events.filter(idempotency_key="architecture:task-running").count() == 1


def test_stale_runtime_attempt_is_ignored_without_task_state_mutation() -> None:
    run = _make_run()
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="architecture:attempt-1-running",
        reason="current attempt started",
    )
    intent = RuntimeIntentEnvelope(
        intent_id=uuid4(),
        intent_type="task_lifecycle_transition",
        run_id=run.id,
        attempt_id="stale-attempt",
        trace_id="trace-architecture",
        timestamp=timezone.now(),
        payload={
            "node_id": "task_1",
            "node_type": "agent",
            "status": "completed",
            "attempt_number": 1,
            "idempotency_key": "architecture:stale-complete",
        },
    )

    result = process_runtime_intent_message(
        stream_message_id="1700000100003-0",
        fields=_intent_fields(intent),
    )

    assert result == "ignored"
    assert TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1").status == "running"
    outcome = RuntimeIntentOutcome.objects.get(intent_id=intent.intent_id)
    assert outcome.outcome == "ignored"
    assert not run.task_lifecycle_events.filter(idempotency_key="architecture:stale-complete").exists()


def test_decision_resolution_requires_immutable_audit_record_before_dispatch(
    authenticated_client,
    mock_engine_client,
    user,
) -> None:
    run = _make_run(user, status_value="paused")
    run.paused_node_id = "task_1"
    run.save(update_fields=["paused_node_id"])
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="task_1",
        assignee=user,
        status="pending",
        payload={"prompt_message": "Approve architecture test."},
    )
    mock_engine_client.resume_run_error = "synthetic dispatch failure"

    response = authenticated_client.post(
        f"/api/runs/{run.id}/resume",
        {"node_id": "task_1", "input_json": {"approved": True, "feedback": "Proceed"}},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    approval.refresh_from_db()
    assert approval.status == "approved"
    assert DecisionRecord.objects.filter(source_approval_task=approval, status="approved").exists()
    assert AuditLog.objects.filter(
        action="approval.resolved",
        resource_type="approval",
        resource_id=str(approval.id),
    ).exists()


def test_dead_letter_message_requires_diagnostic_context() -> None:
    run = _make_run()
    transition = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="architecture:dead-letter-running",
        reason="node started",
    )

    dead_letter_task(
        task=transition.lifecycle_task,
        reason="retry exhausted",
        last_error="provider timed out after bounded retries",
        attempt_count=3,
        recovery_options=["inspect_run", "replay_intent", "force_fail_run"],
        idempotency_key="architecture:dead-letter",
        source="test",
        intent_id=uuid4(),
        stream_message_id="1700000100004-0",
    )

    dead_letter = TaskDeadLetterRecord.objects.get(lifecycle_task=transition.lifecycle_task)
    assert dead_letter.reason
    assert dead_letter.attempt_count == 3
    assert dead_letter.last_error
    assert "inspect_run" in dead_letter.recovery_options
    assert dead_letter.stream_message_id == "1700000100004-0"
    assert dead_letter.intent_id is not None


def test_operator_access_remains_org_scoped(authenticated_client, user) -> None:
    other_user = User.objects.create_user(
        email=f"architecture-other-{uuid4().hex}@example.com",
        password="password123",
    )
    ensure_default_organization(other_user)
    other_run = _make_run(other_user)

    response = authenticated_client.get(f"/api/operator/runs/{other_run.id}/state")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=True)
def test_checkpoint_is_not_visible_before_transaction_commit(user) -> None:
    if connection.vendor == "sqlite":
        pytest.skip("SQLite does not provide the separate-connection visibility proof used here.")

    run = _make_run(user)
    checkpoint_pk = str(run.id)

    with transaction.atomic():
        RunCheckpoint.objects.create(
            run=run,
            node_id="task_1",
            step_index=1,
            state_json={"state": "uncommitted"},
            completed_nodes=[],
            skipped_nodes=[],
            graph_json={},
        )
        separate = connections["default"].copy()
        try:
            with separate.cursor() as cursor:
                cursor.execute("select count(*) from run_checkpoints where run_id = %s", [checkpoint_pk])
                assert cursor.fetchone()[0] == 0
        finally:
            separate.close()

    separate = connections["default"].copy()
    try:
        with separate.cursor() as cursor:
            cursor.execute("select count(*) from run_checkpoints where run_id = %s", [checkpoint_pk])
            assert cursor.fetchone()[0] == 1
    finally:
        separate.close()
