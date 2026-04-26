from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from django.conf import settings
from django.utils import timezone

from application.services.metrics import get_api_metrics_snapshot
from application.services.structured_logging import log_event
from infrastructure.orm.models import RunQueueEntry

logger = logging.getLogger(__name__)

_log_lock = Lock()
_last_trigger_log_at: dict[str, float] = {}


@dataclass(frozen=True)
class BackendWatchdogSnapshot:
    enabled: bool
    healthy: bool
    triggers: list[str]
    recovery_action: str
    request_timeout_rate_per_minute: float
    request_timeout_threshold_per_minute: float
    request_timeout_threshold_ms: int
    queue_backlog: int
    queue_backlog_threshold: int
    generated_at: str
    errors: list[str] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "healthy": self.healthy,
            "triggers": self.triggers,
            "recovery_action": self.recovery_action,
            "request_timeout_rate_per_minute": self.request_timeout_rate_per_minute,
            "request_timeout_threshold_per_minute": (self.request_timeout_threshold_per_minute),
            "request_timeout_threshold_ms": self.request_timeout_threshold_ms,
            "queue_backlog": self.queue_backlog,
            "queue_backlog_threshold": self.queue_backlog_threshold,
            "errors": self.errors,
            "generated_at": self.generated_at,
        }


def evaluate_backend_watchdog() -> BackendWatchdogSnapshot:
    enabled = bool(getattr(settings, "BACKEND_WATCHDOG_ENABLED", True))
    request_timeout_threshold_per_minute = float(
        getattr(settings, "BACKEND_WATCHDOG_REQUEST_TIMEOUTS_PER_MINUTE", 10)
    )
    queue_backlog_threshold = int(
        getattr(
            settings,
            "BACKEND_WATCHDOG_QUEUE_BACKLOG_THRESHOLD",
            getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500),
        )
    )
    recovery_action = str(
        getattr(settings, "BACKEND_WATCHDOG_RECOVERY_ACTION", "container_restart")
    )

    api_metrics = get_api_metrics_snapshot()
    queue_backlog = 0
    errors: list[str] = []
    try:
        queue_backlog = RunQueueEntry.objects.filter(status__in=["pending", "processing"]).count()
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    triggers: list[str] = []
    if (
        request_timeout_threshold_per_minute > 0
        and api_metrics.timeout_like_rate_per_minute >= request_timeout_threshold_per_minute
    ):
        triggers.append("request_timeout_rate")
    if queue_backlog_threshold > 0 and queue_backlog >= queue_backlog_threshold:
        triggers.append("queue_backlog")

    snapshot = BackendWatchdogSnapshot(
        enabled=enabled,
        healthy=(not enabled) or not triggers,
        triggers=triggers if enabled else [],
        recovery_action=recovery_action if enabled and triggers else "none",
        request_timeout_rate_per_minute=api_metrics.timeout_like_rate_per_minute,
        request_timeout_threshold_per_minute=request_timeout_threshold_per_minute,
        request_timeout_threshold_ms=api_metrics.timeout_threshold_ms,
        queue_backlog=queue_backlog,
        queue_backlog_threshold=queue_backlog_threshold,
        errors=errors,
        generated_at=timezone.now().isoformat(),
    )
    if enabled and triggers:
        _log_watchdog_trigger(snapshot)
    return snapshot


def _log_watchdog_trigger(snapshot: BackendWatchdogSnapshot) -> None:
    now = time.monotonic()
    throttle_seconds = int(getattr(settings, "BACKEND_WATCHDOG_LOG_THROTTLE_SECONDS", 60))
    for trigger in snapshot.triggers:
        with _log_lock:
            last_logged_at = _last_trigger_log_at.get(trigger, 0.0)
            if now - last_logged_at < max(throttle_seconds, 1):
                continue
            _last_trigger_log_at[trigger] = now

        log_event(
            logger,
            logging.ERROR,
            "backend_watchdog_triggered",
            trigger=trigger,
            recovery_action=snapshot.recovery_action,
            request_timeout_rate_per_minute=snapshot.request_timeout_rate_per_minute,
            request_timeout_threshold_per_minute=(snapshot.request_timeout_threshold_per_minute),
            request_timeout_threshold_ms=snapshot.request_timeout_threshold_ms,
            queue_backlog=snapshot.queue_backlog,
            queue_backlog_threshold=snapshot.queue_backlog_threshold,
            errors=snapshot.errors,
        )
