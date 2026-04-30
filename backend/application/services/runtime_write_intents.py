from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis import Redis

from adapters.ws.runs.broadcast import (
    broadcast_decision_required,
    broadcast_decision_resolved,
    broadcast_node_run_updated,
    broadcast_run_updated,
)
from application.services.company_archive import ArchiveService
from application.services.metrics import record_stale_attempt_ignored
from application.services.redaction import redact_payload
from application.services.redis_connections import build_redis_client
from application.services.run_liveness import recovery_state_for_status, touch_run_liveness
from application.services.run_locking import acquire_run_transaction_lock
from application.services.run_snapshots import (
    RunSnapshot,
    delete_snapshot,
    safe_delete_snapshot,
    set_snapshot,
)
from application.services.tool_executions import transition_tool_execution
from infrastructure.orm.models import (
    ApprovalTask,
    NodeRun,
    NodeRunEventProjection,
    ProcessedRuntimeIntent,
    Run,
    RunCheckpoint,
    RunEvent,
    RunEventProjection,
    ToolExecution,
)

RUNTIME_INTENT_STREAM = (
    os.environ.get(
        "FORGEGRAPH_RUNTIME_INTENT_STREAM",
        "forgegraph:runtime:intents",
    ).strip()
    or "forgegraph:runtime:intents"
)
RUNTIME_INTENT_CONSUMER_GROUP = (
    os.environ.get(
        "FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP",
        "backend-runtime-writers",
    ).strip()
    or "backend-runtime-writers"
)
RUNTIME_INTENT_DEAD_LETTER_STREAM = (
    os.environ.get(
        "FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM",
        "forgegraph:runtime:intents:dead",
    ).strip()
    or "forgegraph:runtime:intents:dead"
)

SUPPORTED_RUNTIME_INTENTS = {
    "pause_run",
    "ack_run_resumed",
    "node_completed",
    "store_checkpoint",
    "set_run_status",
    "tool_execution_started",
    "tool_execution_succeeded",
    "tool_execution_failed",
    "tool_execution_ambiguous",
    "upsert_node_run",
}

RUN_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"pending", "running", "failed", "canceled"},
    "running": {"running", "paused", "resume_requested", "succeeded", "failed", "canceled"},
    "paused": {"paused", "resume_requested", "failed", "canceled"},
    "resume_requested": {"resume_requested", "running", "failed", "canceled"},
    "succeeded": {"succeeded"},
    "failed": {"failed"},
    "canceled": {"canceled"},
}

IntentProcessResult = Literal["processed", "duplicate", "invalid", "ignored"]
_UNSET = object()
logger = logging.getLogger(__name__)


class RuntimeIntentError(ValueError):
    """Raised when a runtime intent is malformed or violates state-machine rules."""


@dataclass(frozen=True)
class RuntimeIntentEnvelope:
    intent_id: UUID
    intent_type: str
    run_id: UUID
    attempt_id: str
    trace_id: str
    timestamp: datetime
    payload: dict[str, Any]


def _schedule_node_completed_boundary(
    *,
    intent: RuntimeIntentEnvelope,
    snapshot: RunSnapshot,
    event_time: datetime,
    stream_message_id: str,
) -> None:
    """Finalize the node_completed boundary only after commit and snapshot durability."""

    def finalize_node_completed_boundary() -> None:
        set_snapshot(snapshot)
        try:
            with transaction.atomic():
                if _intent_already_processed(intent.intent_id):
                    return

                run = _load_run_for_update(intent.run_id)
                _touch_run(run, event_time=event_time)
                _record_processed_intent(
                    intent=intent,
                    run=run,
                    stream_message_id=stream_message_id,
                )
        except Exception:
            try:
                delete_snapshot(snapshot.run_id)
            except Exception:
                logger.warning(
                    "node_completed_snapshot_compensation_failed",
                    exc_info=True,
                    extra={"run_id": str(snapshot.run_id), "intent_id": str(intent.intent_id)},
                )
            raise

    transaction.on_commit(finalize_node_completed_boundary)


def log_stale_intent(
    intent: RuntimeIntentEnvelope,
    *,
    current_attempt_id: str,
) -> None:
    logger.warning(
        "intent_ignored_due_to_stale_attempt",
        extra={
            "run_id": str(intent.run_id),
            "intent_id": str(intent.intent_id),
            "intent_type": intent.intent_type,
            "intent_attempt_id": intent.attempt_id,
            "active_attempt_id": current_attempt_id,
            "current_attempt_id": current_attempt_id,
        },
    )


def build_runtime_intent_redis_client() -> Redis:
    return build_redis_client(
        db=int(os.environ.get("RUNTIME_INTENT_REDIS_DB", os.environ.get("REDIS_DB", "0"))),
        decode_responses=True,
    )


