"""
Lightweight in-memory metrics for API, worker, and queue visibility.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import UUID

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
    liveness_reconciled_total: int
    liveness_reconciled_by_reason: dict[str, int]
    stale_attempt_ignored_total: int
    stale_attempt_ignored_by_source: dict[str, int]
    generated_at: str


@dataclass(frozen=True)
class WebSocketMetricsSnapshot:
    active_connections: int
    connection_failures_total: int
    messages_sent_total: int
    messages_dropped_total: int
    messages_filtered_total: int
    slow_client_disconnects_total: int
    message_rate_per_minute: float
    send_latency_ms_p50: float | None
    send_latency_ms_p95: float | None
    generated_at: str


@dataclass(frozen=True)
class ApiMetricsSnapshot:
    requests_total: int
    server_errors_total: int
    timeout_like_requests_total: int
    timeout_like_rate_per_minute: float
    timeout_threshold_ms: int
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    callback_auth_failures_total: int
    callback_auth_failures_by_reason: dict[str, int]
    generated_at: str


_lock = Lock()
_counters: Counter[str] = Counter()
_latencies_ms: deque[int] = deque(maxlen=1000)
_ws_message_timestamps: deque[float] = deque(maxlen=5000)
_ws_send_latencies_ms: deque[int] = deque(maxlen=5000)
_api_latencies_ms: deque[int] = deque(maxlen=2000)
_api_timeout_like_timestamps: deque[float] = deque(maxlen=5000)
_api_timeout_threshold_ms = 5000


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


def record_liveness_reconciliation(reason: str) -> None:
    normalized_reason = str(reason or "unknown").strip().lower() or "unknown"
    with _lock:
        _counters["liveness_reconciled_total"] += 1
        _counters[f"liveness_reconciled_reason:{normalized_reason}"] += 1


def record_stale_attempt_ignored(source: str) -> None:
    normalized_source = str(source or "unknown").strip().lower() or "unknown"
    with _lock:
        _counters["stale_attempt_ignored_total"] += 1
        _counters[f"stale_attempt_ignored_source:{normalized_source}"] += 1


def record_callback_auth_failure(reason: str) -> None:
    normalized_reason = str(reason or "unknown").strip().lower() or "unknown"
    with _lock:
        _counters["callback_auth_failures_total"] += 1
        _counters[f"callback_auth_failure_reason:{normalized_reason}"] += 1


def record_api_request(
    *,
    status_code: int,
    duration_ms: int,
    timeout_like: bool = False,
    timeout_threshold_ms: int | None = None,
    path: str = "",
    method: str = "",
) -> None:
    now_ts = time.time()
    with _lock:
        global _api_timeout_threshold_ms
        if timeout_threshold_ms is not None and timeout_threshold_ms > 0:
            _api_timeout_threshold_ms = int(timeout_threshold_ms)
        _counters["api_requests_total"] += 1
        if status_code >= 500:
            _counters["api_server_errors_total"] += 1
        if timeout_like:
            _counters["api_timeout_like_requests_total"] += 1
            _api_timeout_like_timestamps.append(now_ts)
        _api_latencies_ms.append(max(duration_ms, 0))
    if path:
        record_service_metric_sample(
            metric_name="api_request_duration_ms",
            source="backend_middleware",
            value=max(duration_ms, 0),
            unit="ms",
            dimensions={
                "path": path,
                "method": method.upper(),
                "status_code": int(status_code),
                "timeout_like": bool(timeout_like),
            },
        )
        if status_code == 429:
            record_service_metric_sample(
                metric_name="api_rate_limit_breach",
                source="backend_middleware",
                value=1,
                unit="count",
                dimensions={"path": path, "method": method.upper()},
            )


def _prune_api_timeout_like_timestamps(now_ts: float) -> None:
    while _api_timeout_like_timestamps and (now_ts - _api_timeout_like_timestamps[0]) > 60:
        _api_timeout_like_timestamps.popleft()


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


def record_ws_message_sent(*, duration_ms: int | None = None) -> None:
    now_ts = time.time()
    with _lock:
        _counters["ws_messages_sent_total"] += 1
        _ws_message_timestamps.append(now_ts)
        if duration_ms is not None:
            _ws_send_latencies_ms.append(max(duration_ms, 0))
        _prune_ws_message_timestamps(now_ts)


def record_ws_message_dropped(reason: str = "unknown") -> None:
    normalized_reason = str(reason or "unknown").strip().lower() or "unknown"
    with _lock:
        _counters["ws_messages_dropped_total"] += 1
        _counters[f"ws_messages_dropped_reason:{normalized_reason}"] += 1


def record_ws_message_filtered() -> None:
    with _lock:
        _counters["ws_messages_filtered_total"] += 1


def record_ws_slow_client_disconnect(reason: str = "send_timeout") -> None:
    normalized_reason = str(reason or "send_timeout").strip().lower() or "send_timeout"
    with _lock:
        _counters["ws_slow_client_disconnects_total"] += 1
        _counters[f"ws_slow_client_disconnect_reason:{normalized_reason}"] += 1


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


def record_service_metric_sample(
    *,
    metric_name: str,
    source: str,
    value: float,
    unit: str = "",
    dimensions: dict[str, Any] | None = None,
    organization_id: UUID | str | None = None,
    run_id: UUID | str | None = None,
    observed_at: datetime | None = None,
) -> None:
    """Persist a backend-owned metric sample without making telemetry request-critical."""

    try:
        from infrastructure.orm.models import ServiceMetricSample

        ServiceMetricSample.objects.create(
            metric_name=str(metric_name or "").strip(),
            source=str(source or "").strip() or "unknown",
            organization_id=organization_id,
            run_id=run_id,
            value=float(value),
            unit=str(unit or "").strip(),
            dimensions=dimensions or {},
            observed_at=observed_at or timezone.now(),
        )
    except Exception:
        # Metrics must never break user-facing requests or runtime execution.
        return


def get_run_metrics_snapshot() -> RunMetricsSnapshot:
    with _lock:
        started = int(_counters.get("run_started_total", 0))
        completed = int(_counters.get("run_completed_total", 0))
        failed = int(_counters.get("run_failed_total", 0))
        canceled = int(_counters.get("run_canceled_total", 0))
        latencies = list(_latencies_ms)
        liveness_reconciled_total = int(_counters.get("liveness_reconciled_total", 0))
        liveness_reconciled_by_reason = {
            key.split(":", 1)[1]: int(value)
            for key, value in _counters.items()
            if key.startswith("liveness_reconciled_reason:")
        }
        stale_attempt_ignored_total = int(_counters.get("stale_attempt_ignored_total", 0))
        stale_attempt_ignored_by_source = {
            key.split(":", 1)[1]: int(value)
            for key, value in _counters.items()
            if key.startswith("stale_attempt_ignored_source:")
        }

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
        liveness_reconciled_total=liveness_reconciled_total,
        liveness_reconciled_by_reason=liveness_reconciled_by_reason,
        stale_attempt_ignored_total=stale_attempt_ignored_total,
        stale_attempt_ignored_by_source=stale_attempt_ignored_by_source,
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
        messages_filtered = int(_counters.get("ws_messages_filtered_total", 0))
        slow_client_disconnects = int(_counters.get("ws_slow_client_disconnects_total", 0))
        recent_messages = len(_ws_message_timestamps)
        send_latencies = list(_ws_send_latencies_ms)

    return WebSocketMetricsSnapshot(
        active_connections=active_connections,
        connection_failures_total=connection_failures,
        messages_sent_total=messages_sent,
        messages_dropped_total=messages_dropped,
        messages_filtered_total=messages_filtered,
        slow_client_disconnects_total=slow_client_disconnects,
        message_rate_per_minute=float(recent_messages),
        send_latency_ms_p50=_percentile(send_latencies, 0.5),
        send_latency_ms_p95=_percentile(send_latencies, 0.95),
        generated_at=timezone.now().isoformat(),
    )


def get_api_metrics_snapshot() -> ApiMetricsSnapshot:
    now_ts = time.time()
    with _lock:
        _prune_api_timeout_like_timestamps(now_ts)
        api_latencies = list(_api_latencies_ms)
        callback_auth_failures_by_reason = {
            key.split(":", 1)[1]: int(value)
            for key, value in _counters.items()
            if key.startswith("callback_auth_failure_reason:")
        }
        callback_auth_failures_total = int(_counters.get("callback_auth_failures_total", 0))
        requests_total = int(_counters.get("api_requests_total", 0))
        server_errors_total = int(_counters.get("api_server_errors_total", 0))
        timeout_like_requests_total = int(_counters.get("api_timeout_like_requests_total", 0))
        timeout_like_rate_per_minute = float(len(_api_timeout_like_timestamps))
        timeout_threshold_ms = int(_api_timeout_threshold_ms)

    return ApiMetricsSnapshot(
        requests_total=requests_total,
        server_errors_total=server_errors_total,
        timeout_like_requests_total=timeout_like_requests_total,
        timeout_like_rate_per_minute=timeout_like_rate_per_minute,
        timeout_threshold_ms=timeout_threshold_ms,
        latency_ms_p50=_percentile(api_latencies, 0.5),
        latency_ms_p95=_percentile(api_latencies, 0.95),
        callback_auth_failures_total=callback_auth_failures_total,
        callback_auth_failures_by_reason=callback_auth_failures_by_reason,
        generated_at=timezone.now().isoformat(),
    )
