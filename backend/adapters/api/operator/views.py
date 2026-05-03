from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID, uuid4

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.runs.views import get_engine_client_for_run, run_queryset_for_user
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.redaction import redact_payload
from application.services.run_liveness import touch_run_liveness
from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
    build_runtime_intent_redis_client,
    decode_runtime_intent_message,
)
from application.services.task_lifecycle import mark_run_tasks_terminal
from infrastructure.orm.models import (
    AuditLog,
    CostLedgerEntry,
    DecisionRecord,
    LLMUsage,
    MemoryObservation,
    RetryOperation,
    Run,
    RunCheckpoint,
    RunEvent,
    RuntimeIntentOutcome,
    TaskDeadLetterRecord,
    TaskLifecycleEvent,
    TaskLifecycleRecord,
    User,
)

logger = logging.getLogger(__name__)


def _ensure_operator(user: Any) -> Response | None:
    if not isinstance(user, User) or not has_min_role(user, "admin"):
        return error_response(
            code="FORBIDDEN",
            message="You don't have permission to use operator recovery controls.",
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _tenant_id(user: User) -> UUID:
    if user.default_organization_id is None:
        raise ValueError("Operator has no default organization.")
    return user.default_organization_id


def _run_for_operator(user: User, run_id: UUID) -> Run | None:
    return (
        run_queryset_for_user(user)
        .select_related("owner", "organization", "graph_version__graph")
        .filter(id=run_id)
        .first()
    )


def _operator_reason(request: Request, default: str = "") -> str:
    reason = str(request.data.get("reason") or default).strip()
    return reason[:1000]


def _lifecycle_task_payload(task: TaskLifecycleRecord) -> dict[str, Any]:
    latest_retry = task.retry_operations.order_by("-updated_at", "-created_at").first()
    latest_dead_letter = task.dead_letters.order_by("-created_at").first()
    return {
        "id": str(task.id),
        "run_id": str(task.run_id),
        "organization_id": str(task.organization_id),
        "source_node_id": task.source_node_id,
        "node_type": task.node_type,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "summary": task.summary,
        "current_attempt": task.current_attempt,
        "current_node_run_id": str(task.current_node_run_id) if task.current_node_run_id else None,
        "current_decision_id": str(task.current_decision_id) if task.current_decision_id else None,
        "retry_metadata": task.retry_metadata,
        "recovery_options": task.recovery_options,
        "unresolved_error": task.unresolved_error,
        "stale_event_count": task.stale_event_count,
        "late_event_count": task.late_event_count,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "ended_at": task.ended_at.isoformat() if task.ended_at else None,
        "last_transition_at": task.last_transition_at.isoformat()
        if task.last_transition_at
        else None,
        "latest_retry": _retry_payload(latest_retry) if latest_retry else None,
        "dead_letter": _dead_letter_payload(latest_dead_letter) if latest_dead_letter else None,
    }


def _retry_payload(retry: RetryOperation) -> dict[str, Any]:
    return {
        "id": str(retry.id),
        "operation_type": retry.operation_type,
        "idempotency_key": retry.idempotency_key,
        "attempt_number": retry.attempt_number,
        "max_attempts": retry.max_attempts,
        "retry_delay_ms": retry.retry_delay_ms,
        "retry_reason": retry.retry_reason,
        "last_error": retry.last_error,
        "owning_component": retry.owning_component,
        "next_scheduled_at": retry.next_scheduled_at.isoformat()
        if retry.next_scheduled_at
        else None,
        "terminal_fallback": retry.terminal_fallback,
        "retry_class": retry.retry_class,
        "status": retry.status,
        "updated_at": retry.updated_at.isoformat(),
    }


def _dead_letter_payload(dead_letter: TaskDeadLetterRecord) -> dict[str, Any]:
    return {
        "id": str(dead_letter.id),
        "task_id": str(dead_letter.lifecycle_task_id),
        "run_id": str(dead_letter.run_id),
        "intent_id": str(dead_letter.intent_id) if dead_letter.intent_id else None,
        "stream_message_id": dead_letter.stream_message_id,
        "reason": dead_letter.reason,
        "attempt_count": dead_letter.attempt_count,
        "last_error": dead_letter.last_error,
        "recovery_options": dead_letter.recovery_options,
        "status": dead_letter.status,
        "acknowledged_at": dead_letter.acknowledged_at.isoformat()
        if dead_letter.acknowledged_at
        else None,
        "acknowledgement_reason": dead_letter.acknowledgement_reason,
        "created_at": dead_letter.created_at.isoformat(),
    }


def _run_state_payload(run: Run) -> dict[str, Any]:
    tasks = (
        TaskLifecycleRecord.objects.filter(run=run)
        .select_related("current_node_run", "current_decision")
        .prefetch_related("retry_operations", "dead_letters")
        .order_by("source_node_id", "current_attempt")
    )
    pending_decisions = DecisionRecord.objects.filter(
        execution=run,
        status="pending",
    ).select_related("task", "task_lifecycle", "agent", "source_approval_task")
    checkpoint = RunCheckpoint.objects.filter(run=run).first()
    last_backend_mutation = (
        TaskLifecycleEvent.objects.filter(run=run).order_by("-occurred_at", "-created_at").first()
    )
    last_engine_callback = (
        RunEvent.objects.filter(run=run)
        .exclude(event_type__startswith="run.")
        .order_by("-created_at")
        .first()
    )
    unresolved_errors = [
        item
        for item in [run.error_message]
        + list(
            TaskLifecycleRecord.objects.filter(run=run)
            .exclude(unresolved_error="")
            .values_list("unresolved_error", flat=True)
        )
        if item
    ]
    cost_to_date = (
        CostLedgerEntry.objects.filter(execution=run)
        .aggregate(total=models.Sum("total_cost_usd"))
        .get("total")
    )
    if cost_to_date is None:
        cost_to_date = (
            LLMUsage.objects.filter(run=run).aggregate(total=models.Sum("cost_usd")).get("total")
            or 0
        )
    memory_writes = MemoryObservation.objects.filter(run_id=run.id).count()
    audit_rows = AuditLog.objects.filter(resource_id=str(run.id)).order_by("-created_at")[:20]
    return {
        "run": {
            "id": str(run.id),
            "status": run.status,
            "current_attempt": run.active_attempt_id,
            "recovery_state": run.recovery_state,
            "recovery_reason": run.recovery_reason,
            "resume_attempt_id": str(run.resume_attempt_id) if run.resume_attempt_id else None,
            "last_progress_at": run.last_progress_at.isoformat() if run.last_progress_at else None,
            "last_heartbeat_at": run.last_heartbeat_at.isoformat()
            if run.last_heartbeat_at
            else None,
            "engine_instance_id": run.engine_instance_id,
            "error_message": redact_payload(run.error_message),
        },
        "active_tasks": [
            _lifecycle_task_payload(task)
            for task in tasks
            if task.status not in {"completed", "failed", "dead_lettered", "cancelled"}
        ],
        "tasks": [_lifecycle_task_payload(task) for task in tasks],
        "pending_decisions": [
            {
                "id": str(decision.id),
                "status": decision.status,
                "decision_type": decision.decision_type,
                "task_id": str(decision.task_id) if decision.task_id else None,
                "task_lifecycle_id": str(decision.task_lifecycle_id)
                if decision.task_lifecycle_id
                else None,
                "requested_at": decision.requested_at.isoformat()
                if decision.requested_at
                else None,
            }
            for decision in pending_decisions
        ],
        "last_checkpoint": {
            "node_id": checkpoint.node_id,
            "step_index": checkpoint.step_index,
            "updated_at": checkpoint.updated_at.isoformat(),
        }
        if checkpoint
        else None,
        "last_backend_state_mutation": {
            "id": str(last_backend_mutation.id),
            "event_type": last_backend_mutation.event_type,
            "outcome": last_backend_mutation.outcome,
            "to_status": last_backend_mutation.to_status,
            "occurred_at": last_backend_mutation.occurred_at.isoformat(),
        }
        if last_backend_mutation
        else None,
        "last_engine_callback": {
            "id": str(last_engine_callback.id),
            "event_type": last_engine_callback.event_type,
            "created_at": last_engine_callback.created_at.isoformat(),
            "payload": redact_payload(last_engine_callback.payload),
        }
        if last_engine_callback
        else None,
        "unresolved_errors": unresolved_errors,
        "dead_letter_count": TaskDeadLetterRecord.objects.filter(run=run, status="active").count(),
        "cost_to_date": float(cost_to_date or 0),
        "memory_writes": memory_writes,
        "audit_timeline": [
            {
                "id": str(row.id),
                "action": row.action,
                "resource_type": row.resource_type,
                "created_at": row.created_at.isoformat(),
                "metadata": redact_payload(row.metadata),
            }
            for row in audit_rows
        ],
    }


class OperatorRunStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id: UUID) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        run = _run_for_operator(request.user, run_id)  # type: ignore[arg-type]
        if run is None:
            return error_response("NOT_FOUND", "Run not found.", status=404)
        return success_response(_run_state_payload(run))


class OperatorTaskStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, task_id: UUID) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        task = (
            TaskLifecycleRecord.objects.filter(organization_id=_tenant_id(user), id=task_id)
            .select_related("run", "current_node_run", "current_decision")
            .prefetch_related("events", "attempts", "retry_operations", "dead_letters")
            .first()
        )
        if task is None:
            return error_response("NOT_FOUND", "Task not found.", status=404)
        return success_response(
            {
                "task": _lifecycle_task_payload(task),
                "attempts": [
                    {
                        "id": str(attempt.id),
                        "attempt_number": attempt.attempt_number,
                        "parent_attempt_id": str(attempt.parent_attempt_id)
                        if attempt.parent_attempt_id
                        else None,
                        "status": attempt.status,
                        "owner_component": attempt.owner_component,
                        "last_error": attempt.last_error,
                    }
                    for attempt in task.attempts.order_by("attempt_number")
                ],
                "events": [
                    {
                        "id": str(event.id),
                        "event_type": event.event_type,
                        "from_status": event.from_status,
                        "to_status": event.to_status,
                        "outcome": event.outcome,
                        "reason": event.reason,
                        "occurred_at": event.occurred_at.isoformat(),
                    }
                    for event in task.events.order_by("-occurred_at")[:50]
                ],
            }
        )


class OperatorRuntimeIntentBacklogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        try:
            redis_client = build_runtime_intent_redis_client()
            groups = cast(list[dict[str, Any]], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM))
            group_payload: dict[str, str | int] = next(
                (
                    {
                        "name": str(group.get("name") or ""),
                        "pending": int(group.get("pending") or 0),
                        "lag": int(group.get("lag") or 0),
                    }
                    for group in groups
                    if str(group.get("name") or "") == RUNTIME_INTENT_CONSUMER_GROUP
                ),
                {"name": RUNTIME_INTENT_CONSUMER_GROUP, "pending": 0, "lag": 0},
            )
            pending = int(group_payload["pending"])
            lag = int(group_payload["lag"])
            stream_length = int(cast(Any, redis_client.xlen(RUNTIME_INTENT_STREAM)))
            dead_letter_count = int(cast(Any, redis_client.xlen(RUNTIME_INTENT_DEAD_LETTER_STREAM)))
            dead_letter_messages = cast(
                list[tuple[Any, dict[str, Any]]],
                redis_client.xrevrange(
                    RUNTIME_INTENT_DEAD_LETTER_STREAM,
                    max="+",
                    min="-",
                    count=25,
                ),
            )
            recent_dead_letters = [
                _dead_letter_stream_payload(message_id, fields)
                for message_id, fields in dead_letter_messages
            ]
        except Exception as exc:
            return error_response(
                "RUNTIME_INTENT_BACKLOG_UNAVAILABLE",
                str(exc),
                status=503,
            )
        return success_response(
            {
                "stream": RUNTIME_INTENT_STREAM,
                "dead_letter_stream": RUNTIME_INTENT_DEAD_LETTER_STREAM,
                "stream_length": stream_length,
                "pending": pending,
                "lag": lag,
                "backlog": pending + lag,
                "dead_letter_count": dead_letter_count,
                "recent_dead_letters": recent_dead_letters,
            }
        )


class OperatorDeadLetterListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        dead_letters = (
            TaskDeadLetterRecord.objects.filter(lifecycle_task__organization_id=_tenant_id(user))
            .select_related("lifecycle_task", "run")
            .order_by("-created_at")[:100]
        )
        outcomes = RuntimeIntentOutcome.objects.filter(
            models.Q(run__organization_id=_tenant_id(user)) | models.Q(run__isnull=True),
            outcome="dead_lettered",
        ).order_by("-processed_at")[:100]
        return success_response(
            {
                "task_dead_letters": [_dead_letter_payload(item) for item in dead_letters],
                "runtime_intent_outcomes": [
                    {
                        "intent_id": str(outcome.intent_id),
                        "run_id": str(outcome.run_id) if outcome.run_id else None,
                        "intent_type": outcome.intent_type,
                        "attempt_id": outcome.attempt_id,
                        "reason": outcome.reason,
                        "error_class": outcome.error_class,
                        "acknowledged_at": outcome.acknowledged_at.isoformat()
                        if outcome.acknowledged_at
                        else None,
                        "processed_at": outcome.processed_at.isoformat(),
                    }
                    for outcome in outcomes
                ],
            }
        )


class OperatorRuntimeIntentReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, intent_id: UUID) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        outcome = (
            RuntimeIntentOutcome.objects.filter(intent_id=intent_id).select_related("run").first()
        )
        if outcome is None:
            return error_response("NOT_FOUND", "Runtime intent outcome not found.", status=404)
        outcome_run = outcome.run
        if outcome_run is not None and outcome_run.organization_id != _tenant_id(user):
            return error_response("NOT_FOUND", "Runtime intent outcome not found.", status=404)
        if outcome.outcome != "dead_lettered":
            return error_response(
                "INTENT_REPLAY_CONFLICT",
                "Only dead-lettered intents can be replayed through this control.",
                status=409,
            )
        try:
            redis_client = build_runtime_intent_redis_client()
            replay_fields = _find_dead_letter_stream_fields(redis_client, intent_id)
            if replay_fields is None:
                return error_response(
                    "INTENT_PAYLOAD_UNAVAILABLE",
                    "Dead-letter payload is no longer available in Redis.",
                    status=409,
                )
            intent = decode_runtime_intent_message(
                {"intent": str(replay_fields.get("intent") or "")}
            )
            if (
                outcome_run is not None
                and outcome_run.active_attempt_id
                and intent.attempt_id != outcome_run.active_attempt_id
            ):
                return error_response(
                    "STALE_ATTEMPT",
                    "Cannot replay an intent for a stale attempt.",
                    status=409,
                )
            replay_message_id = redis_client.xadd(
                RUNTIME_INTENT_STREAM,
                {"intent": str(replay_fields.get("intent") or "")},
            )
        except Exception as exc:
            return error_response("INTENT_REPLAY_FAILED", str(exc), status=409)
        record_audit_log(
            actor=user,
            tenant_id=str(_tenant_id(user)),
            action="operator.intent_replayed",
            resource_type="runtime_intent",
            resource_id=str(intent_id),
            metadata={
                "reason": _operator_reason(request, "operator replay"),
                "message_id": str(replay_message_id),
            },
        )
        return success_response(
            {"intent_id": str(intent_id), "replay_message_id": str(replay_message_id)}
        )


class OperatorRuntimeIntentAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, intent_id: UUID) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        reason = _operator_reason(request, "operator acknowledged poison intent")
        if not reason:
            return error_response("VALIDATION_ERROR", "A reason is required.", status=400)
        outcome = (
            RuntimeIntentOutcome.objects.filter(intent_id=intent_id).select_related("run").first()
        )
        if outcome is None:
            return error_response("NOT_FOUND", "Runtime intent outcome not found.", status=404)
        outcome_run = outcome.run
        if outcome_run is not None and outcome_run.organization_id != _tenant_id(user):
            return error_response("NOT_FOUND", "Runtime intent outcome not found.", status=404)
        now = timezone.now()
        outcome.acknowledged_at = now
        outcome.acknowledged_by = user
        outcome.acknowledgement_reason = reason
        outcome.save(
            update_fields=[
                "acknowledged_at",
                "acknowledged_by",
                "acknowledgement_reason",
                "updated_at",
            ]
        )
        TaskDeadLetterRecord.objects.filter(intent_id=intent_id, status="active").update(
            status="acknowledged",
            acknowledged_at=now,
            acknowledged_by=user,
            acknowledgement_reason=reason,
        )
        record_audit_log(
            actor=user,
            tenant_id=str(_tenant_id(user)),
            action="operator.intent_acknowledged",
            resource_type="runtime_intent",
            resource_id=str(intent_id),
            metadata={"reason": reason},
        )
        return success_response({"intent_id": str(intent_id), "acknowledged_at": now.isoformat()})


class OperatorForceFailRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id: UUID) -> Response:
        return _force_terminal_run(request, run_id, status_value="failed")


class OperatorForceCancelRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id: UUID) -> Response:
        return _force_terminal_run(request, run_id, status_value="canceled")


class OperatorForceRehydrateRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id: UUID) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        reason = _operator_reason(request, "operator rehydrate from checkpoint")
        if not reason:
            return error_response("VALIDATION_ERROR", "A reason is required.", status=400)
        run = _run_for_operator(user, run_id)
        if run is None:
            return error_response("NOT_FOUND", "Run not found.", status=404)
        checkpoint = RunCheckpoint.objects.filter(run=run).first()
        if checkpoint is None:
            return error_response(
                "NO_CHECKPOINT",
                "Cannot force rehydrate without a backend-owned checkpoint.",
                status=409,
            )
        resume_attempt_id = uuid4()
        now = timezone.now()
        with transaction.atomic():
            locked_run = Run.objects.select_for_update().get(id=run.id)
            locked_run.status = "resume_requested"
            locked_run.resume_attempt_id = resume_attempt_id
            locked_run.resume_requested_at = now
            locked_run.recovery_state = "operator_rehydrate_requested"
            locked_run.recovery_reason = "operator_rehydrate"
            update_fields = [
                "status",
                "resume_attempt_id",
                "resume_requested_at",
                "recovery_state",
                "recovery_reason",
            ]
            update_fields.extend(
                touch_run_liveness(
                    locked_run,
                    event_time=now,
                    recovery_state="operator_rehydrate_requested",
                )
            )
            locked_run.save(update_fields=sorted(set(update_fields)))
            RunEvent.objects.create(
                run=locked_run,
                event_type="operator.force_rehydrate",
                payload={
                    "status": "resume_requested",
                    "resume_attempt_id": str(resume_attempt_id),
                    "checkpoint_node_id": checkpoint.node_id,
                    "reason": reason,
                    "category": "state",
                },
                trace_id=locked_run.trace_id,
            )
            record_audit_log(
                actor=user,
                tenant_id=str(_tenant_id(user)),
                action="operator.run_force_rehydrate",
                resource_type="run",
                resource_id=str(run.id),
                metadata={"reason": reason, "resume_attempt_id": str(resume_attempt_id)},
            )
        try:
            _, engine_client = get_engine_client_for_run(run=run)
            with engine_client as engine:
                engine.resume_run(
                    run_id=run.id,
                    node_id=checkpoint.node_id,
                    input_json={"operator_rehydrate": True, "reason": reason},
                    resume_attempt_id=str(resume_attempt_id),
                )
        except Exception as exc:
            Run.objects.filter(id=run.id, resume_attempt_id=resume_attempt_id).update(
                recovery_state="resume_dispatch_failed",
                recovery_reason="operator_rehydrate_dispatch_failed",
            )
            return error_response("REHYDRATE_DISPATCH_FAILED", str(exc), status=503)
        run.refresh_from_db()
        broadcast_run_updated(run)
        return success_response(_run_state_payload(run))


class OperatorWebSocketSubscribersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        from application.services.websocket_subscribers import get_websocket_subscriber_snapshot

        return success_response(get_websocket_subscriber_snapshot())


class OperatorOrgLoadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        denied = _ensure_operator(request.user)
        if denied is not None:
            return denied
        user = request.user
        assert isinstance(user, User)
        org_id = _tenant_id(user)
        from application.services.websocket_subscribers import get_websocket_subscriber_snapshot

        ws_snapshot = get_websocket_subscriber_snapshot()
        org_ws = next(
            (
                item
                for item in ws_snapshot.get("by_org", [])
                if str(item.get("organization_id") or "") == str(org_id)
            ),
            None,
        )
        return success_response(
            {
                "organization_id": str(org_id),
                "runs": {
                    "pending": Run.objects.filter(organization_id=org_id, status="pending").count(),
                    "running": Run.objects.filter(organization_id=org_id, status="running").count(),
                    "paused": Run.objects.filter(organization_id=org_id, status="paused").count(),
                    "resume_requested": Run.objects.filter(
                        organization_id=org_id, status="resume_requested"
                    ).count(),
                    "failed": Run.objects.filter(organization_id=org_id, status="failed").count(),
                },
                "tasks": list(
                    TaskLifecycleRecord.objects.filter(organization_id=org_id)
                    .values("status")
                    .annotate(count=models.Count("id"))
                    .order_by("status")
                ),
                "retry_operations": list(
                    RetryOperation.objects.filter(organization_id=org_id)
                    .values("status")
                    .annotate(count=models.Count("id"))
                    .order_by("status")
                ),
                "dead_letters": TaskDeadLetterRecord.objects.filter(
                    lifecycle_task__organization_id=org_id,
                    status="active",
                ).count(),
                "websocket": org_ws
                or {
                    "organization_id": str(org_id),
                    "connections": 0,
                    "limit": ws_snapshot.get("limits", {}).get("per_org"),
                    "remaining": ws_snapshot.get("limits", {}).get("per_org"),
                    "messages_sent": 0,
                    "messages_dropped": 0,
                    "messages_filtered": 0,
                    "slow_disconnects": 0,
                },
            }
        )


