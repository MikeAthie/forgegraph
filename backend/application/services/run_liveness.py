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
from application.services.metrics import record_run_completed
from application.services.structured_logging import log_event
from infrastructure.orm.models import Run, RunCheckpoint, RunEvent

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
    return "idle"


@dataclass(frozen=True)
class CheckpointContext:
    checkpoint_available: bool
    checkpoint_node_id: str | None = None
    checkpoint_step_index: int | None = None
    checkpoint_updated_at: datetime | None = None

    @classmethod
    def from_run(cls, run: Run) -> CheckpointContext:
        try:
            checkpoint = run.checkpoint
        except RunCheckpoint.DoesNotExist:
            return cls(checkpoint_available=False)
        return cls(
            checkpoint_available=True,
            checkpoint_node_id=checkpoint.node_id,
            checkpoint_step_index=checkpoint.step_index,
            checkpoint_updated_at=checkpoint.updated_at,
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "checkpoint_available": self.checkpoint_available,
            "checkpoint_node_id": self.checkpoint_node_id,
            "checkpoint_step_index": self.checkpoint_step_index,
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
            f"step:{self.checkpoint_step_index if self.checkpoint_step_index is not None else 'unknown'} "
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


def apply_recovery_policy(
    run: Run,
    *,
    checkpoint_context: CheckpointContext,
    now: datetime,
) -> bool:
    recovery_policy = _normalized_recovery_policy(run)
    stalled_since = run.last_progress_at or run.started_at or now

    policy_note = None
    if recovery_policy != RECOVERY_POLICY_FAIL:
        policy_note = f"recovery policy '{recovery_policy}' is not implemented in this tranche; failed instead"

    message = _stale_run_error_message(
        stalled_since=stalled_since,
        checkpoint_context=checkpoint_context,
        recovery_policy=recovery_policy,
        policy_note=policy_note,
    )
    payload = {
        "status": "failed",
        "ended_at": now.isoformat(),
        "error_message": message,
        "recovery_state": "stalled_failed",
        "recovery_policy": recovery_policy,
        "category": EVENT_CATEGORY_STATE,
        **checkpoint_context.as_payload(),
    }

    with transaction.atomic():
        run.status = "failed"
        run.ended_at = now
        run.error_message = message
        run.recovery_state = "stalled_failed"
        run.save(
            update_fields=[
                "status",
                "ended_at",
                "error_message",
                "recovery_state",
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
        checkpoint_available=checkpoint_context.checkpoint_available,
        checkpoint_step_index=checkpoint_context.checkpoint_step_index,
        checkpoint_updated_at=checkpoint_context.checkpoint_updated_at,
        engine_instance_id=run.engine_instance_id,
    )
    record_run_completed("failed", run.duration_ms)
    broadcast_run_updated(run)
    return True


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
        Run.objects.filter(status="running", last_progress_at__lt=stale_before).order_by(
            "last_progress_at", "started_at"
        )[: max(limit, 1)]
    )

    result = RunLivenessResult(scanned=len(stale_runs))
    for run in stale_runs:
        if resolve_stale_run(run, now=effective_now):
            result.reconciled += 1

    return result
