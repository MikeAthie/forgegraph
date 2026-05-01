"""
Run queue services for background execution.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from infrastructure.orm.models import Run, RunQueueEntry

logger = logging.getLogger(__name__)
RUN_QUEUE_WORKER_HEARTBEAT_CACHE_KEY = "forgegraph:run_queue:worker_heartbeat"


@dataclass(frozen=True)
class RunQueueSettings:
    max_per_tenant: int
    lock_timeout_seconds: int
    retry_delay_seconds: int


@dataclass(frozen=True)
class RunQueueWorkerHealth:
    active: bool
    worker_id: str = ""
    last_seen_at: datetime | None = None
    age_seconds: float | None = None
    error: str = ""


def get_run_queue_settings() -> RunQueueSettings:
    return RunQueueSettings(
        max_per_tenant=int(getattr(settings, "RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT", 5)),
        lock_timeout_seconds=int(getattr(settings, "RUN_QUEUE_WORKER_LOCK_SECONDS", 300)),
        retry_delay_seconds=int(getattr(settings, "RUN_QUEUE_RETRY_DELAY_SECONDS", 30)),
    )


def run_queue_worker_heartbeat_ttl_seconds() -> int:
    configured = int(
        getattr(
            settings,
            "RUN_QUEUE_WORKER_HEARTBEAT_TTL_SECONDS",
            max(get_run_queue_settings().lock_timeout_seconds * 2, 120),
        )
    )
    return max(configured, 1)


def record_run_queue_worker_heartbeat(worker_id: str) -> None:
    cache.set(
        RUN_QUEUE_WORKER_HEARTBEAT_CACHE_KEY,
        {
            "worker_id": str(worker_id or "").strip(),
            "last_seen_at": timezone.now().isoformat(),
        },
        timeout=run_queue_worker_heartbeat_ttl_seconds(),
    )


def get_run_queue_worker_health(*, now: datetime | None = None) -> RunQueueWorkerHealth:
    effective_now = now or timezone.now()
    try:
        payload = cache.get(RUN_QUEUE_WORKER_HEARTBEAT_CACHE_KEY)
    except Exception as exc:
        return RunQueueWorkerHealth(active=False, error=str(exc))

    if not isinstance(payload, dict):
        return RunQueueWorkerHealth(active=False)

    raw_last_seen = str(payload.get("last_seen_at") or "")
    try:
        last_seen_at = datetime.fromisoformat(raw_last_seen)
    except ValueError:
        return RunQueueWorkerHealth(
            active=False,
            worker_id=str(payload.get("worker_id") or ""),
            error="invalid heartbeat timestamp",
        )

    if timezone.is_naive(last_seen_at):
        last_seen_at = timezone.make_aware(last_seen_at, timezone.get_current_timezone())
    age_seconds = max(0.0, (effective_now - last_seen_at).total_seconds())
    return RunQueueWorkerHealth(
        active=age_seconds <= run_queue_worker_heartbeat_ttl_seconds(),
        worker_id=str(payload.get("worker_id") or ""),
        last_seen_at=last_seen_at,
        age_seconds=age_seconds,
    )


def log_run_queue_worker_unavailable(*, run_id: UUID, tenant_id: str) -> RunQueueWorkerHealth:
    health = get_run_queue_worker_health()
    if health.active:
        return health

    logger.error(
        "run_queue_worker_unavailable",
        extra={
            "run_id": str(run_id),
            "tenant_id": tenant_id,
            "queue_worker_last_seen_at": (
                health.last_seen_at.isoformat() if health.last_seen_at else None
            ),
            "queue_worker_age_seconds": health.age_seconds,
            "queue_worker_error": health.error,
            "warning": "RUN_QUEUE_ENABLED=true but no active process_run_queue worker heartbeat was found.",
        },
    )
    return health


def enqueue_run(
    run: Run,
    *,
    tenant_id: str | None = None,
    priority: int = 0,
    available_at: datetime | None = None,
    max_attempts: int | None = None,
) -> RunQueueEntry:
    tenant_uuid = run.organization_id or (UUID(tenant_id) if tenant_id else None)
    if tenant_uuid is None:
        tenant_uuid = run.owner.default_organization_id
    if tenant_uuid is None:
        tenant_uuid = UUID(str(run.owner_id))

    scheduled_at = available_at or timezone.now()
    defaults = {
        "tenant_id": tenant_uuid,
        "status": "pending",
        "priority": priority,
        "available_at": scheduled_at,
    }
    if max_attempts is not None:
        defaults["max_attempts"] = max_attempts

    entry, _ = RunQueueEntry.objects.update_or_create(run=run, defaults=defaults)
    if entry.status in {"failed", "completed"}:
        entry.status = "pending"
        entry.attempts = 0
        entry.available_at = scheduled_at
        entry.save(update_fields=["status", "attempts", "available_at"])
    return entry


def _active_tenant_run_count(tenant_id: UUID) -> int:
    return Run.objects.filter(
        Q(organization_id=tenant_id)
        | Q(organization__isnull=True, owner__default_organization_id=tenant_id),
        status__in=["running", "paused", "resume_requested"],
    ).count()


def release_stale_entries(lock_timeout_seconds: int | None = None) -> int:
    timeout = lock_timeout_seconds or get_run_queue_settings().lock_timeout_seconds
    cutoff = timezone.now() - timedelta(seconds=timeout)
    return RunQueueEntry.objects.filter(status="processing", locked_at__lt=cutoff).update(
        status="pending",
        locked_at=None,
        locked_by="",
    )


def claim_next_entry(
    *,
    worker_id: str,
    max_candidates: int = 10,
    settings_override: RunQueueSettings | None = None,
) -> RunQueueEntry | None:
    queue_settings = settings_override or get_run_queue_settings()
    now = timezone.now()
    candidates: Iterable[RunQueueEntry]

    with transaction.atomic():
        candidates = (
            RunQueueEntry.objects.select_for_update(skip_locked=True)
            .filter(status="pending", available_at__lte=now)
            .order_by("-priority", "created_at")[:max_candidates]
        )

        for entry in candidates:
            if entry.attempts >= entry.max_attempts:
                entry.status = "failed"
                entry.last_error = "Max attempts reached."
                entry.save(update_fields=["status", "last_error"])
                continue

            if queue_settings.max_per_tenant > 0:
                active_count = _active_tenant_run_count(entry.tenant_id)
                if active_count >= queue_settings.max_per_tenant:
                    entry.available_at = now + timedelta(seconds=queue_settings.retry_delay_seconds)
                    entry.save(update_fields=["available_at"])
                    continue

            entry.status = "processing"
            entry.locked_at = now
            entry.locked_by = worker_id
            entry.attempts += 1
            entry.save(update_fields=["status", "locked_at", "locked_by", "attempts"])
            return entry

    return None


def mark_completed(entry: RunQueueEntry) -> None:
    entry.status = "completed"
    entry.locked_at = None
    entry.locked_by = ""
    entry.save(update_fields=["status", "locked_at", "locked_by"])


def mark_failed(
    entry: RunQueueEntry,
    *,
    error_message: str,
    retryable: bool = False,
    settings_override: RunQueueSettings | None = None,
) -> None:
    queue_settings = settings_override or get_run_queue_settings()
    entry.last_error = error_message
    entry.locked_at = None
    entry.locked_by = ""
    if retryable and entry.attempts < entry.max_attempts:
        entry.status = "pending"
        entry.available_at = timezone.now() + timedelta(seconds=queue_settings.retry_delay_seconds)
        entry.save(update_fields=["status", "available_at", "last_error", "locked_at", "locked_by"])
        return

    entry.status = "failed"
    entry.save(update_fields=["status", "last_error", "locked_at", "locked_by"])
