from __future__ import annotations

import json
import time
from io import StringIO
from typing import cast
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from redis import Redis

from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
    ensure_runtime_intent_group,
)
from infrastructure.orm.management.commands import process_runtime_write_intents
from infrastructure.orm.management.commands.process_runtime_write_intents import Command
from infrastructure.orm.models import (
    ApprovalTask,
    Graph,
    GraphVersion,
    ProcessedRuntimeIntent,
    Run,
    RunCheckpoint,
    RunEvent,
)
from tests.e2e.runtime_intent_failure_harness import (
    CrashBeforeAckRedis,
    FakeRuntimeIntentRedis,
    build_json_logger,
    parse_json_logs,
)

pytestmark = pytest.mark.django_db


def _make_run(user, *, status: str = "running") -> Run:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Redis Runtime Failure Graph",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status=status,
        trace_id="trace-before",
    )


def _runtime_intent_fields(
    *,
    run: Run,
    intent_type: str,
    payload: dict[str, object],
    attempt_id: str = "attempt-1",
    trace_id: str = "trace-intent",
    intent_id: UUID | None = None,
) -> dict[str, str]:
    return {
        "intent": json.dumps(
            {
                "intent_id": str(intent_id or uuid4()),
                "intent_type": intent_type,
                "run_id": str(run.id),
                "attempt_id": attempt_id,
                "trace_id": trace_id,
                "timestamp": timezone.now().isoformat(),
                "payload": payload,
            }
        )
    }


def _pause_run_fields(*, run: Run, intent_id: UUID | None = None) -> dict[str, str]:
    return _runtime_intent_fields(
        run=run,
        intent_id=intent_id,
        intent_type="pause_run",
        payload={
            "node_id": "human_gate_1",
            "node_type": "human_gate",
            "node_name": "Human Review",
            "node_attempt": 1,
            "pause_payload": {
                "prompt_message": "Approve the draft",
                "required_fields": ["feedback"],
            },
            "checkpoint": {
                "node_id": "human_gate_1",
                "step_index": 7,
                "state_snapshot": {
                    "checkpoint_version": 2,
                    "state": {"approved": False},
                    "completed": ["start"],
                    "skipped": [],
                    "pending": {"human_gate_1": 0},
                    "visit_counts": {"start": 1},
                },
                "completed_nodes": ["start"],
                "skipped_nodes": [],
                "graph_json": {"nodes": [], "edges": []},
            },
            "pause_state": {
                "state_snapshot": {"approved": False},
                "completed_nodes": ["start"],
                "skipped_nodes": [],
                "graph_json": '{"nodes":[],"edges":[]}',
                "tenant_id": "tenant-1",
            },
        },
    )


def _checkpoint_fields(*, run: Run, node_id: str, step_index: int) -> dict[str, str]:
    return _runtime_intent_fields(
        run=run,
        intent_type="store_checkpoint",
        payload={
            "node_id": node_id,
            "step_index": step_index,
            "state_snapshot": {"checkpoint_version": 2, "state": {node_id: step_index}},
            "completed_nodes": [],
            "skipped_nodes": [],
            "graph_json": {"nodes": [], "edges": []},
        },
    )


def _terminal_status_fields(*, run: Run, status: str) -> dict[str, str]:
    return _runtime_intent_fields(
        run=run,
        intent_type="set_run_status",
        payload={
            "status": status,
            "ended_at": timezone.now().isoformat(),
            "error_message": "transport backlog released",
        },
    )


def _publish(redis_client: FakeRuntimeIntentRedis, fields: dict[str, str]) -> str:
    return redis_client.xadd(RUNTIME_INTENT_STREAM, fields)


def _command(*, stdout: StringIO | None = None, stderr: StringIO | None = None) -> Command:
    return Command(stdout=stdout or StringIO(), stderr=stderr or StringIO())


def _configure_command_logger(monkeypatch: pytest.MonkeyPatch, name: str) -> StringIO:
    logger, stream = build_json_logger(name)
    monkeypatch.setattr(process_runtime_write_intents, "logger", logger)
    return stream


def _event_types(log_stream: StringIO) -> list[str]:
    return [payload["event_type"] for payload in parse_json_logs(log_stream)]