def _force_terminal_run(request: Request, run_id: UUID, *, status_value: str) -> Response:
    denied = _ensure_operator(request.user)
    if denied is not None:
        return denied
    user = request.user
    assert isinstance(user, User)
    reason = _operator_reason(request, f"operator forced run {status_value}")
    if not reason:
        return error_response("VALIDATION_ERROR", "A reason is required.", status=400)
    run = _run_for_operator(user, run_id)
    if run is None:
        return error_response("NOT_FOUND", "Run not found.", status=404)
    now = timezone.now()
    with transaction.atomic():
        locked_run = Run.objects.select_for_update().get(id=run.id)
        if locked_run.status not in {"succeeded", "failed", "canceled"}:
            locked_run.status = status_value
            locked_run.ended_at = now
            locked_run.error_message = reason
            locked_run.recovery_state = "operator_forced_terminal"
            locked_run.recovery_reason = f"operator_force_{status_value}"
            update_fields = [
                "status",
                "ended_at",
                "error_message",
                "recovery_state",
                "recovery_reason",
            ]
            update_fields.extend(
                touch_run_liveness(
                    locked_run,
                    event_time=now,
                    recovery_state="operator_forced_terminal",
                )
            )
            locked_run.save(update_fields=sorted(set(update_fields)))
            mark_run_tasks_terminal(
                run=locked_run,
                status_value="cancelled" if status_value == "canceled" else "failed",
                source="operator_api",
                reason=reason,
            )
            RetryOperation.objects.filter(
                run=locked_run, status__in=["scheduled", "running"]
            ).update(
                status="cancelled" if status_value == "canceled" else "failed",
                last_error=reason,
            )
            RunEvent.objects.create(
                run=locked_run,
                event_type=f"operator.force_{status_value}",
                payload={"status": status_value, "reason": reason, "category": "state"},
                trace_id=locked_run.trace_id,
            )
        record_audit_log(
            actor=user,
            tenant_id=str(_tenant_id(user)),
            action=f"operator.run_force_{status_value}",
            resource_type="run",
            resource_id=str(run.id),
            metadata={"reason": reason},
        )
    run.refresh_from_db()
    broadcast_run_updated(run)
    return success_response(_run_state_payload(run))


def _dead_letter_stream_payload(message_id: Any, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": str(message_id),
        "intent_id": str(fields.get("intent_id") or ""),
        "intent_type": str(fields.get("intent_type") or ""),
        "run_id": str(fields.get("run_id") or ""),
        "attempt_id": str(fields.get("attempt_id") or ""),
        "reason": str(fields.get("reason") or ""),
        "error_class": str(fields.get("error_class") or ""),
        "dead_lettered_at": str(fields.get("dead_lettered_at") or fields.get("timestamp") or ""),
    }


def _find_dead_letter_stream_fields(redis_client: Any, intent_id: UUID) -> dict[str, Any] | None:
    messages = cast(
        list[tuple[Any, dict[str, Any]]],
        redis_client.xrevrange(
            RUNTIME_INTENT_DEAD_LETTER_STREAM,
            max="+",
            min="-",
            count=500,
        ),
    )
    for _, fields in messages:
        if str(fields.get("intent_id") or "") == str(intent_id):
            return fields
        raw_intent = str(fields.get("intent") or "")
        try:
            payload = json.loads(raw_intent)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("intent_id") or "") == str(intent_id):
            return fields
    return None
