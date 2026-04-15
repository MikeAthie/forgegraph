from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.engine_selection import get_default_engine_instance_id
from application.services.event_categories import EVENT_CATEGORY_STATE
from application.services.metrics import record_liveness_reconciliation, record_run_completed
from application.services.run_queue import enqueue_run
from application.services.run_snapshots import delete_snapshot, get_snapshot
from application.services.structured_logging import log_event
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import Run, RunEvent

logger = logging.getLogger(__name__)

RECOVERY_POLICY_FAIL = "fail"
RECOVERY_POLICY_RETRY = "retry"
RECOVERY_POLICY_RESUME = "resume"


def engine_instance_label() -> str:
    return get_default_engine_instance_id()


def recovery_state_for_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "running":
        return "active"
    if normalized == "paused":
        return "awaiting_input"
    if normalized == "resume_requested":
        return "resume_requested"
    return "idle"


@dataclass(frozen=True)
class CheckpointContext:
    checkpoint_available: bool
    checkpoint_node_id: str | None = None
    checkpoint_next_node: str | None = None
    checkpoint_attempt_id: str | None = None
    checkpoint_updated_at: datetime | None = None

    @classmethod
    def from_run(cls, run: Run) -> CheckpointContext:
        snapshot = get_snapshot(run.id)
        if snapshot is None:
            return cls(checkpoint_available=False)
        return cls(
            checkpoint_available=True,
            checkpoint_node_id=snapshot.last_completed_node,
            checkpoint_next_node=snapshot.next_node or None,
            checkpoint_attempt_id=snapshot.attempt_id or None,
            checkpoint_updated_at=snapshot.updated_at,
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "checkpoint_available": self.checkpoint_available,
            "checkpoint_node_id": self.checkpoint_node_id,
            "checkpoint_next_node": self.checkpoint_next_node,
            "checkpoint_attempt_id": self.checkpoint_attempt_id,
            "checkpoint_updated_at": self.checkpoint_updated_at.isoformat()
            if self.checkpoint_updated_at
            else None,
        }

    def summary(self) -> str:
        if not self.checkpoint_available:
            return "checkpoint=none"
        updated_at = (
            self.checkpoint_updated_at.isoformat(timespec="seconds")
            if self.checkpoint_updated_at
            else "unknown"
        )
        return (
            f"checkpoint=node:{self.checkpoint_node_id or 'unknown'} "
            f"next:{self.checkpoint_next_node or 'unknown'} "
            f"attempt:{self.checkpoint_attempt_id or 'unknown'} "
            f"updated:{updated_at}"
        )


def touch_run_liveness(
    run: Run,
    *,
    event_time: datetime | None = None,
    recovery_state: str | None = None,
    engine_instance_id: str | None = None,
) -> list[str]:
    effective_time = event_time or timezone.now()
    update_fields = ["last_progress_at", "last_heartbeat_at"]
    run.last_progress_at = effective_time
    run.last_heartbeat_at = effective_time

    if recovery_state is not None:
        run.recovery_state = recovery_state
        update_fields.append("recovery_state")
    if engine_instance_id is not None and engine_instance_id != run.engine_instance_id:
        run.engine_instance_id = engine_instance_id
        update_fields.append("engine_instance_id")

    return update_fields


@dataclass
class RunLivenessResult:
    scanned: int = 0
    reconciled: int = 0


def _stale_run_reason(run: Run) -> str:
    if str(run.status or "").strip().lower() == "resume_requested":
        return "resume_timeout"
    return "engine_stalled"


def _stalled_since(run: Run, now: datetime) -> datetime:
    return run.resume_requested_at or run.last_progress_at or run.started_at or now


def _normalized_recovery_policy(run: Run) -> str:
    normalized = str(getattr(run, "recovery_policy", "") or "").strip().lower()
    if normalized in {RECOVERY_POLICY_FAIL, RECOVERY_POLICY_RETRY, RECOVERY_POLICY_RESUME}:
        return normalized
    return RECOVERY_POLICY_FAIL


def _stale_run_error_message(
    *,
    stalled_since: datetime,
    checkpoint_context: CheckpointContext,
    recovery_policy: str,
    policy_note: str | None = None,
) -> str:
    parts = [
        "Run stalled with no backend-observed progress",
        f"since {stalled_since.isoformat()}",
        f"recovery_policy={recovery_policy}",
        checkpoint_context.summary(),
    ]
    if policy_note:
        parts.append(policy_note)
    return ". ".join(parts) + "."