def ensure_runtime_intent_group(redis_client: Redis) -> None:
    try:
        redis_client.xgroup_create(
            name=RUNTIME_INTENT_STREAM,
            groupname=RUNTIME_INTENT_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
    except Exception as exc:  # pragma: no cover
        if "BUSYGROUP" not in str(exc):
            raise


def decode_runtime_intent_message(fields: dict[str, str]) -> RuntimeIntentEnvelope:
    raw_intent = fields.get("intent", "")
    if not raw_intent:
        raise RuntimeIntentError("runtime intent message is missing the 'intent' field")

    try:
        payload = json.loads(raw_intent)
    except json.JSONDecodeError as exc:
        raise RuntimeIntentError(f"runtime intent payload is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeIntentError("runtime intent payload must decode to an object")

    raw_timestamp = str(payload.get("timestamp") or "").strip()
    timestamp = parse_datetime(raw_timestamp) if raw_timestamp else None
    if timestamp is None:
        raise RuntimeIntentError("runtime intent timestamp is required and must be ISO-8601")

    intent_type = str(payload.get("intent_type") or "").strip()
    if intent_type not in SUPPORTED_RUNTIME_INTENTS:
        raise RuntimeIntentError(f"unsupported runtime intent type: {intent_type or 'unknown'}")

    envelope_payload = payload.get("payload")
    if not isinstance(envelope_payload, dict):
        raise RuntimeIntentError("runtime intent payload field must be an object")

    try:
        intent_id = UUID(str(payload.get("intent_id") or "").strip())
    except ValueError as exc:
        raise RuntimeIntentError("runtime intent intent_id must be a UUID") from exc

    try:
        run_id = UUID(str(payload.get("run_id") or "").strip())
    except ValueError as exc:
        raise RuntimeIntentError("runtime intent run_id must be a UUID") from exc

    return RuntimeIntentEnvelope(
        intent_id=intent_id,
        intent_type=intent_type,
        run_id=run_id,
        attempt_id=str(payload.get("attempt_id") or "").strip(),
        trace_id=str(payload.get("trace_id") or "").strip(),
        timestamp=timestamp,
        payload=envelope_payload,
    )


def process_runtime_intent_message(
    *,
    stream_message_id: str,
    fields: dict[str, str],
) -> IntentProcessResult:
    intent = decode_runtime_intent_message(fields)
    if intent.intent_type == "pause_run":
        return apply_pause_run_intent(intent=intent, stream_message_id=stream_message_id)
    if intent.intent_type == "ack_run_resumed":
        return apply_ack_run_resumed_intent(intent=intent, stream_message_id=stream_message_id)
    if intent.intent_type == "node_completed":
        return apply_node_completed_intent(intent=intent, stream_message_id=stream_message_id)
    if intent.intent_type == "store_checkpoint":
        return apply_store_checkpoint_intent(intent=intent, stream_message_id=stream_message_id)
    if intent.intent_type == "set_run_status":
        return apply_set_run_status_intent(intent=intent, stream_message_id=stream_message_id)
    if intent.intent_type.startswith("tool_execution_"):
        return apply_tool_execution_status_intent(
            intent=intent,
            stream_message_id=stream_message_id,
        )
    if intent.intent_type == "upsert_node_run":
        return apply_upsert_node_run_intent(intent=intent, stream_message_id=stream_message_id)
    raise RuntimeIntentError(f"unsupported runtime intent type: {intent.intent_type}")


def apply_pause_run_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    pause_payload = intent.payload.get("pause_payload")
    node_id = str(intent.payload.get("node_id") or "").strip()
    if not node_id:
        raise RuntimeIntentError("pause_run payload.node_id is required")

    node_type = str(intent.payload.get("node_type") or "human_gate").strip() or "human_gate"
    node_name = str(intent.payload.get("node_name") or "").strip()
    node_attempt = _coerce_non_negative_int(intent.payload.get("node_attempt"), default=1)
    checkpoint = _require_object(intent.payload.get("checkpoint"), field="checkpoint")
    pause_state = _require_object(intent.payload.get("pause_state"), field="pause_state")

    checkpoint_node_id = str(checkpoint.get("node_id") or "").strip()
    if checkpoint_node_id != node_id:
        raise RuntimeIntentError("pause_run checkpoint.node_id must match payload.node_id")

    checkpoint_step_index = _coerce_non_negative_int(checkpoint.get("step_index"), default=0)
    checkpoint_state_snapshot = _require_object(
        checkpoint.get("state_snapshot"),
        field="checkpoint.state_snapshot",
    )
    pause_state_snapshot = _require_object(
        pause_state.get("state_snapshot"),
        field="pause_state.state_snapshot",
    )

    run: Run | None = None
    decision_payload = {
        "node_id": node_id,
        "node_name": node_name,
        "node_type": node_type,
        "attempt": node_attempt,
        "status": "waiting",
        "prompt_message": str(_payload_dict(pause_payload).get("prompt_message") or ""),
        "required_fields": list(_payload_dict(pause_payload).get("required_fields") or []),
    }

    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        if run.status not in {"running", "paused"}:
            return "invalid"

        _upsert_checkpoint(
            run=run,
            checkpoint_node_id=checkpoint_node_id,
            checkpoint_step_index=checkpoint_step_index,
            checkpoint_state_snapshot=checkpoint_state_snapshot,
            checkpoint_completed_nodes=list(checkpoint.get("completed_nodes") or []),
            checkpoint_skipped_nodes=list(checkpoint.get("skipped_nodes") or []),
            checkpoint_graph_json=checkpoint.get("graph_json"),
        )

        normalized_pause_state = {
            "state_snapshot": redact_payload(pause_state_snapshot),
            "completed_nodes": list(pause_state.get("completed_nodes") or []),
            "skipped_nodes": list(pause_state.get("skipped_nodes") or []),
            "graph_json": _stringify_graph_json(pause_state.get("graph_json")),
            "tenant_id": str(pause_state.get("tenant_id") or ""),
        }

        _update_run_fields(
            run,
            status="paused",
            trace_id=intent.trace_id or None,
            paused_node_id=node_id,
            pause_state_json=normalized_pause_state,
            resume_requested_at=None if run.resume_requested_at is not None else _UNSET,
            resume_attempt_id=None if run.resume_attempt_id is not None else _UNSET,
            event_time=intent.timestamp,
        )

        normalized_node_output = {"pause_payload": redact_payload(_payload_dict(pause_payload))}
        _upsert_node_run(
            run=run,
            node_id=node_id,
            node_type=node_type,
            attempt=node_attempt,
            status="waiting",
            started_at=intent.timestamp,
            output_json=normalized_node_output,
            trace_id=intent.trace_id,
            span_id="",
        )

        approval_payload = {
            "prompt_message": decision_payload["prompt_message"],
            "required_fields": decision_payload["required_fields"],
        }
        approval_task, created = ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={"assignee": run.owner, "payload": approval_payload},
        )
        if not created and approval_task.payload != approval_payload:
            approval_task.payload = approval_payload
            approval_task.save(update_fields=["payload"])

        _upsert_run_projection(
            run=run,
            status="paused",
            trace_id=intent.trace_id,
            event_time=intent.timestamp,
            event_type="pause_run",
            event_id=str(intent.intent_id),
            paused_node_id=node_id,
            pause_state_json=run.pause_state_json,
        )
        _upsert_node_projection(
            run=run,
            node_id=node_id,
            node_type=node_type,
            attempt=node_attempt,
            status="waiting",
            trace_id=intent.trace_id,
            span_id="",
            event_time=intent.timestamp,
            event_type="pause_run",
            event_id=str(intent.intent_id),
            started_at=intent.timestamp,
            output_json=normalized_node_output,
        )

        _create_run_event(
            run=run,
            event_type="run.updated",
            external_id=str(intent.intent_id),
            trace_id=intent.trace_id,
            payload={
                "status": "paused",
                "paused_node_id": node_id,
                "pause_payload": redact_payload(_payload_dict(pause_payload)),
                "pause_state_json": redact_payload(run.pause_state_json),
                "category": "state",
            },
        )
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)

    if run is not None:
        broadcast_run_updated(run)
        broadcast_decision_required(run=run, payload=decision_payload)
    return "processed"


