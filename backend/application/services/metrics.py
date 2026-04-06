"""
Lightweight in-memory metrics for API, worker, and queue visibility.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from threading import Lock

from django.utils import timezone


@dataclass(frozen=True)
class RunMetricsSnapshot:
    run_started_total: int
    run_completed_total: int
    run_failed_total: int
    run_canceled_total: int
    run_success_rate: float | None
    run_latency_ms_p50: float | None
    run_latency_ms_p95: float | None
    window_size: int
    generated_at: str


@dataclass(frozen=True)
class WebSocketMetricsSnapshot:
    active_connections: int
    connection_failures_total: int
    messages_sent_total: int
    messages_dropped_total: int
    message_rate_per_minute: float
    generated_at: str


_lock = Lock()
_counters: Counter[str] = Counter()
_latencies_ms: deque[int] = deque(maxlen=1000)
_ws_message_timestamps: deque[float] = deque(maxlen=5000)


def record_run_started() -> None:
    with _lock:
        _counters["run_started_total"] += 1


def record_run_completed(status: str, duration_ms: int | None) -> None:
    with _lock:
        _counters["run_completed_total"] += 1
        if status == "failed":
            _counters["run_failed_total"] += 1
        elif status == "canceled":
            _counters["run_canceled_total"] += 1
        if duration_ms is not None:
            _latencies_ms.append(duration_ms)


def _prune_ws_message_timestamps(now_ts: float) -> None:
    while _ws_message_timestamps and (now_ts - _ws_message_timestamps[0]) > 60:
        _ws_message_timestamps.popleft()


def record_ws_connected() -> None:
    with _lock:
        _counters["ws_active_connections"] += 1


def record_ws_disconnected() -> None:
    with _lock:
        _counters["ws_active_connections"] = max(0, _counters["ws_active_connections"] - 1)


def record_ws_connection_failure() -> None:
    with _lock:
        _counters["ws_connection_failures_total"] += 1


def record_ws_message_sent() -> None:
    now_ts = time.time()
    with _lock:
        _counters["ws_messages_sent_total"] += 1
        _ws_message_timestamps.append(now_ts)
        _prune_ws_message_timestamps(now_ts)


def record_ws_message_dropped() -> None:
    with _lock:
        _counters["ws_messages_dropped_total"] += 1


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * percentile
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return float(d0 + d1)


def get_run_metrics_snapshot() -> RunMetricsSnapshot:
    with _lock:
        started = int(_counters.get("run_started_total", 0))
        completed = int(_counters.get("run_completed_total", 0))
        failed = int(_counters.get("run_failed_total", 0))
        canceled = int(_counters.get("run_canceled_total", 0))
        latencies = list(_latencies_ms)

    success_rate = None
    if completed > 0:
        success_rate = max(0.0, float(completed - failed - canceled) / float(completed))

    return RunMetricsSnapshot(
        run_started_total=started,
        run_completed_total=completed,
        run_failed_total=failed,
        run_canceled_total=canceled,
        run_success_rate=success_rate,
        run_latency_ms_p50=_percentile(latencies, 0.5),
        run_latency_ms_p95=_percentile(latencies, 0.95),
        window_size=len(latencies),
        generated_at=timezone.now().isoformat(),
    )


def get_websocket_metrics_snapshot() -> WebSocketMetricsSnapshot:
    now_ts = time.time()
    with _lock:
        _prune_ws_message_timestamps(now_ts)
        active_connections = int(_counters.get("ws_active_connections", 0))
        connection_failures = int(_counters.get("ws_connection_failures_total", 0))
        messages_sent = int(_counters.get("ws_messages_sent_total", 0))
        messages_dropped = int(_counters.get("ws_messages_dropped_total", 0))
        recent_messages = len(_ws_message_timestamps)

    return WebSocketMetricsSnapshot(
        active_connections=active_connections,
        connection_failures_total=connection_failures,
        messages_sent_total=messages_sent,
        messages_dropped_total=messages_dropped,
        message_rate_per_minute=float(recent_messages),
        generated_at=timezone.now().isoformat(),
    )