def _stale_run_recovery_message(
    *,
    stalled_since: datetime,
    checkpoint_context: CheckpointContext,
    recovery_policy: str,
) -> str:
    return (
        "Run stalled with no backend-observed progress. "
        f"since {stalled_since.isoformat()}. "
        f"recovery_policy={recovery_policy}. "
        f"{checkpoint_context.summary()}. "
        "Backend queued recovery."
    )


def _fail_stale_run(
    run: Run,
    *,
    checkpoint_context: CheckpointContext,
    now: datetime,
    recovery_policy: str,
    recovery_reason: str,
    policy_note: str | None = None,
) -> bool:
    message = _stale_run_error_message(
        stalled_since=_stalled_since(run, now),
        checkpoint_context=checkpoint_context,
        recovery_policy=recovery_policy,
        policy_note=policy_note,
    )
    payload = {
        "status": "failed",
        "ended_at": now.isoformat(),
        "error_message": message,
        "recovery_state": "stalled_failed",
        "recovery_reason": recovery_reason,
        "recovery_policy": recovery_policy,
        "category": EVENT_CATEGORY_STATE,
        **checkpoint_context.as_payload(),
    }

    with transaction.atomic():
        run.status = "failed"
        run.ended_at = now
        run.error_message = message
        run.recovery_state = "stalled_failed"
        run.recovery_reason = recovery_reason
        run.resume_requested_at = None
        run.resume_attempt_id = None
        run.save(
            update_fields=[
                "status",
                "ended_at",
                "error_message",
                "recovery_state",
                "recovery_reason",
                "resume_requested_at",
                "resume_attempt_id",
            ]
        )
        RunEvent.objects.create(
            run=run,
            event_type="run.updated",
            payload=payload,
            trace_id=run.trace_id,
        )

    log_event(
        logger,
        logging.WARNING,
        "run_stale_reconciled",
        run_id=str(run.id),
        trace_id=run.trace_id,
        status="failed",
        node_id=checkpoint_context.checkpoint_node_id,
        error_message=message,
        recovery_policy=recovery_policy,
        recovery_reason=recovery_reason,
        checkpoint_available=checkpoint_context.checkpoint_available,
        checkpoint_next_node=checkpoint_context.checkpoint_next_node,
        checkpoint_attempt_id=checkpoint_context.checkpoint_attempt_id,
        checkpoint_updated_at=checkpoint_context.checkpoint_updated_at,
        engine_instance_id=run.engine_instance_id,
    )
    record_liveness_reconciliation(recovery_reason)
    record_run_completed("failed", run.duration_ms)
    broadcast_run_updated(run)
    return True


def _queue_stale_run_recovery(
    run: Run,
    *,
    checkpoint_context: CheckpointContext,
    now: datetime,
    recovery_policy: str,
    recovery_reason: str,
) -> bool:
    recovery_state = (
        "stalled_resume_pending"
        if recovery_policy == RECOVERY_POLICY_RESUME
        else "stalled_retry_pending"
    )
    message = _stale_run_recovery_message(
        stalled_since=_stalled_since(run, now),
        checkpoint_context=checkpoint_context,
        recovery_policy=recovery_policy,
    )

    with transaction.atomic():
        if recovery_policy == RECOVERY_POLICY_RETRY:
            delete_snapshot(run.id)

        run.status = "pending"
        run.ended_at = None
        run.output_json = None
        run.error_message = ""
        run.engine_instance_id = ""
        run.recovery_state = recovery_state
        run.recovery_reason = recovery_reason
        run.paused_node_id = None
        run.pause_state_json = None
        run.resume_requested_at = None
        run.resume_attempt_id = None
        run.last_progress_at = now
        run.last_heartbeat_at = now
        run.save(
            update_fields=[
                "status",
                "ended_at",
                "output_json",
                "error_message",
                "engine_instance_id",
                "recovery_state",
                "recovery_reason",
                "paused_node_id",
                "pause_state_json",
                "resume_requested_at",
                "resume_attempt_id",
                "last_progress_at",
                "last_heartbeat_at",
            ]
        )
        queue_entry = enqueue_run(
            run,
            tenant_id=get_tenant_id_for_user(run.owner),
            available_at=now,
        )
        RunEvent.objects.create(
            run=run,
            event_type="run.updated",
            payload={
                "status": "pending",
                "recovery_state": recovery_state,
                "recovery_reason": recovery_reason,
                "recovery_policy": recovery_policy,
                "recovery_action": recovery_policy,
                "recovery_message": message,
                "queue_status": queue_entry.status,
                "queue_available_at": queue_entry.available_at.isoformat(),
                "checkpoint_cleared": recovery_policy == RECOVERY_POLICY_RETRY,
                "category": EVENT_CATEGORY_STATE,
                **checkpoint_context.as_payload(),
            },
            trace_id=run.trace_id,
        )

    log_event(
        logger,
        logging.WARNING,
        "run_stale_requeued",
        run_id=str(run.id),
        trace_id=run.trace_id,
        status="pending",
        node_id=checkpoint_context.checkpoint_node_id,
        recovery_policy=recovery_policy,
        recovery_reason=recovery_reason,
        checkpoint_available=checkpoint_context.checkpoint_available,
        checkpoint_next_node=checkpoint_context.checkpoint_next_node,
        checkpoint_attempt_id=checkpoint_context.checkpoint_attempt_id,
        checkpoint_updated_at=checkpoint_context.checkpoint_updated_at,
        queue_status=queue_entry.status,
    )
    record_liveness_reconciliation(recovery_reason)
    broadcast_run_updated(run)
    return True