def test_consumer_stopped_leaves_backlog_visible_and_run_state_stuck(user):
    """Reveals that published intents accumulate and backend state does not advance."""

    redis_client = FakeRuntimeIntentRedis()
    ensure_runtime_intent_group(cast(Redis, redis_client))
    run = _make_run(user, status="running")

    _publish(redis_client, _checkpoint_fields(run=run, node_id="node_1", step_index=1))
    _publish(redis_client, _checkpoint_fields(run=run, node_id="node_2", step_index=2))
    _publish(redis_client, _terminal_status_fields(run=run, status="failed"))

    stderr = StringIO()
    command = _command(stderr=stderr)
    command._log_consumer_lag(
        redis_client=cast(Redis, redis_client),
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
    )

    run.refresh_from_db()
    group_info = redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)[0]

    assert redis_client.xlen(RUNTIME_INTENT_STREAM) == 3
    assert group_info["pending"] == 0
    assert group_info["lag"] == 3
    assert run.status == "running"
    assert ProcessedRuntimeIntent.objects.filter(run=run).count() == 0
    assert "Runtime intent consumer lag:" in stderr.getvalue()
    assert "lag=3" in stderr.getvalue()


def test_consumer_crash_after_apply_before_ack_reclaims_and_deduplicates(monkeypatch, user):
    """Reveals at-least-once delivery and verifies duplicate intents do not corrupt state."""

    base_redis = FakeRuntimeIntentRedis()
    ensure_runtime_intent_group(cast(Redis, base_redis))
    crash_redis = CrashBeforeAckRedis(base_redis)
    run = _make_run(user, status="running")
    intent_id = uuid4()
    _publish(base_redis, _pause_run_fields(run=run, intent_id=intent_id))

    log_stream = _configure_command_logger(monkeypatch, "tests.redis_runtime_transport.crash")
    monkeypatch.setattr(
        process_runtime_write_intents,
        "build_runtime_intent_redis_client",
        lambda: crash_redis,
    )

    with pytest.raises(RuntimeError, match="simulated consumer crash before ack"):
        _command().handle(
            consumer="consumer-a",
            block_ms=1,
            count=1,
            claim_idle_ms=1,
            max_deliveries=8,
            lag_log_interval_seconds=1,
            lag_warning_threshold=1,
            lag_warning_threshold_ms=1,
            no_progress_threshold_seconds=1,
            once=True,
        )

    run.refresh_from_db()
    assert run.status == "paused"
    assert base_redis.pending_count(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP) == 1
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).count() == 1

    time.sleep(0.01)
    monkeypatch.setattr(
        process_runtime_write_intents,
        "build_runtime_intent_redis_client",
        lambda: base_redis,
    )
    _command().handle(
        consumer="consumer-b",
        block_ms=1,
        count=1,
        claim_idle_ms=1,
        max_deliveries=8,
        lag_log_interval_seconds=1,
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
        no_progress_threshold_seconds=1,
        once=True,
    )

    run.refresh_from_db()
    event_types = _event_types(log_stream)

    assert "intent_received" in event_types
    assert "intent_applied" in event_types
    assert "intent_reclaimed" in event_types
    assert "duplicate_intent_ignored" in event_types
    assert event_types.count("intent_ack") == 1
    assert run.status == "paused"
    assert base_redis.pending_count(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP) == 0
    assert ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).count() == 1
    assert ApprovalTask.objects.filter(run=run, node_id="human_gate_1").count() == 1
    assert RunCheckpoint.objects.filter(run=run).count() == 1
    assert RunEvent.objects.filter(run=run, external_id=str(intent_id)).count() == 1


