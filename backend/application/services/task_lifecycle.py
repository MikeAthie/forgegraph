from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.redaction import redact_payload
from infrastructure.orm.models import (
    DecisionRecord,
    GraphVersion,
    NodeRun,
    Organization,
    RetryOperation,
    Run,
    TaskAttemptRecord,
    TaskDeadLetterRecord,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
    User,
)

TASK_STATUSES = {
    "created",
    "queued",
    "claimed",
    "running",
    "paused",
    "waiting_for_decision",
    "retry_scheduled",
    "completed",
    "failed",
    "dead_lettered",
    "cancelled",
}
TERMINAL_TASK_STATUSES = {"completed", "failed", "dead_lettered", "cancelled"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "canceled"}

ALLOWED_TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"created", "queued", "claimed", "running", "paused", "waiting_for_decision", "failed", "dead_lettered", "cancelled"},
    "queued": {"queued", "claimed", "running", "retry_scheduled", "failed", "dead_lettered", "cancelled"},
    "claimed": {"claimed", "running", "retry_scheduled", "failed", "dead_lettered", "cancelled"},
    "running": {"running", "paused", "waiting_for_decision", "retry_scheduled", "completed", "failed", "dead_lettered", "cancelled"},
    "paused": {"paused", "running", "waiting_for_decision", "retry_scheduled", "failed", "dead_lettered", "cancelled"},
    "waiting_for_decision": {"waiting_for_decision", "running", "retry_scheduled", "completed", "failed", "dead_lettered", "cancelled"},
    "retry_scheduled": {"retry_scheduled", "queued", "claimed", "running", "failed", "dead_lettered", "cancelled"},
    "completed": {"completed"},
    "failed": {"failed", "retry_scheduled", "dead_lettered"},
    "dead_lettered": {"dead_lettered"},
    "cancelled": {"cancelled"},
}

NODE_TO_TASK_STATUS = {
    "pending": "queued",
    "running": "running",
    "waiting": "waiting_for_decision",
    "succeeded": "completed",
    "failed": "failed",
    "skipped": "cancelled",
}

ATTEMPT_STATUS_BY_TASK_STATUS = {
    "created": "created",
    "queued": "created",
    "claimed": "running",
    "running": "running",
    "paused": "running",
    "waiting_for_decision": "running",
    "retry_scheduled": "retry_scheduled",
    "completed": "completed",
    "failed": "failed",
    "dead_lettered": "dead_lettered",
    "cancelled": "cancelled",
}


@dataclass(frozen=True)
class TaskTransitionResult:
    lifecycle_task: TaskLifecycleRecord
    attempt: TaskAttemptRecord | None
    event: TaskLifecycleEvent
    outcome: str
    duplicate: bool = False


def organization_for_run(run: Run) -> Organization:
    if run.organization_id:
        return run.organization
    if run.graph_version.graph.organization_id:
        return run.graph_version.graph.organization
    if run.owner.default_organization_id:
        return run.owner.default_organization
    raise ValueError("Run does not have an organization for task lifecycle state.")


def lifecycle_external_key(run: Run, node_id: str) -> str:
    return f"{run.id}:{node_id or '__run__'}"


def task_title_for_node(run: Run, node_id: str, node_type: str = "") -> str:
    graph_json = run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else None
    if not graph_json and run.graph_version_id:
        graph_json = run.graph_version.graph_json if isinstance(run.graph_version.graph_json, dict) else None
    for node in _extract_graph_nodes(graph_json or {}):
        if str(node.get("id") or "") != node_id:
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        label = str(node.get("name") or data.get("label") or data.get("name") or "").strip()
        if label:
            return f"{label} task"
    return f"{node_id or 'Run'} task"


def ensure_lifecycle_task(
    *,
    run: Run,
    node_id: str,
    node_type: str = "",
    title: str = "",
    current_node_run: NodeRun | None = None,
) -> TaskLifecycleRecord:
    organization = organization_for_run(run)
    node_id = str(node_id or "__run__").strip() or "__run__"
    external_key = lifecycle_external_key(run, node_id)
    defaults = {
        "run": run,
        "source_node_id": node_id,
        "node_type": node_type,
        "title": title or task_title_for_node(run, node_id, node_type),
        "priority": _priority_for_run(run),
        "summary": _summary_for_status(run=run, node_id=node_id, status="created"),
        "current_node_run": current_node_run,
        "last_transition_at": timezone.now(),
    }
    task, _ = TaskLifecycleRecord.objects.get_or_create(
        organization=organization,
        external_key=external_key,
        defaults=defaults,
    )
    update_fields: list[str] = []
    if task.run_id != run.id:
        task.run = run
        update_fields.append("run")
    if node_type and task.node_type != node_type:
        task.node_type = node_type
        update_fields.append("node_type")
    if title and task.title != title:
        task.title = title
        update_fields.append("title")
    if current_node_run is not None and task.current_node_run_id != current_node_run.id:
        task.current_node_run = current_node_run
        update_fields.append("current_node_run")
    if update_fields:
        task.save(update_fields=sorted(set(update_fields + ["updated_at"])))
    return task


