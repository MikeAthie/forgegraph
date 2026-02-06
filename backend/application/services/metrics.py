"""
Lightweight in-memory metrics for API, worker, and queue visibility.
"""

from __future__ import annotations

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


_lock = Lock()
_counters: Counter[str] = Counter()
_latencies_ms: deque[int] = deque(maxlen=1000)


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