def apply_recovery_policy(
    run: Run,
    *,
    checkpoint_context: CheckpointContext,
    now: datetime,
) -> bool:
    recovery_policy = _normalized_recovery_policy(run)
    recovery_reason = _stale_run_reason(run)
    if recovery_policy == RECOVERY_POLICY_RETRY:
        if not getattr(settings, "RUN_QUEUE_ENABLED", False):
            return _fail_stale_run(
                run,
                checkpoint_context=checkpoint_context,
                now=now,
                recovery_policy=recovery_policy,
                recovery_reason=recovery_reason,
                policy_note="recovery policy 'retry' requires RUN_QUEUE_ENABLED=true; failed instead",
            )
        return _queue_stale_run_recovery(
            run,
            checkpoint_context=checkpoint_context,
            now=now,
            recovery_policy=recovery_policy,
            recovery_reason=recovery_reason,
        )

    if recovery_policy == RECOVERY_POLICY_RESUME:
        if not getattr(settings, "RUN_QUEUE_ENABLED", False):
            return _fail_stale_run(
                run,
                checkpoint_context=checkpoint_context,
                now=now,
                recovery_policy=recovery_policy,
                recovery_reason=recovery_reason,
                policy_note="recovery policy 'resume' requires RUN_QUEUE_ENABLED=true; failed instead",
            )
        if not checkpoint_context.checkpoint_available:
            return _fail_stale_run(
                run,
                checkpoint_context=checkpoint_context,
                now=now,
                recovery_policy=recovery_policy,
                recovery_reason="missing_checkpoint",
                policy_note=(
                    "recovery policy 'resume' requires a backend-owned checkpoint; failed instead"
                ),
            )
        return _queue_stale_run_recovery(
            run,
            checkpoint_context=checkpoint_context,
            now=now,
            recovery_policy=recovery_policy,
            recovery_reason=recovery_reason,
        )

    return _fail_stale_run(
        run,
        checkpoint_context=checkpoint_context,
        now=now,
        recovery_policy=recovery_policy,
        recovery_reason=recovery_reason,
    )


def resolve_stale_run(
    run: Run,
    *,
    now: datetime,
) -> bool:
    checkpoint_context = CheckpointContext.from_run(run)
    return apply_recovery_policy(
        run,
        checkpoint_context=checkpoint_context,
        now=now,
    )


def reconcile_stale_runs(
    *,
    stale_after_seconds: int | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> RunLivenessResult:
    effective_now = now or timezone.now()
    threshold_seconds = stale_after_seconds or int(
        getattr(settings, "RUN_LIVENESS_TIMEOUT_SECONDS", 300)
    )
    stale_before = effective_now - timedelta(seconds=max(threshold_seconds, 1))

    stale_runs = list(
        Run.objects.filter(
            status__in=["running", "resume_requested"],
            last_progress_at__lt=stale_before,
        ).order_by("last_progress_at", "resume_requested_at", "started_at")[: max(limit, 1)]
    )

    result = RunLivenessResult(scanned=len(stale_runs))
    for run in stale_runs:
        if resolve_stale_run(run, now=effective_now):
            result.reconciled += 1

    return result