def initialize_lifecycle_tasks_for_run(run: Run, *, source: str = "run_start") -> list[TaskLifecycleRecord]:
    tasks: list[TaskLifecycleRecord] = []
    graph_json = run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else run.graph_version.graph_json
    for node in _extract_graph_nodes(graph_json if isinstance(graph_json, dict) else {}):
        node_id = str(node.get("id") or "").strip()
        if not node_id or not _is_executable_node(node):
            continue
        node_type = _node_type(node)
        task = ensure_lifecycle_task(run=run, node_id=node_id, node_type=node_type)
        tasks.append(task)
        transition_task_lifecycle(
            run=run,
            node_id=node_id,
            node_type=node_type,
            to_status="created",
            attempt_number=1,
            source=source,
            idempotency_key=f"task:{run.id}:{node_id}:created:1",
            reason="task initialized from graph",
        )
    return tasks


def transition_task_lifecycle(
    *,
    run: Run,
    node_id: str,
    to_status: str,
    attempt_number: int = 1,
    node_type: str = "",
    source: str,
    idempotency_key: str,
    reason: str = "",
    event_type: str = "task_lifecycle.transition",
    node_run: NodeRun | None = None,
    decision: DecisionRecord | None = None,
    owner_component: str = "backend",
    parent_attempt_number: int | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: Any = None,
    allow_late: bool = False,
) -> TaskTransitionResult:
    if to_status not in TASK_STATUSES:
        raise ValueError(f"Unsupported task lifecycle status: {to_status}")
    if not idempotency_key.strip():
        raise ValueError("Task lifecycle transition requires an idempotency key.")
    effective_time = occurred_at or timezone.now()
    safe_payload = redact_payload(payload or {})

    with transaction.atomic():
        run = Run.objects.select_for_update(of=("self",)).select_related(
            "owner",
            "organization",
            "graph_version__graph__organization",
        ).get(id=run.id)
        task = ensure_lifecycle_task(
            run=run,
            node_id=node_id,
            node_type=node_type,
            current_node_run=node_run,
        )
        existing_event = TaskLifecycleEvent.objects.filter(
            organization_id=task.organization_id,
            idempotency_key=idempotency_key,
        ).first()
        if existing_event is not None:
            return TaskTransitionResult(
                lifecycle_task=task,
                attempt=_attempt_for_number(task, existing_event.attempt_number),
                event=existing_event,
                outcome="duplicate",
                duplicate=True,
            )

        from_status = task.status
        outcome = _transition_outcome(
            task=task,
            run=run,
            to_status=to_status,
            attempt_number=attempt_number,
            allow_late=allow_late,
        )
        attempt: TaskAttemptRecord | None = None
        if outcome == "accepted":
            try:
                attempt = _ensure_attempt(
                    task=task,
                    run=run,
                    attempt_number=attempt_number,
                    parent_attempt_number=parent_attempt_number,
                    node_run=node_run,
                    owner_component=owner_component,
                    idempotency_key=idempotency_key,
                    status=ATTEMPT_STATUS_BY_TASK_STATUS.get(to_status, "created"),
                    event_time=effective_time,
                    reason=reason,
                )
            except ValueError as exc:
                outcome = "invalid"
                reason = reason or str(exc)
            else:
                _apply_task_transition(
                    task=task,
                    to_status=to_status,
                    attempt_number=attempt_number,
                    node_run=node_run,
                    decision=decision,
                    reason=reason,
                    event_time=effective_time,
                    payload=safe_payload,
                )
        elif outcome == "stale":
            task.stale_event_count += 1
            task.save(update_fields=["stale_event_count", "updated_at"])
        elif outcome == "late":
            task.late_event_count += 1
            task.save(update_fields=["late_event_count", "updated_at"])

        event = TaskLifecycleEvent.objects.create(
            organization_id=task.organization_id,
            run=run,
            lifecycle_task=task,
            idempotency_key=idempotency_key,
            source=source,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            attempt_number=max(int(attempt_number or 1), 1),
            outcome=outcome,
            reason=reason,
            payload=safe_payload,
            occurred_at=effective_time,
        )
        return TaskTransitionResult(
            lifecycle_task=task,
            attempt=attempt,
            event=event,
            outcome=outcome,
        )


