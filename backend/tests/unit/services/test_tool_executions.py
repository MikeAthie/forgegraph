from __future__ import annotations

import json
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.runtime_write_intents import process_runtime_intent_message
from application.services.tool_executions import (
    ToolExecutionDispatchBlocked,
    backend_attempt_id_for_run,
    prepare_tool_executions_for_dispatch,
)
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    ProcessedRuntimeIntent,
    Run,
    ToolExecution,
)

pytestmark = pytest.mark.django_db


def _make_run(user, *, status: str = "pending") -> Run:
    graph = Graph.objects.create(owner=user, name="Tool Execution Correctness Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(owner=user, graph_version=version, status=status)


def _tool_graph(*, node_id: str = "tool_1") -> dict[str, object]:
    return {
        "nodes": [
            {
                "id": node_id,
                "type": "tool",
                "config": {
                    "tool": "email.send",
                    "version": "1.0.0",
                    "input": {"to": "user@example.com"},
                },
            },
            {"id": "out", "type": "output", "config": {}},
        ],
        "edges": [{"id": "e1", "from": node_id, "to": "out"}],
        "metadata": {
            "tool_resolution": {
                "pinned_tools": [
                    {
                        "name": "email.send",
                        "version": "1.0.0",
                        "side_effects": {"type": "external", "idempotent": True},
                    }
                ]
            }
        },
    }


def _intent_fields(*, run: Run, intent_type: str, attempt_id: str, payload: dict[str, object]):
    return {
        "intent": json.dumps(
            {
                "intent_id": str(uuid4()),
                "intent_type": intent_type,
                "run_id": str(run.id),
                "attempt_id": attempt_id,
                "trace_id": "trace-tool-execution",
                "timestamp": timezone.now().isoformat(),
                "payload": payload,
            }
        )
    }


def test_prepare_tool_executions_creates_record_and_dispatch_identity(user) -> None:
    run = _make_run(user)

    prepared = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())

    execution = ToolExecution.objects.get(run=run, node_id="tool_1")
    config = prepared["nodes"][0]["config"]

    assert execution.status == "planned"
    assert execution.side_effect_class == "idempotent"
    assert config["tool_execution_id"] == str(execution.id)
    assert config["idempotency_key"] == execution.idempotency_key
    assert prepared["metadata"]["backend_attempt_id"] == backend_attempt_id_for_run(run)


def test_idempotency_key_is_stable_across_dispatch_retries(user) -> None:
    run = _make_run(user)

    first = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())
    second = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())

    first_config = first["nodes"][0]["config"]
    second_config = second["nodes"][0]["config"]

    assert first_config["tool_execution_id"] == second_config["tool_execution_id"]
    assert first_config["idempotency_key"] == second_config["idempotency_key"]
    assert ToolExecution.objects.filter(run=run).count() == 1


def test_retry_is_blocked_for_failed_unsafe_tool_execution(user) -> None:
    run = _make_run(user)
    prepared = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())
    execution = ToolExecution.objects.get(run=run)
    execution.side_effect_class = "non_idempotent"
    execution.status = "failed"
    execution.save(update_fields=["side_effect_class", "status", "updated_at"])

    with pytest.raises(ToolExecutionDispatchBlocked):
        prepare_tool_executions_for_dispatch(run=run, graph_json=prepared)


def test_succeeded_tool_execution_is_not_reexecuted(user) -> None:
    run = _make_run(user)
    prepared = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())
    execution = ToolExecution.objects.get(run=run)
    execution.status = "succeeded"
    execution.save(update_fields=["status", "updated_at"])

    redispatched = prepare_tool_executions_for_dispatch(run=run, graph_json=prepared)

    assert redispatched["nodes"][0]["config"]["skip_tool_execution"] is True


def test_tool_execution_ambiguous_intent_marks_execution_and_fails_run(user) -> None:
    run = _make_run(user, status="running")
    prepared = prepare_tool_executions_for_dispatch(run=run, graph_json=_tool_graph())
    execution = ToolExecution.objects.get(run=run)
    attempt_id = prepared["metadata"]["backend_attempt_id"]

    result = process_runtime_intent_message(
        stream_message_id="1-0",
        fields=_intent_fields(
            run=run,
            intent_type="tool_execution_ambiguous",
            attempt_id=attempt_id,
            payload={
                "tool_execution_id": str(execution.id),
                "reason": "http_request_outcome_unknown",
                "error_class": "*domain.AmbiguousExecutionError",
                "idempotency_applied": True,
            },
        ),
    )

    execution.refresh_from_db()
    run.refresh_from_db()

    assert result == "processed"
    assert execution.status == "ambiguous"
    assert run.status == "failed"
    assert "ambiguous" in run.error_message
    assert ProcessedRuntimeIntent.objects.filter(run=run).count() == 1