def apply_ack_run_resumed_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    resolution = _payload_dict(intent.payload.get("resolution"))
    node_id = str(intent.payload.get("node_id") or "").strip()
    run: Run | None = None
    resolved_payload: dict[str, Any] | None = None

    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        if run.status != "resume_requested":
            return "invalid"

        expected_attempt_id = str(run.resume_attempt_id) if run.resume_attempt_id else ""
        if expected_attempt_id and intent.attempt_id != expected_attempt_id:
            return "invalid"

        resolved_node_id = node_id or str(run.paused_node_id or "")
        resolved_payload = {
            "node_id": resolved_node_id,
            "status": "resolved",
            "resolution": redact_payload(resolution),
        }

        _update_run_fields(
            run,
            status="running",
            trace_id=intent.trace_id or None,
            paused_node_id=None,
            pause_state_json=None,
            resume_requested_at=None,
            resume_attempt_id=None,
            event_time=intent.timestamp,
        )
        _upsert_run_projection(
            run=run,
            status="running",
            trace_id=intent.trace_id,
            event_time=intent.timestamp,
            event_type="ack_run_resumed",
            event_id=str(intent.intent_id),
            paused_node_id=None,
            pause_state_json=None,
        )
        _create_run_event(
            run=run,
            event_type="run.updated",
            external_id=str(intent.intent_id),
            trace_id=intent.trace_id,
            payload={
                "status": "running",
                "paused_node_id": None,
                "pause_state_json": None,
                "resume_requested_at": None,
                "resume_attempt_id": None,
                "category": "state",
            },
        )
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)

    if run is not None:
        broadcast_run_updated(run)
        if resolved_payload and resolved_payload["node_id"]:
            broadcast_decision_resolved(run=run, payload=resolved_payload)
    return "processed"


def apply_node_completed_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    node_id = str(intent.payload.get("node_id") or "").strip()
    if not node_id:
        raise RuntimeIntentError("node_completed payload.node_id is required")

    attempt = _coerce_non_negative_int(intent.payload.get("attempt"), default=1)
    next_node = str(intent.payload.get("next_node") or "").strip()

    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        if run.status in {"succeeded", "failed", "canceled"}:
            return "invalid"

        node_run = NodeRun.objects.filter(run=run, node_id=node_id, attempt=attempt).first()
        if node_run is None:
            return "invalid"
        if node_run.status not in {"succeeded", "failed"}:
            return "invalid"

        snapshot = RunSnapshot(
            run_id=run.id,
            last_completed_node=node_id,
            next_node=next_node,
            attempt_id=intent.attempt_id or str(attempt),
            updated_at=intent.timestamp,
        )
        _schedule_node_completed_boundary(
            intent=intent,
            snapshot=snapshot,
            event_time=intent.timestamp,
            stream_message_id=stream_message_id,
        )

    return "processed"