def transition_from_node_run(
    *,
    run: Run,
    node_run: NodeRun,
    source: str,
    idempotency_key: str,
    reason: str = "",
    occurred_at: Any = None,
    allow_late: bool = False,
) -> TaskTransitionResult:
    return transition_task_lifecycle(
        run=run,
        node_id=node_run.node_id,
        node_type=node_run.node_type,
        to_status=NODE_TO_TASK_STATUS.get(node_run.status, "running"),
        attempt_number=node_run.attempt,
        source=source,
        idempotency_key=idempotency_key,
        reason=reason or f"node_run {node_run.status}",
        node_run=node_run,
        owner_component="engine",
        payload={
            "node_run_id": str(node_run.id),
            "node_status": node_run.status,
            "error_json": node_run.error_json,
        },
        occurred_at=occurred_at,
        allow_late=allow_late,
    )


def record_retry_operation(
    *,
    run: Run,
    operation_type: str,
    idempotency_key: str,
    attempt_number: int,
    max_attempts: int,
    retry_delay_ms: int,
    retry_reason: str,
    last_error: str,
    owning_component: str,
    retry_class: str,
    terminal_fallback: str,
    node_id: str = "",
    node_type: str = "",
    next_scheduled_at: Any = None,
    parent_attempt_number: int | None = None,
    payload: dict[str, Any] | None = None,
) -> RetryOperation:
    if retry_class not in {choice[0] for choice in RetryOperation.RETRY_CLASS_CHOICES}:
        retry_class = "transport"
    if not next_scheduled_at and retry_delay_ms > 0:
        next_scheduled_at = timezone.now() + timedelta(milliseconds=retry_delay_ms)

    with transaction.atomic():
        run = Run.objects.select_for_update(of=("self",)).select_related(
            "owner",
            "organization",
            "graph_version__graph__organization",
        ).get(id=run.id)
        task: TaskLifecycleRecord | None = None
        attempt: TaskAttemptRecord | None = None
        if node_id:
            transition = transition_task_lifecycle(
                run=run,
                node_id=node_id,
                node_type=node_type,
                to_status="retry_scheduled",
                attempt_number=attempt_number,
                parent_attempt_number=parent_attempt_number,
                source=owning_component,
                idempotency_key=f"{idempotency_key}:task",
                reason=retry_reason,
                owner_component=owning_component,
                payload=payload or {},
            )
            task = transition.lifecycle_task
            attempt = transition.attempt
        organization = organization_for_run(run)
        status_value = "scheduled"
        if attempt_number >= max_attempts and terminal_fallback in {"dead_letter", "dead_lettered"}:
            status_value = "dead_lettered"
        elif attempt_number >= max_attempts:
            status_value = "exhausted"
        retry_op, _ = RetryOperation.objects.update_or_create(
            organization=organization,
            idempotency_key=idempotency_key,
            defaults={
                "run": run,
                "lifecycle_task": task,
                "attempt": attempt,
                "operation_type": operation_type,
                "attempt_number": max(int(attempt_number or 1), 1),
                "max_attempts": max(int(max_attempts or 1), 1),
                "retry_delay_ms": max(int(retry_delay_ms or 0), 0),
                "retry_reason": retry_reason,
                "last_error": last_error,
                "owning_component": owning_component,
                "next_scheduled_at": next_scheduled_at,
                "terminal_fallback": terminal_fallback,
                "retry_class": retry_class,
                "status": status_value,
            },
        )
        if status_value == "dead_lettered" and task is not None:
            dead_letter_task(
                task=task,
                reason=retry_reason or "retry exhausted",
                last_error=last_error,
                attempt_count=attempt_number,
                recovery_options=["replay_intent", "force_fail_run", "force_cancel_run"],
                idempotency_key=f"{idempotency_key}:dead_letter",
                source=owning_component,
            )
        return retry_op


