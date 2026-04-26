from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.utils import timezone
from redis.exceptions import RedisError

from application.services.runtime_transport_metrics import (
    RuntimeTransportMetricsSnapshot,
    get_runtime_transport_metrics_snapshot,
)
from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
    build_runtime_intent_redis_client,
)


@dataclass(frozen=True)
class RuntimeTransportObservabilitySnapshot:
    intent_publish_failures_total: int
    intent_received_total: int
    intent_applied_total: int
    intent_ack_total: int
    intent_reclaimed_total: int
    duplicate_intent_ignored_total: int
    dead_lettered_total: int
    stream_length: int
    pending: int
    lag: int
    backlog: int
    consumer_idle_ms: int
    oldest_pending_idle_ms: int
    dead_letter_count: int
    source: str
    error: str
    generated_at: str


def get_runtime_transport_observability_snapshot() -> RuntimeTransportObservabilitySnapshot:
    fallback = get_runtime_transport_metrics_snapshot()
    try:
        redis_client = build_runtime_intent_redis_client()
        stream_length = int(cast(int, redis_client.xlen(RUNTIME_INTENT_STREAM)))
        pending, lag = _group_pending_and_lag(redis_client)
        backlog = pending + lag
        dead_letter_count = int(cast(int, redis_client.xlen(RUNTIME_INTENT_DEAD_LETTER_STREAM)))
        return _snapshot_from_metrics(
            fallback,
            stream_length=stream_length,
            pending=pending,
            lag=lag,
            backlog=backlog,
            consumer_idle_ms=_consumer_idle_ms(redis_client),
            oldest_pending_idle_ms=_oldest_pending_idle_ms(redis_client),
            dead_letter_count=dead_letter_count,
            source="redis",
            error="",
        )
    except RedisError as exc:
        return _snapshot_from_metrics(
            fallback,
            stream_length=0,
            pending=fallback.stream_pending,
            lag=fallback.stream_lag,
            backlog=fallback.stream_backlog,
            consumer_idle_ms=fallback.consumer_idle_ms,
            oldest_pending_idle_ms=fallback.oldest_pending_idle_ms,
            dead_letter_count=fallback.dead_letter_count,
            source="in_process_fallback",
            error=str(exc),
        )


def _snapshot_from_metrics(
    metrics: RuntimeTransportMetricsSnapshot,
    *,
    stream_length: int,
    pending: int,
    lag: int,
    backlog: int,
    consumer_idle_ms: int,
    oldest_pending_idle_ms: int,
    dead_letter_count: int,
    source: str,
    error: str,
) -> RuntimeTransportObservabilitySnapshot:
    return RuntimeTransportObservabilitySnapshot(
        intent_publish_failures_total=metrics.intent_publish_failures_total,
        intent_received_total=metrics.intent_received_total,
        intent_applied_total=metrics.intent_applied_total,
        intent_ack_total=metrics.intent_ack_total,
        intent_reclaimed_total=metrics.intent_reclaimed_total,
        duplicate_intent_ignored_total=metrics.duplicate_intent_ignored_total,
        dead_lettered_total=metrics.dead_lettered_total,
        stream_length=max(int(stream_length), 0),
        pending=max(int(pending), 0),
        lag=max(int(lag), 0),
        backlog=max(int(backlog), 0),
        consumer_idle_ms=max(int(consumer_idle_ms), 0),
        oldest_pending_idle_ms=max(int(oldest_pending_idle_ms), 0),
        dead_letter_count=max(int(dead_letter_count), 0),
        source=source,
        error=error,
        generated_at=timezone.now().isoformat(),
    )


def _group_pending_and_lag(redis_client: Any) -> tuple[int, int]:
    try:
        groups = cast(list[dict[str, Any]], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM))
    except RedisError:
        raise
    except Exception:
        return 0, 0

    for group in groups:
        group_name = _to_str(group.get("name", ""))
        if group_name != RUNTIME_INTENT_CONSUMER_GROUP:
            continue
        return _to_int(group.get("pending", 0)), _to_int(group.get("lag", 0))
    return 0, 0


def _consumer_idle_ms(redis_client: Any) -> int:
    try:
        consumers = cast(
            list[dict[str, Any]],
            redis_client.xinfo_consumers(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP),
        )
    except Exception:
        return 0

    idle_values: list[int] = []
    for consumer in consumers:
        idle_values.append(_to_int(consumer.get("idle") or consumer.get("idle_ms") or 0))
    return max(idle_values, default=0)


def _oldest_pending_idle_ms(redis_client: Any) -> int:
    try:
        pending_entries = cast(
            list[dict[str, Any]],
            redis_client.xpending_range(
                RUNTIME_INTENT_STREAM,
                RUNTIME_INTENT_CONSUMER_GROUP,
                "-",
                "+",
                1,
            ),
        )
    except Exception:
        return 0
    if not pending_entries:
        return 0
    pending = pending_entries[0]
    return _to_int(pending.get("idle") or pending.get("time_since_delivered") or 0)


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if not isinstance(value, str | bytes | bytearray | float):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)