def apply_store_checkpoint_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    checkpoint_node_id = str(intent.payload.get("node_id") or "").strip()
    if not checkpoint_node_id:
        raise RuntimeIntentError("store_checkpoint payload.node_id is required")

    checkpoint_step_index = _coerce_non_negative_int(intent.payload.get("step_index"), default=0)
    checkpoint_state_snapshot = _require_object(
        intent.payload.get("state_snapshot"),
        field="state_snapshot",
    )

    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        if run.status in {"succeeded", "failed", "canceled"}:
            return "invalid"

        _upsert_checkpoint(
            run=run,
            checkpoint_node_id=checkpoint_node_id,
            checkpoint_step_index=checkpoint_step_index,
            checkpoint_state_snapshot=checkpoint_state_snapshot,
            checkpoint_completed_nodes=list(intent.payload.get("completed_nodes") or []),
            checkpoint_skipped_nodes=list(intent.payload.get("skipped_nodes") or []),
            checkpoint_graph_json=intent.payload.get("graph_json"),
        )

        _touch_run(run, event_time=intent.timestamp)
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)

    return "processed"


def apply_set_run_status_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    raw_status_value = str(intent.payload.get("status") or "").strip()
    if raw_status_value and raw_status_value not in RUN_STATUS_TRANSITIONS:
        raise RuntimeIntentError(
            f"set_run_status payload.status is invalid: {raw_status_value or 'empty'}"
        )

    run: Run | None = None
    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        status_value = raw_status_value or run.status
        if raw_status_value and status_value not in RUN_STATUS_TRANSITIONS.get(
            run.status, {run.status}
        ):
            return "invalid"

        clear_pause_state = bool(intent.payload.get("clear_pause_state"))
        if status_value in {"failed", "canceled", "succeeded"}:
            clear_pause_state = True

        _update_run_fields(
            run,
            status=status_value,
            trace_id=str(intent.payload.get("trace_id") or intent.trace_id or "").strip() or None,
            started_at=_parse_optional_datetime_field(intent.payload, "started_at"),
            ended_at=_parse_optional_datetime_field(intent.payload, "ended_at"),
            output_json=redact_payload(intent.payload.get("output_json"))
            if "output_json" in intent.payload
            else _UNSET,
            error_message=str(redact_payload(intent.payload.get("error_message") or ""))
            if "error_message" in intent.payload
            else _UNSET,
            paused_node_id=None if clear_pause_state else _UNSET,
            pause_state_json=None if clear_pause_state else _UNSET,
            resume_requested_at=None if clear_pause_state and run.resume_requested_at else _UNSET,
            resume_attempt_id=None if clear_pause_state and run.resume_attempt_id else _UNSET,
            event_time=intent.timestamp,
        )
        _upsert_run_projection(
            run=run,
            status=run.status,
            trace_id=run.trace_id,
            event_time=intent.timestamp,
            event_type="set_run_status",
            event_id=str(intent.intent_id),
            paused_node_id=run.paused_node_id,
            pause_state_json=run.pause_state_json,
            started_at=run.started_at,
            ended_at=run.ended_at,
            output_json=run.output_json,
            error_message=run.error_message,
        )
        _create_run_event(
            run=run,
            event_type="run.updated",
            external_id=str(intent.intent_id),
            trace_id=run.trace_id,
            payload={
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "output_json": redact_payload(run.output_json),
                "error_message": redact_payload(run.error_message),
                "paused_node_id": run.paused_node_id,
                "pause_state_json": redact_payload(run.pause_state_json),
                "category": "state",
            },
        )
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)
        if run.status in {"succeeded", "failed", "canceled"}:
            run_id = run.id

            def delete_completed_run_snapshot() -> None:
                safe_delete_snapshot(run_id)

            transaction.on_commit(delete_completed_run_snapshot)
            if run.status == "succeeded":
                _schedule_deliverable_archive(run_id=run.id)

    if run is not None:
        broadcast_run_updated(run)
    return "processed"


