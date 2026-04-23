from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock

from django.utils import timezone


@dataclass(frozen=True)
class RuntimeTransportMetricsSnapshot:
    intent_publish_failures_total: int
    intent_received_total: int
    intent_applied_total: int
    intent_ack_total: int
    intent_reclaimed_total: int
    duplicate_intent_ignored_total: int
    dead_lettered_total: int
    stream_pending: int
    stream_backlog: int
    consumer_idle_ms: int
    oldest_pending_idle_ms: int
    dead_letter_count: int
    generated_at: str


_lock = Lock()
_counters: Counter[str] = Counter()
_gauges: dict[str, int] = {
    "stream_pending": 0,
    "stream_backlog": 0,
    "consumer_idle_ms": 0,
    "oldest_pending_idle_ms": 0,
    "dead_letter_count": 0,
}


def record_transport_event(event_type: str) -> None:
    normalized = str(event_type or "unknown").strip().lower() or "unknown"
    with _lock:
        _counters[f"event:{normalized}"] += 1


def update_transport_health(
    *,
    pending: int,
    backlog: int,
    consumer_idle_ms: int,
    oldest_pending_idle_ms: int,
    dead_letter_count: int,
) -> None:
    with _lock:
        _gauges["stream_pending"] = max(int(pending), 0)
        _gauges["stream_backlog"] = max(int(backlog), 0)
        _gauges["consumer_idle_ms"] = max(int(consumer_idle_ms), 0)
        _gauges["oldest_pending_idle_ms"] = max(int(oldest_pending_idle_ms), 0)
        _gauges["dead_letter_count"] = max(int(dead_letter_count), 0)


def get_runtime_transport_metrics_snapshot() -> RuntimeTransportMetricsSnapshot:
    with _lock:
        counters = dict(_counters)
        gauges = dict(_gauges)

    return RuntimeTransportMetricsSnapshot(
        intent_publish_failures_total=int(counters.get("event:intent_publish_failed", 0)),
        intent_received_total=int(counters.get("event:intent_received", 0)),
        intent_applied_total=int(counters.get("event:intent_applied", 0)),
        intent_ack_total=int(counters.get("event:intent_ack", 0)),
        intent_reclaimed_total=int(counters.get("event:intent_reclaimed", 0)),
        duplicate_intent_ignored_total=int(counters.get("event:duplicate_intent_ignored", 0)),
        dead_lettered_total=int(counters.get("event:dead_lettered", 0)),
        stream_pending=int(gauges.get("stream_pending", 0)),
        stream_backlog=int(gauges.get("stream_backlog", 0)),
        consumer_idle_ms=int(gauges.get("consumer_idle_ms", 0)),
        oldest_pending_idle_ms=int(gauges.get("oldest_pending_idle_ms", 0)),
        dead_letter_count=int(gauges.get("dead_letter_count", 0)),
        generated_at=timezone.now().isoformat(),
    )
