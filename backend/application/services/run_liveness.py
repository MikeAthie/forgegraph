from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.metrics import record_run_completed
from infrastructure.orm.models import Run, RunEvent


def engine_instance_label() -> str:
    return f"{settings.ENGINE_HOST}:{settings.ENGINE_PORT}"


def recovery_state_for_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "running":
        return "active"
    if normalized == "paused":
        return "awaiting_input"
    return "idle"


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
        stalled_since = run.last_progress_at or run.started_at or effective_now
        message = (
            "Run stalled with no backend-observed progress "
            f"since {stalled_since.isoformat()}. "
            "The control plane reconciled it automatically."
        )
        with transaction.atomic():
            run.status = "failed"
            run.ended_at = effective_now
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
                payload={
                    "status": "failed",
                    "ended_at": effective_now.isoformat(),
                    "error_message": message,
                    "recovery_state": "stalled_failed",
                },
                trace_id=run.trace_id,
            )
        record_run_completed("failed", run.duration_ms)
        broadcast_run_updated(run)
        result.reconciled += 1

    return result