def apply_tool_execution_status_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    status_by_intent_type = {
        "tool_execution_started": "in_progress",
        "tool_execution_succeeded": "succeeded",
        "tool_execution_failed": "failed",
        "tool_execution_ambiguous": "ambiguous",
    }
    next_status = status_by_intent_type.get(intent.intent_type)
    if next_status is None:
        raise RuntimeIntentError(f"unsupported tool execution intent type: {intent.intent_type}")

    try:
        tool_execution_id = UUID(str(intent.payload.get("tool_execution_id") or "").strip())
    except ValueError as exc:
        raise RuntimeIntentError("tool execution payload.tool_execution_id must be a UUID") from exc

    run: Run | None = None
    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result

        tool_execution = (
            ToolExecution.objects.select_for_update()
            .filter(
                id=tool_execution_id,
                run=run,
            )
            .first()
        )
        if tool_execution is None:
            raise RuntimeIntentError("tool execution record not found for run")
        if tool_execution.attempt_id != intent.attempt_id:
            raise RuntimeIntentError("tool execution attempt_id does not match intent.attempt_id")

        transition_tool_execution(tool_execution=tool_execution, status=next_status)
        _touch_run(run, event_time=intent.timestamp)
        _create_run_event(
            run=run,
            event_type=f"tool_execution.{next_status}",
            external_id=str(intent.intent_id),
            trace_id=run.trace_id,
            payload={
                "tool_execution_id": str(tool_execution.id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "tool_name": tool_execution.tool_name,
                "tool_version": tool_execution.tool_version,
                "idempotency_key": tool_execution.idempotency_key,
                "side_effect_class": tool_execution.side_effect_class,
                "status": next_status,
                "reason": str(intent.payload.get("reason") or "").strip(),
                "error_class": str(intent.payload.get("error_class") or "").strip(),
                "idempotency_applied": bool(intent.payload.get("idempotency_applied")),
                "category": "state",
            },
        )
        if next_status == "ambiguous" and run.status not in {"succeeded", "failed", "canceled"}:
            _update_run_fields(
                run,
                status="failed",
                ended_at=intent.timestamp,
                error_message=(
                    "Tool execution outcome is ambiguous; automatic retry blocked. "
                    f"tool_execution_id={tool_execution.id}"
                ),
                event_time=intent.timestamp,
            )
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)

    if run is not None:
        broadcast_run_updated(run)
    return "processed"


def apply_upsert_node_run_intent(
    *,
    intent: RuntimeIntentEnvelope,
    stream_message_id: str,
) -> IntentProcessResult:
    _require_intent_attempt_id(intent)
    node_id = str(intent.payload.get("node_id") or "").strip()
    node_type = str(intent.payload.get("node_type") or "").strip()
    status_value = str(intent.payload.get("status") or "").strip()
    if not node_id:
        raise RuntimeIntentError("upsert_node_run payload.node_id is required")
    if not node_type:
        raise RuntimeIntentError("upsert_node_run payload.node_type is required")
    if status_value not in {"pending", "running", "waiting", "succeeded", "failed", "skipped"}:
        raise RuntimeIntentError("upsert_node_run payload.status is invalid")

    attempt = _coerce_non_negative_int(intent.payload.get("attempt"), default=1)
    run: Run | None = None
    node_run: NodeRun | None = None

    with transaction.atomic():
        if _intent_already_processed(intent.intent_id):
            return "duplicate"

        run = _load_run_for_update(intent.run_id)
        stale_result = _ignore_stale_attempt(intent=intent, run=run)
        if stale_result is not None:
            return stale_result
        if run.status in {"succeeded", "failed", "canceled"}:
            return "invalid"
        node_run = _upsert_node_run(
            run=run,
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            status=status_value,
            started_at=_parse_optional_datetime_field(intent.payload, "started_at"),
            ended_at=_parse_optional_datetime_field(intent.payload, "ended_at"),
            input_json=redact_payload(intent.payload.get("input_json"))
            if "input_json" in intent.payload
            else _UNSET,
            output_json=redact_payload(intent.payload.get("output_json"))
            if "output_json" in intent.payload
            else _UNSET,
            error_json=redact_payload(intent.payload.get("error_json"))
            if "error_json" in intent.payload
            else _UNSET,
            trace_id=str(intent.payload.get("trace_id") or intent.trace_id or "").strip(),
            span_id=str(intent.payload.get("span_id") or "").strip(),
            node_run_id=str(intent.payload.get("id") or "").strip(),
        )
        _touch_run(run, event_time=intent.timestamp)
        _upsert_node_projection(
            run=run,
            node_id=node_id,
            node_type=node_run.node_type,
            attempt=attempt,
            status=node_run.status,
            trace_id=node_run.trace_id,
            span_id=node_run.span_id,
            event_time=intent.timestamp,
            event_type="upsert_node_run",
            event_id=str(intent.intent_id),
            started_at=node_run.started_at,
            ended_at=node_run.ended_at,
            output_json=node_run.output_json,
            error_json=node_run.error_json,
        )
        _record_processed_intent(intent=intent, run=run, stream_message_id=stream_message_id)
        if node_run.status == "succeeded":
            _schedule_deliverable_archive(run_id=run.id, node_run_id=node_run.id)

    if run is not None and node_run is not None:
        broadcast_node_run_updated(run=run, node_run=node_run)
    return "processed"


def _load_run_for_update(run_id: UUID) -> Run:
    try:
        acquire_run_transaction_lock(run_id)
        return Run.objects.select_for_update().select_related("owner").get(id=run_id)
    except Run.DoesNotExist as exc:
        raise RuntimeIntentError(f"run '{run_id}' not found") from exc