def dead_letter_task(
    *,
    task: TaskLifecycleRecord,
    reason: str,
    last_error: str,
    attempt_count: int,
    recovery_options: list[str],
    idempotency_key: str,
    source: str,
    intent_id: UUID | None = None,
    stream_message_id: str = "",
) -> TaskDeadLetterRecord:
    transition_task_lifecycle(
        run=task.run,
        node_id=task.source_node_id,
        node_type=task.node_type,
        to_status="dead_lettered",
        attempt_number=max(attempt_count, task.current_attempt),
        source=source,
        idempotency_key=idempotency_key,
        reason=reason,
        payload={
            "last_error": last_error,
            "recovery_options": recovery_options,
            "intent_id": str(intent_id) if intent_id else "",
            "stream_message_id": stream_message_id,
        },
    )
    dead_letter, _ = TaskDeadLetterRecord.objects.update_or_create(
        lifecycle_task=task,
        intent_id=intent_id,
        defaults={
            "run": task.run,
            "stream_message_id": stream_message_id,
            "reason": reason,
            "attempt_count": max(int(attempt_count or 0), 0),
            "last_error": last_error,
            "recovery_options": recovery_options,
            "status": "active",
        },
    )
    return dead_letter


def mark_run_tasks_terminal(
    *,
    run: Run,
    status_value: str,
    source: str,
    reason: str,
) -> None:
    if status_value not in {"failed", "cancelled"}:
        raise ValueError("Run task terminal marker only supports failed or cancelled.")
    for task in TaskLifecycleRecord.objects.filter(run=run).exclude(
        status__in=TERMINAL_TASK_STATUSES
    ):
        transition_task_lifecycle(
            run=run,
            node_id=task.source_node_id,
            node_type=task.node_type,
            to_status=status_value,
            attempt_number=task.current_attempt,
            source=source,
            idempotency_key=f"task:{run.id}:{task.source_node_id}:{status_value}:{source}:{timezone.now().timestamp()}",
            reason=reason,
        )


def _transition_outcome(
    *,
    task: TaskLifecycleRecord,
    run: Run,
    to_status: str,
    attempt_number: int,
    allow_late: bool,
) -> str:
    normalized_attempt = max(int(attempt_number or 1), 1)
    if normalized_attempt < task.current_attempt:
        return "stale"
    if (
        run.status in {"failed", "canceled"}
        and to_status == "completed"
        and not allow_late
    ):
        return "late"
    if to_status not in ALLOWED_TASK_TRANSITIONS.get(task.status, set()):
        return "out_of_order"
    if task.status in TERMINAL_TASK_STATUSES and to_status != task.status:
        return "out_of_order"
    return "accepted"


def _ensure_attempt(
    *,
    task: TaskLifecycleRecord,
    run: Run,
    attempt_number: int,
    parent_attempt_number: int | None,
    node_run: NodeRun | None,
    owner_component: str,
    idempotency_key: str,
    status: str,
    event_time: Any,
    reason: str,
) -> TaskAttemptRecord:
    attempt_number = max(int(attempt_number or 1), 1)
    parent_attempt = None
    if attempt_number > 1:
        parent_lookup = parent_attempt_number or attempt_number - 1
        parent_attempt = TaskAttemptRecord.objects.filter(
            lifecycle_task=task,
            attempt_number=parent_lookup,
        ).first()
        if parent_attempt is None:
            raise ValueError("Retry attempts must have a parent attempt.")
    attempt, _ = TaskAttemptRecord.objects.get_or_create(
        lifecycle_task=task,
        attempt_number=attempt_number,
        defaults={
            "run": run,
            "parent_attempt": parent_attempt,
            "node_run": node_run,
            "idempotency_key": idempotency_key,
            "owner_component": owner_component,
            "status": status,
            "retry_reason": reason if status == "retry_scheduled" else "",
            "last_error": reason if status in {"failed", "dead_lettered"} else "",
            "started_at": event_time if status == "running" else None,
            "ended_at": event_time if status in {"completed", "failed", "dead_lettered", "cancelled"} else None,
        },
    )
    update_fields: list[str] = []
    if node_run is not None and attempt.node_run_id != node_run.id:
        attempt.node_run = node_run
        update_fields.append("node_run")
    if status and attempt.status != status:
        attempt.status = status
        update_fields.append("status")
    if owner_component and attempt.owner_component != owner_component:
        attempt.owner_component = owner_component
        update_fields.append("owner_component")
    if status == "running" and attempt.started_at is None:
        attempt.started_at = event_time
        update_fields.append("started_at")
    if status in {"completed", "failed", "dead_lettered", "cancelled"} and attempt.ended_at is None:
        attempt.ended_at = event_time
        update_fields.append("ended_at")
    if reason and status in {"retry_scheduled", "failed", "dead_lettered"}:
        if attempt.retry_reason != reason and status == "retry_scheduled":
            attempt.retry_reason = reason
            update_fields.append("retry_reason")
        if attempt.last_error != reason and status in {"failed", "dead_lettered"}:
            attempt.last_error = reason
            update_fields.append("last_error")
    if update_fields:
        attempt.save(update_fields=sorted(set(update_fields + ["updated_at"])))
    return attempt