def test_poison_message_is_dead_lettered_and_run_is_failed(monkeypatch, user):
    redis_client = FakeRuntimeIntentRedis()
    ensure_runtime_intent_group(cast(Redis, redis_client))
    run = _make_run(user, status="running")
    _publish(redis_client, _pause_run_fields(run=run))

    log_stream = _configure_command_logger(monkeypatch, "tests.redis_runtime_transport.dead_letter")
    monkeypatch.setattr(
        process_runtime_write_intents,
        "build_runtime_intent_redis_client",
        lambda: redis_client,
    )

    def always_fail(*, stream_message_id: str, fields: dict[str, str]):
        raise RuntimeError(f"poison message {stream_message_id}")

    monkeypatch.setattr(
        process_runtime_write_intents, "process_runtime_intent_message", always_fail
    )

    _command().handle(
        consumer="consumer-a",
        block_ms=1,
        count=1,
        claim_idle_ms=1,
        max_deliveries=1,
        lag_log_interval_seconds=1,
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
        no_progress_threshold_seconds=1,
        once=True,
    )
    assert redis_client.pending_count(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP) == 1
    assert redis_client.xlen(RUNTIME_INTENT_DEAD_LETTER_STREAM) == 0

    time.sleep(0.01)
    _command().handle(
        consumer="consumer-b",
        block_ms=1,
        count=1,
        claim_idle_ms=1,
        max_deliveries=1,
        lag_log_interval_seconds=1,
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
        no_progress_threshold_seconds=1,
        once=True,
    )

    run.refresh_from_db()
    event_types = _event_types(log_stream)
    dead_letters = redis_client.stream_entries(RUNTIME_INTENT_DEAD_LETTER_STREAM)

    assert redis_client.pending_count(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP) == 0
    assert len(dead_letters) == 1
    assert dead_letters[0][1]["original_message_id"] == "1-0"
    assert run.status == "failed"
    assert run.recovery_state == "transport_dead_lettered"
    assert run.recovery_reason == "transport_dead_lettered"
    assert "dead_lettered" in event_types


def test_slow_consumer_grows_backlog_then_recovers(monkeypatch, user):
    """Reveals that lag is measurable under slowdown and drains once normal speed returns."""

    redis_client = FakeRuntimeIntentRedis()
    ensure_runtime_intent_group(cast(Redis, redis_client))
    run = _make_run(user, status="running")
    _publish(redis_client, _checkpoint_fields(run=run, node_id="node_1", step_index=1))
    _publish(redis_client, _checkpoint_fields(run=run, node_id="node_2", step_index=2))
    _publish(redis_client, _terminal_status_fields(run=run, status="failed"))

    log_stream = _configure_command_logger(monkeypatch, "tests.redis_runtime_transport.slow")
    monkeypatch.setattr(
        process_runtime_write_intents,
        "build_runtime_intent_redis_client",
        lambda: redis_client,
    )

    original_process = process_runtime_write_intents.process_runtime_intent_message  # type: ignore[attr-defined]
    call_count = 0

    def slow_process(*, stream_message_id: str, fields: dict[str, str]):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            time.sleep(0.02)
        return original_process(stream_message_id=stream_message_id, fields=fields)

    monkeypatch.setattr(
        process_runtime_write_intents, "process_runtime_intent_message", slow_process
    )

    slow_stderr = StringIO()
    _command(stderr=slow_stderr).handle(
        consumer="slow-consumer",
        block_ms=1,
        count=1,
        claim_idle_ms=1,
        max_deliveries=8,
        lag_log_interval_seconds=1,
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
        no_progress_threshold_seconds=1,
        once=True,
    )

    run.refresh_from_db()
    first_group_info = redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)[0]

    assert first_group_info["lag"] == 2
    assert run.status == "running"
    assert ProcessedRuntimeIntent.objects.filter(run=run).count() == 1
    assert "Runtime intent consumer lag:" in slow_stderr.getvalue()
    assert "lag=2" in slow_stderr.getvalue()

    monkeypatch.setattr(
        process_runtime_write_intents,
        "process_runtime_intent_message",
        original_process,
    )

    _command().handle(
        consumer="recovered-consumer",
        block_ms=1,
        count=10,
        claim_idle_ms=1,
        max_deliveries=8,
        lag_log_interval_seconds=1,
        lag_warning_threshold=1,
        lag_warning_threshold_ms=1,
        no_progress_threshold_seconds=1,
        once=True,
    )

    run.refresh_from_db()
    final_group_info = redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)[0]
    event_types = _event_types(log_stream)

    assert final_group_info["lag"] == 0
    assert final_group_info["pending"] == 0
    assert run.status == "failed"
    assert ProcessedRuntimeIntent.objects.filter(run=run).count() == 3
    assert "intent_received" in event_types
    assert "intent_applied" in event_types
    assert event_types.count("intent_ack") == 3