def _schedule_deliverable_archive(*, run_id: UUID, node_run_id: UUID | None = None) -> None:
    """Archive deliverable-shaped outputs after authoritative runtime writes commit."""

    def archive_deliverables() -> None:
        try:
            run = Run.objects.select_related(
                "organization",
                "graph_version__graph__organization",
            ).get(id=run_id)
            node_run = None
            if node_run_id is not None:
                node_run = NodeRun.objects.filter(id=node_run_id, run=run).first()
            ArchiveService().archive_deliverable_as_asset(run=run, node_run=node_run)
        except Exception:
            logger.exception(
                "deliverable_archive_failed",
                extra={"run_id": str(run_id), "node_run_id": str(node_run_id or "")},
            )

    transaction.on_commit(archive_deliverables)


def mark_run_transport_failure(
    *,
    run_id: UUID | str | None,
    stream_message_id: str,
    reason: str,
    event_time: datetime | None = None,
    dead_letter_stream: str = RUNTIME_INTENT_DEAD_LETTER_STREAM,
    intent_id: str = "",
    intent_type: str = "",
) -> bool:
    raw_run_id = str(run_id or "").strip()
    if not raw_run_id:
        return False

    try:
        parsed_run_id = UUID(raw_run_id)
    except ValueError:
        return False

    effective_event_time = event_time or timezone.now()
    try:
        with transaction.atomic():
            run = _load_run_for_update(parsed_run_id)
            is_terminal = run.status in {"succeeded", "failed", "canceled"}
            next_status = run.status if is_terminal else "failed"
            transport_error_message = (
                "Runtime intent transport dead-lettered an intent. "
                f"message_id={stream_message_id}. "
                f"intent_id={intent_id or 'unknown'}. "
                f"intent_type={intent_type or 'unknown'}. "
                f"reason={reason}."
            )
            _update_run_fields(
                run,
                status=next_status,
                ended_at=effective_event_time
                if next_status == "failed" and not is_terminal
                else _UNSET,
                error_message=transport_error_message if not is_terminal else _UNSET,
                resume_requested_at=None if run.resume_requested_at is not None else _UNSET,
                resume_attempt_id=None if run.resume_attempt_id is not None else _UNSET,
                event_time=effective_event_time,
            )
            run.recovery_state = "transport_dead_lettered"
            run.recovery_reason = "transport_dead_lettered"
            run.save(update_fields=["recovery_state", "recovery_reason"])
            _create_run_event(
                run=run,
                event_type="run.updated",
                external_id=intent_id or stream_message_id,
                trace_id=run.trace_id,
                payload={
                    "status": run.status,
                    "error_message": transport_error_message,
                    "recovery_state": "transport_dead_lettered",
                    "recovery_reason": "transport_dead_lettered",
                    "stream_message_id": stream_message_id,
                    "dead_letter_stream": dead_letter_stream,
                    "intent_id": intent_id or None,
                    "intent_type": intent_type or None,
                    "category": "state",
                },
            )
    except RuntimeIntentError:
        return False

    broadcast_run_updated(run)
    return True


def _intent_already_processed(intent_id: UUID) -> bool:
    return ProcessedRuntimeIntent.objects.filter(intent_id=intent_id).exists()


def _require_intent_attempt_id(intent: RuntimeIntentEnvelope) -> None:
    if not str(intent.attempt_id or "").strip():
        raise RuntimeIntentError(f"{intent.intent_type} intent.attempt_id is required")


def _ignore_stale_attempt(
    *,
    intent: RuntimeIntentEnvelope,
    run: Run,
) -> IntentProcessResult | None:
    current_attempt_id = run.authoritative_attempt_id

    if current_attempt_id and intent.attempt_id != current_attempt_id:
        record_stale_attempt_ignored("runtime_intent")
        log_stale_intent(intent, current_attempt_id=current_attempt_id)
        return "ignored"
    return None


def _record_processed_intent(
    *,
    intent: RuntimeIntentEnvelope,
    run: Run,
    stream_message_id: str,
) -> None:
    ProcessedRuntimeIntent.objects.create(
        intent_id=intent.intent_id,
        run=run,
        intent_type=intent.intent_type,
        attempt_id=intent.attempt_id,
        trace_id=intent.trace_id,
        stream_message_id=stream_message_id,
    )


def _touch_run(run: Run, *, event_time: datetime) -> None:
    update_fields = touch_run_liveness(
        run,
        event_time=event_time,
        recovery_state=recovery_state_for_status(run.status),
    )
    run.save(update_fields=sorted(set(update_fields)))