def _attempt_for_number(
    task: TaskLifecycleRecord,
    attempt_number: int,
) -> TaskAttemptRecord | None:
    return TaskAttemptRecord.objects.filter(
        lifecycle_task=task,
        attempt_number=attempt_number,
    ).first()


def _apply_task_transition(
    *,
    task: TaskLifecycleRecord,
    to_status: str,
    attempt_number: int,
    node_run: NodeRun | None,
    decision: DecisionRecord | None,
    reason: str,
    event_time: Any,
    payload: dict[str, Any],
) -> None:
    update_fields: list[str] = []
    if task.status != to_status:
        task.status = to_status
        update_fields.append("status")
    if task.current_attempt != max(int(attempt_number or 1), 1):
        task.current_attempt = max(int(attempt_number or 1), 1)
        update_fields.append("current_attempt")
    if node_run is not None and task.current_node_run_id != node_run.id:
        task.current_node_run = node_run
        update_fields.append("current_node_run")
    if decision is not None and task.current_decision_id != decision.id:
        task.current_decision = decision
        update_fields.append("current_decision")
    if to_status == "running" and task.started_at is None:
        task.started_at = event_time
        update_fields.append("started_at")
    if to_status in TERMINAL_TASK_STATUSES and task.ended_at is None:
        task.ended_at = event_time
        update_fields.append("ended_at")
    if to_status == "retry_scheduled":
        task.retry_metadata = payload
        update_fields.append("retry_metadata")
    if to_status == "dead_lettered":
        task.recovery_options = payload.get("recovery_options") or task.recovery_options or [
            "inspect_run"
        ]
        task.unresolved_error = reason or str(payload.get("last_error") or "")
        update_fields.extend(["recovery_options", "unresolved_error"])
    elif to_status in {"failed"} and reason:
        task.unresolved_error = reason
        update_fields.append("unresolved_error")
    if task.priority != _priority_for_task_status(to_status):
        task.priority = _priority_for_task_status(to_status)
        update_fields.append("priority")
    summary = _summary_for_status(run=task.run, node_id=task.source_node_id, status=to_status, reason=reason)
    if task.summary != summary:
        task.summary = summary
        update_fields.append("summary")
    task.last_transition_at = event_time
    update_fields.append("last_transition_at")
    if update_fields:
        task.save(update_fields=sorted(set(update_fields + ["updated_at"])))


def _extract_graph_nodes(graph_json: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph_json.get("nodes", [])
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def _node_type(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(node.get("type") or data.get("type") or data.get("node_type") or "").strip()


def _is_executable_node(node: dict[str, Any]) -> bool:
    node_type = _node_type(node).lower()
    return node_type not in {"input", "output", "trigger", "note", "comment"}


def _priority_for_run(run: Run) -> str:
    if run.status == "paused":
        return "high"
    if run.status == "failed":
        return "urgent"
    return "normal"


def _priority_for_task_status(status_value: str) -> str:
    if status_value in {"dead_lettered", "failed"}:
        return "urgent"
    if status_value in {"waiting_for_decision", "paused", "retry_scheduled"}:
        return "high"
    return "normal"


def _summary_for_status(
    *,
    run: Run,
    node_id: str,
    status: str,
    reason: str = "",
) -> str:
    if status == "waiting_for_decision":
        return f"{node_id} is waiting for a human decision."
    if status == "retry_scheduled":
        return f"{node_id} has a bounded retry scheduled."
    if status == "dead_lettered":
        return f"{node_id} is dead-lettered: {reason or 'operator recovery required'}."
    if status == "failed":
        return f"{node_id} failed{': ' + reason if reason else ''}."
    if status == "completed":
        return f"{node_id} completed."
    if status == "running":
        return f"{node_id} is running."
    return f"{node_id} is {status.replace('_', ' ')}."