def _update_run_fields(
    run: Run,
    *,
    status: str | object = _UNSET,
    trace_id: str | None | object = _UNSET,
    started_at: datetime | None | object = _UNSET,
    ended_at: datetime | None | object = _UNSET,
    output_json: Any = _UNSET,
    error_message: str | object = _UNSET,
    paused_node_id: str | None | object = _UNSET,
    pause_state_json: Any = _UNSET,
    resume_requested_at: datetime | None | object = _UNSET,
    resume_attempt_id: UUID | None | object = _UNSET,
    event_time: datetime,
) -> None:
    update_fields: list[str] = []

    if status is not _UNSET and run.status != status:
        run.status = str(status)
        update_fields.append("status")
    if trace_id is not _UNSET:
        next_trace_id = str(trace_id or "")
        if run.trace_id != next_trace_id:
            run.trace_id = next_trace_id
            update_fields.append("trace_id")
    if started_at is not _UNSET and run.started_at != started_at:
        run.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and run.ended_at != ended_at:
        run.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if output_json is not _UNSET and run.output_json != output_json:
        run.output_json = output_json
        update_fields.append("output_json")
    if error_message is not _UNSET and run.error_message != error_message:
        run.error_message = str(error_message)
        update_fields.append("error_message")
    if paused_node_id is not _UNSET and run.paused_node_id != paused_node_id:
        run.paused_node_id = cast(str | None, paused_node_id)
        update_fields.append("paused_node_id")
    if pause_state_json is not _UNSET and run.pause_state_json != pause_state_json:
        run.pause_state_json = pause_state_json
        update_fields.append("pause_state_json")
    if resume_requested_at is not _UNSET and run.resume_requested_at != resume_requested_at:
        run.resume_requested_at = cast(datetime | None, resume_requested_at)
        update_fields.append("resume_requested_at")
    if resume_attempt_id is not _UNSET and run.resume_attempt_id != resume_attempt_id:
        run.resume_attempt_id = cast(UUID | None, resume_attempt_id)
        update_fields.append("resume_attempt_id")

    update_fields.extend(
        touch_run_liveness(
            run,
            event_time=event_time,
            recovery_state=recovery_state_for_status(run.status),
        )
    )
    run.save(update_fields=sorted(set(update_fields)))


def _upsert_checkpoint(
    *,
    run: Run,
    checkpoint_node_id: str,
    checkpoint_step_index: int,
    checkpoint_state_snapshot: dict[str, Any],
    checkpoint_completed_nodes: list[Any],
    checkpoint_skipped_nodes: list[Any],
    checkpoint_graph_json: object,
) -> None:
    checkpoint_graph = _decode_graph_json(checkpoint_graph_json)
    checkpoint, created = RunCheckpoint.objects.select_for_update().get_or_create(
        run=run,
        defaults={
            "node_id": checkpoint_node_id,
            "step_index": checkpoint_step_index,
            "state_json": redact_payload(checkpoint_state_snapshot),
            "completed_nodes": checkpoint_completed_nodes,
            "skipped_nodes": checkpoint_skipped_nodes,
            "graph_json": checkpoint_graph,
        },
    )
    if created or checkpoint.step_index <= checkpoint_step_index:
        checkpoint.node_id = checkpoint_node_id
        checkpoint.step_index = checkpoint_step_index
        checkpoint.state_json = redact_payload(checkpoint_state_snapshot)
        checkpoint.completed_nodes = checkpoint_completed_nodes
        checkpoint.skipped_nodes = checkpoint_skipped_nodes
        checkpoint.graph_json = checkpoint_graph
        checkpoint.save(
            update_fields=[
                "node_id",
                "step_index",
                "state_json",
                "completed_nodes",
                "skipped_nodes",
                "graph_json",
                "updated_at",
            ]
        )


def _upsert_node_run(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    status: str,
    started_at: datetime | None | object = _UNSET,
    ended_at: datetime | None | object = _UNSET,
    input_json: Any = _UNSET,
    output_json: Any = _UNSET,
    error_json: Any = _UNSET,
    trace_id: str = "",
    span_id: str = "",
    node_run_id: str = "",
) -> NodeRun:
    defaults: dict[str, object] = {
        "node_type": node_type,
        "status": status,
    }
    if node_run_id:
        try:
            defaults["id"] = UUID(node_run_id)
        except ValueError:
            pass

    node_run, _ = NodeRun.objects.get_or_create(
        run=run,
        node_id=node_id,
        attempt=attempt,
        defaults=defaults,
    )

    update_fields: list[str] = []
    if node_run.node_type != node_type:
        node_run.node_type = node_type
        update_fields.append("node_type")
    if node_run.status != status:
        node_run.status = status
        update_fields.append("status")
    if started_at is not _UNSET and node_run.started_at != started_at:
        node_run.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and node_run.ended_at != ended_at:
        node_run.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if input_json is not _UNSET and node_run.input_json != input_json:
        node_run.input_json = input_json
        update_fields.append("input_json")
    if output_json is not _UNSET and node_run.output_json != output_json:
        node_run.output_json = output_json
        update_fields.append("output_json")
    if error_json is not _UNSET and node_run.error_json != error_json:
        node_run.error_json = error_json
        update_fields.append("error_json")
    if trace_id and node_run.trace_id != trace_id:
        node_run.trace_id = trace_id
        update_fields.append("trace_id")
    if span_id and node_run.span_id != span_id:
        node_run.span_id = span_id
        update_fields.append("span_id")
    if update_fields:
        node_run.save(update_fields=sorted(set(update_fields)))
    return node_run


def _upsert_run_projection(
    *,
    run: Run,
    status: str,
    trace_id: str,
    event_time: datetime,
    event_type: str,
    event_id: str,
    paused_node_id: str | None | object = _UNSET,
    pause_state_json: Any = _UNSET,
    started_at: datetime | None | object = _UNSET,
    ended_at: datetime | None | object = _UNSET,
    output_json: Any = _UNSET,
    error_message: str | object = _UNSET,
) -> None:
    projection, _ = RunEventProjection.objects.get_or_create(
        run=run,
        defaults={
            "status": status,
            "trace_id": trace_id,
            "last_event_type": event_type,
            "last_event_id": event_id,
            "last_event_at": event_time,
        },
    )
    update_fields: list[str] = []
    if projection.status != status:
        projection.status = status
        update_fields.append("status")
    if paused_node_id is not _UNSET and projection.paused_node_id != paused_node_id:
        projection.paused_node_id = cast(str | None, paused_node_id)
        update_fields.append("paused_node_id")
    if pause_state_json is not _UNSET and projection.pause_state_json != pause_state_json:
        projection.pause_state_json = pause_state_json
        update_fields.append("pause_state_json")
    if started_at is not _UNSET and projection.started_at != started_at:
        projection.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and projection.ended_at != ended_at:
        projection.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if output_json is not _UNSET and projection.output_json != output_json:
        projection.output_json = output_json
        update_fields.append("output_json")
    if error_message is not _UNSET and projection.error_message != error_message:
        projection.error_message = str(error_message)
        update_fields.append("error_message")
    if trace_id and projection.trace_id != trace_id:
        projection.trace_id = trace_id
        update_fields.append("trace_id")
    if projection.last_event_type != event_type:
        projection.last_event_type = event_type
        update_fields.append("last_event_type")
    if projection.last_event_id != event_id:
        projection.last_event_id = event_id
        update_fields.append("last_event_id")
    if projection.last_event_at != event_time:
        projection.last_event_at = event_time
        update_fields.append("last_event_at")
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


def _upsert_node_projection(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    status: str,
    trace_id: str,
    span_id: str,
    event_time: datetime,
    event_type: str,
    event_id: str,
    started_at: datetime | None | object = _UNSET,
    ended_at: datetime | None | object = _UNSET,
    output_json: Any = _UNSET,
    error_json: Any = _UNSET,
) -> None:
    projection, _ = NodeRunEventProjection.objects.get_or_create(
        run=run,
        node_id=node_id,
        attempt=attempt,
        defaults={
            "node_type": node_type,
            "status": status,
            "trace_id": trace_id,
            "span_id": span_id,
            "last_event_type": event_type,
            "last_event_id": event_id,
            "last_event_at": event_time,
        },
    )
    update_fields: list[str] = []
    if projection.node_type != node_type:
        projection.node_type = node_type
        update_fields.append("node_type")
    if projection.status != status:
        projection.status = status
        update_fields.append("status")
    if started_at is not _UNSET and projection.started_at != started_at:
        projection.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and projection.ended_at != ended_at:
        projection.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if output_json is not _UNSET and projection.output_json != output_json:
        projection.output_json = output_json
        update_fields.append("output_json")
    if error_json is not _UNSET and projection.error_json != error_json:
        projection.error_json = error_json
        update_fields.append("error_json")
    if trace_id and projection.trace_id != trace_id:
        projection.trace_id = trace_id
        update_fields.append("trace_id")
    if span_id and projection.span_id != span_id:
        projection.span_id = span_id
        update_fields.append("span_id")
    if projection.last_event_type != event_type:
        projection.last_event_type = event_type
        update_fields.append("last_event_type")
    if projection.last_event_id != event_id:
        projection.last_event_id = event_id
        update_fields.append("last_event_id")
    if projection.last_event_at != event_time:
        projection.last_event_at = event_time
        update_fields.append("last_event_at")
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


def _create_run_event(
    *,
    run: Run,
    event_type: str,
    external_id: str,
    trace_id: str,
    payload: dict[str, Any],
) -> None:
    RunEvent.objects.create(
        run=run,
        event_type=event_type,
        external_id=external_id,
        trace_id=trace_id,
        payload=payload,
    )


def _coerce_non_negative_int(raw_value: object, *, default: int) -> int:
    try:
        value = int(cast(Any, raw_value))
    except (TypeError, ValueError):
        value = default
    return value if value >= 0 else default


def _parse_optional_datetime(raw_value: object) -> datetime | None:
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, str):
        parsed = parse_datetime(raw_value)
        if parsed is not None:
            return parsed
    raise RuntimeIntentError("invalid datetime field in runtime intent payload")


def _parse_optional_datetime_field(payload: dict[str, Any], field: str) -> datetime | None | object:
    if field not in payload:
        return _UNSET
    return _parse_optional_datetime(payload.get(field))


def _decode_graph_json(raw_value: object) -> object:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeIntentError(
                "checkpoint.graph_json must be a JSON object, array, or JSON string"
            ) from exc
    raise RuntimeIntentError("checkpoint.graph_json must be a JSON object, array, or JSON string")


def _stringify_graph_json(raw_value: object) -> str:
    if isinstance(raw_value, str):
        return raw_value
    if isinstance(raw_value, (dict, list)):
        return json.dumps(raw_value)
    return str(raw_value or "")


def _payload_dict(raw_value: object) -> dict[str, Any]:
    return raw_value if isinstance(raw_value, dict) else {}


def _require_object(raw_value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise RuntimeIntentError(f"runtime intent payload field '{field}' must be an object")
    return raw_value
