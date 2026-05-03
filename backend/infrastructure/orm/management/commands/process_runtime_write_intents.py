from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass
from typing import Any, TypedDict, cast

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from redis import Redis
from redis.exceptions import RedisError

from application.services.run_liveness import reconcile_stale_runs
from application.services.runtime_transport_metrics import (
    record_transport_event,
    update_transport_health,
)
from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
    RuntimeIntentError,
    build_runtime_intent_redis_client,
    decode_runtime_intent_message,
    ensure_runtime_intent_group,
    mark_run_transport_failure,
    process_runtime_intent_message,
    record_runtime_intent_dead_letter,
)
from application.services.structured_logging import log_event

logger = logging.getLogger(__name__)


class RedisStreamGroupInfo(TypedDict, total=False):
    name: str | bytes
    pending: int
    lag: int


@dataclass(frozen=True)
class ConsumerLagSnapshot:
    stream_length: int
    pending: int
    lag: int
    backlog: int
    consumer_idle_ms: int
    oldest_pending_idle_ms: int
    dead_letter_count: int


class Command(BaseCommand):
    help = "Consume backend-owned runtime write intents from the Redis stream."

    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, (str, bytes)):
            return int(value)
        return default

    @staticmethod
    def _to_str(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--consumer",
            default=f"{socket.gethostname()}-runtime-intents",
            help="Redis stream consumer name.",
        )
        parser.add_argument(
            "--block-ms",
            type=int,
            default=5000,
            help="How long to block waiting for new intents.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Maximum number of messages to read per poll.",
        )
        parser.add_argument(
            "--claim-idle-ms",
            type=int,
            default=30000,
            help="Claim pending messages idle for at least this long.",
        )
        parser.add_argument(
            "--max-deliveries",
            type=int,
            default=8,
            help="Dead-letter messages that exceed this many delivery attempts.",
        )
        parser.add_argument(
            "--lag-log-interval-seconds",
            type=int,
            default=30,
            help="How often to log stream lag diagnostics.",
        )
        parser.add_argument(
            "--lag-warning-threshold",
            type=int,
            default=100,
            help="Emit a warning when consumer backlog reaches this threshold.",
        )
        parser.add_argument(
            "--lag-warning-threshold-ms",
            type=int,
            default=30000,
            help="Emit a warning when pending idle time reaches this threshold.",
        )
        parser.add_argument(
            "--no-progress-threshold-seconds",
            type=int,
            default=60,
            help="Emit a warning when backlog exists but the consumer makes no progress.",
        )
        parser.add_argument(
            "--watchdog-backlog-threshold",
            type=int,
            default=0,
            help=(
                "Exit for supervisor restart when backlog reaches this threshold and the "
                "consumer is not making progress. Defaults to SLO_QUEUE_MAX_DEPTH."
            ),
        )
        parser.add_argument(
            "--liveness-reconcile-interval-seconds",
            type=int,
            default=0,
            help="How often to reconcile stalled runs from this backend-owned worker.",
        )
        parser.add_argument(
            "--stale-run-after-seconds",
            type=int,
            default=0,
            help="Override the run liveness timeout used by the periodic reconciler.",
        )
        parser.add_argument(
            "--stream-retention-seconds",
            type=int,
            default=86400,
            help="Trim acknowledged stream entries older than this many seconds.",
        )
        parser.add_argument(
            "--stream-hard-maxlen",
            type=int,
            default=100000,
            help=(
                "Pressure-relief stream length cap. Trims only entries already behind the "
                "consumer group's delivered and pending safety boundaries."
            ),
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one poll and exit.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        consumer = str(options["consumer"])
        block_ms = max(int(options["block_ms"]), 1)
        count = max(int(options["count"]), 1)
        claim_idle_ms = max(int(options["claim_idle_ms"]), 1)
        max_deliveries = max(int(options["max_deliveries"]), 1)
        lag_log_interval_seconds = max(int(options["lag_log_interval_seconds"]), 1)
        lag_warning_threshold = max(int(options["lag_warning_threshold"]), 1)
        lag_warning_threshold_ms = max(int(options["lag_warning_threshold_ms"]), 1)
        no_progress_threshold_seconds = max(int(options["no_progress_threshold_seconds"]), 1)
        watchdog_backlog_threshold = int(options.get("watchdog_backlog_threshold") or 0)
        if watchdog_backlog_threshold <= 0:
            watchdog_backlog_threshold = int(getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500))
        liveness_reconcile_interval_seconds = int(
            options.get("liveness_reconcile_interval_seconds") or 0
        )
        if liveness_reconcile_interval_seconds <= 0:
            liveness_reconcile_interval_seconds = int(
                getattr(settings, "RUN_LIVENESS_RECONCILE_INTERVAL_SECONDS", 15)
            )
        stale_run_after_seconds = int(options.get("stale_run_after_seconds") or 0) or int(
            getattr(
                settings,
                "RUN_ENGINE_STALLED_TIMEOUT_SECONDS",
                getattr(settings, "RUN_LIVENESS_TIMEOUT_SECONDS", 60),
            )
        )
        stream_retention_seconds = max(int(options.get("stream_retention_seconds", 86400)), 0)
        stream_hard_maxlen = max(int(options.get("stream_hard_maxlen", 100000)), 0)
        once = bool(options["once"])

        redis_client = build_runtime_intent_redis_client()
        ensure_runtime_intent_group(redis_client)

        self.stdout.write(
            self.style.SUCCESS(
                f"Runtime intent consumer '{consumer}' reading from '{RUNTIME_INTENT_STREAM}' "
                f"via group '{RUNTIME_INTENT_CONSUMER_GROUP}'."
            )
        )

        last_lag_log_at = 0.0
        last_progress_at = time.monotonic()
        last_liveness_reconcile_at = 0.0
        while True:
            try:
                saw_messages, made_progress = self._consume_once(
                    redis_client=redis_client,
                    consumer=consumer,
                    block_ms=block_ms,
                    count=count,
                    claim_idle_ms=claim_idle_ms,
                    max_deliveries=max_deliveries,
                    stream_retention_seconds=stream_retention_seconds,
                    stream_hard_maxlen=stream_hard_maxlen,
                )
            except RedisError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "runtime_intent_transport_error",
                    stream=RUNTIME_INTENT_STREAM,
                    dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
                    error_message=str(exc),
                )
                time.sleep(1)
                if once:
                    return
                continue

            if made_progress:
                last_progress_at = time.monotonic()

            now = time.monotonic()
            if saw_messages or now - last_lag_log_at >= lag_log_interval_seconds:
                lag_snapshot = self._log_consumer_lag(
                    redis_client=redis_client,
                    lag_warning_threshold=lag_warning_threshold,
                    lag_warning_threshold_ms=lag_warning_threshold_ms,
                )
                self._warn_if_no_progress(
                    lag_snapshot=lag_snapshot,
                    last_progress_at=last_progress_at,
                    no_progress_threshold_seconds=no_progress_threshold_seconds,
                )
                self._exit_if_watchdog_backlog_stalled(
                    lag_snapshot=lag_snapshot,
                    last_progress_at=last_progress_at,
                    no_progress_threshold_seconds=no_progress_threshold_seconds,
                    watchdog_backlog_threshold=watchdog_backlog_threshold,
                )
                last_lag_log_at = now

            if (
                liveness_reconcile_interval_seconds > 0
                and now - last_liveness_reconcile_at >= liveness_reconcile_interval_seconds
            ):
                self._reconcile_liveness(stale_run_after_seconds=stale_run_after_seconds)
                last_liveness_reconcile_at = now

            if once:
                return

    def _consume_once(
        self,
        *,
        redis_client: Redis,
        consumer: str,
        block_ms: int,
        count: int,
        claim_idle_ms: int,
        max_deliveries: int,
        stream_retention_seconds: int,
        stream_hard_maxlen: int,
    ) -> tuple[bool, bool]:
        saw_messages = False
        made_progress = False

        claimed_messages = self._claim_stale_messages(
            redis_client=redis_client,
            consumer=consumer,
            claim_idle_ms=claim_idle_ms,
            count=count,
        )
        saw_messages = saw_messages or bool(claimed_messages)
        claimed_seen, claimed_progress = self._process_messages(
            redis_client=redis_client,
            consumer=consumer,
            messages=claimed_messages,
            max_deliveries=max_deliveries,
            reclaimed=True,
            stream_retention_seconds=stream_retention_seconds,
            stream_hard_maxlen=stream_hard_maxlen,
        )
        saw_messages = saw_messages or claimed_seen
        made_progress = made_progress or claimed_progress

        records = cast(
            list[tuple[str, list[tuple[str, dict[str, Any]]]]],
            redis_client.xreadgroup(
                groupname=RUNTIME_INTENT_CONSUMER_GROUP,
                consumername=consumer,
                streams={RUNTIME_INTENT_STREAM: ">"},
                count=count,
                block=block_ms,
            ),
        )
        for _, messages in records:
            saw_messages = saw_messages or bool(messages)
            batch_seen, batch_progress = self._process_messages(
                redis_client=redis_client,
                consumer=consumer,
                messages=messages,
                max_deliveries=max_deliveries,
                reclaimed=False,
                stream_retention_seconds=stream_retention_seconds,
                stream_hard_maxlen=stream_hard_maxlen,
            )
            saw_messages = saw_messages or batch_seen
            made_progress = made_progress or batch_progress

        return saw_messages, made_progress

    def _claim_stale_messages(
        self,
        *,
        redis_client: Redis,
        consumer: str,
        claim_idle_ms: int,
        count: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        response = cast(
            Any,
            redis_client.xautoclaim(
                RUNTIME_INTENT_STREAM,
                RUNTIME_INTENT_CONSUMER_GROUP,
                consumer,
                claim_idle_ms,
                start_id="0-0",
                count=count,
            ),
        )
        if not response:
            return []

        messages: Any = []
        if isinstance(response, (list, tuple)):
            if len(response) >= 2:
                messages = response[1]
            elif len(response) == 1:
                messages = response[0]
        return list(messages or [])

    def _process_messages(
        self,
        *,
        redis_client: Redis,
        consumer: str,
        messages: list[tuple[str, dict[str, Any]]],
        max_deliveries: int,
        reclaimed: bool,
        stream_retention_seconds: int,
        stream_hard_maxlen: int,
    ) -> tuple[bool, bool]:
        saw_messages = False
        made_progress = False
        for message_id, fields in messages:
            saw_messages = True
            metadata = self._intent_metadata(fields)
            delivery_count, idle_ms = self._delivery_details(
                redis_client=redis_client,
                message_id=str(message_id),
                consumer=consumer,
            )
            retry_count = max(delivery_count - 1, 0)

            if reclaimed:
                log_event(
                    logger,
                    logging.WARNING,
                    "intent_reclaimed",
                    run_id=metadata.get("run_id"),
                    intent_id=metadata.get("intent_id"),
                    intent_type=metadata.get("intent_type"),
                    attempt_id=metadata.get("attempt_id"),
                    retry_count=retry_count,
                    delivery_count=delivery_count,
                    message_id=str(message_id),
                    reclaimed=True,
                    consumer_idle_ms=idle_ms,
                )
                record_transport_event("intent_reclaimed")

            log_event(
                logger,
                logging.INFO,
                "intent_received",
                run_id=metadata.get("run_id"),
                intent_id=metadata.get("intent_id"),
                intent_type=metadata.get("intent_type"),
                attempt_id=metadata.get("attempt_id"),
                retry_count=retry_count,
                delivery_count=delivery_count,
                message_id=str(message_id),
                reclaimed=reclaimed,
            )
            record_transport_event("intent_received")

            if delivery_count > max_deliveries:
                self._dead_letter_message(
                    redis_client=redis_client,
                    message_id=str(message_id),
                    fields=fields,
                    metadata=metadata,
                    reason=f"delivery count exceeded {max_deliveries}",
                    error_class="max_deliveries_exceeded",
                    delivery_count=delivery_count,
                    reclaimed=reclaimed,
                    stream_hard_maxlen=stream_hard_maxlen,
                )
                made_progress = True
                continue

            try:
                result = process_runtime_intent_message(
                    stream_message_id=str(message_id),
                    fields={str(key): str(value) for key, value in fields.items()},
                )
            except RuntimeIntentError as exc:
                self._dead_letter_message(
                    redis_client=redis_client,
                    message_id=str(message_id),
                    fields=fields,
                    metadata=metadata,
                    reason=f"invalid runtime intent: {exc}",
                    error_class="invalid_intent",
                    delivery_count=delivery_count,
                    reclaimed=reclaimed,
                    stream_hard_maxlen=stream_hard_maxlen,
                )
                made_progress = True
                continue
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Runtime intent {message_id} failed and will be retried: {exc}"
                        f"{self._format_metadata(metadata)}"
                    )
                )
                time.sleep(1)
                continue

            if result == "duplicate":
                log_event(
                    logger,
                    logging.WARNING,
                    "duplicate_intent_ignored",
                    run_id=metadata.get("run_id"),
                    intent_id=metadata.get("intent_id"),
                    intent_type=metadata.get("intent_type"),
                    attempt_id=metadata.get("attempt_id"),
                    retry_count=retry_count,
                    delivery_count=delivery_count,
                    message_id=str(message_id),
                )
                record_transport_event("duplicate_intent_ignored")
            else:
                log_event(
                    logger,
                    logging.INFO,
                    "intent_applied",
                    run_id=metadata.get("run_id"),
                    intent_id=metadata.get("intent_id"),
                    intent_type=metadata.get("intent_type"),
                    attempt_id=metadata.get("attempt_id"),
                    retry_count=retry_count,
                    delivery_count=delivery_count,
                    message_id=str(message_id),
                    status=result,
                )
                record_transport_event("intent_applied")

            redis_client.xack(
                RUNTIME_INTENT_STREAM,
                RUNTIME_INTENT_CONSUMER_GROUP,
                message_id,
            )
            log_event(
                logger,
                logging.INFO,
                "intent_ack",
                run_id=metadata.get("run_id"),
                intent_id=metadata.get("intent_id"),
                intent_type=metadata.get("intent_type"),
                attempt_id=metadata.get("attempt_id"),
                retry_count=retry_count,
                delivery_count=delivery_count,
                message_id=str(message_id),
            )
            record_transport_event("intent_ack")

            trimmed_count = self._trim_stream(
                redis_client=redis_client,
                stream_retention_seconds=stream_retention_seconds,
            )
            trimmed_count += self._enforce_stream_hard_cap(
                redis_client=redis_client,
                stream_hard_maxlen=stream_hard_maxlen,
            )
            if trimmed_count > 0:
                log_event(
                    logger,
                    logging.INFO,
                    "runtime_intent_stream_trimmed",
                    stream=RUNTIME_INTENT_STREAM,
                    trimmed_count=trimmed_count,
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Runtime intent {message_id} processed with result '{result}'"
                    f"{self._format_metadata(metadata)}."
                )
            )
            made_progress = True

        return saw_messages, made_progress

    def _delivery_details(
        self,
        *,
        redis_client: Redis,
        message_id: str,
        consumer: str,
    ) -> tuple[int, int]:
        pending_entries = cast(
            list[dict[str, Any]],
            redis_client.xpending_range(
                RUNTIME_INTENT_STREAM,
                RUNTIME_INTENT_CONSUMER_GROUP,
                message_id,
                message_id,
                1,
                consumername=consumer,
            ),
        )
        if not pending_entries:
            pending_entries = cast(
                list[dict[str, Any]],
                redis_client.xpending_range(
                    RUNTIME_INTENT_STREAM,
                    RUNTIME_INTENT_CONSUMER_GROUP,
                    message_id,
                    message_id,
                    1,
                ),
            )
        if not pending_entries:
            return 1, 0
        pending = pending_entries[0]
        if not isinstance(pending, dict):
            return 1, 0
        raw_count = pending.get("times_delivered") or pending.get("delivery_count") or 1
        raw_idle_ms = (
            pending.get("idle")
            or pending.get("time_since_delivered")
            or pending.get("idle_ms")
            or 0
        )
        try:
            delivery_count = int(raw_count)
        except (TypeError, ValueError):
            delivery_count = 1
        try:
            idle_ms = int(raw_idle_ms)
        except (TypeError, ValueError):
            idle_ms = 0
        return max(delivery_count, 1), max(idle_ms, 0)

    def _dead_letter_message(
        self,
        *,
        redis_client: Redis,
        message_id: str,
        fields: dict[str, Any],
        metadata: dict[str, str],
        reason: str,
        error_class: str,
        delivery_count: int,
        reclaimed: bool,
        stream_hard_maxlen: int,
    ) -> None:
        dead_lettered_at = timezone.now()
        redis_client.xadd(
            RUNTIME_INTENT_DEAD_LETTER_STREAM,
            {
                "original_stream": RUNTIME_INTENT_STREAM,
                "original_message_id": message_id,
                "stream_message_id": message_id,
                "dead_lettered_at": dead_lettered_at.isoformat(),
                "timestamp": dead_lettered_at.isoformat(),
                "reason": reason,
                "error_class": error_class,
                "delivery_count": delivery_count,
                "reclaimed": json.dumps(bool(reclaimed)),
                "intent": str(fields.get("intent") or ""),
                "intent_id": metadata.get("intent_id") or "",
                "intent_type": metadata.get("intent_type") or "",
                "run_id": metadata.get("run_id") or "",
                "attempt_id": metadata.get("attempt_id") or "",
            },
        )
        redis_client.xack(
            RUNTIME_INTENT_STREAM,
            RUNTIME_INTENT_CONSUMER_GROUP,
            message_id,
        )
        mark_run_transport_failure(
            run_id=metadata.get("run_id"),
            stream_message_id=message_id,
            reason=reason,
            event_time=dead_lettered_at,
            dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
            intent_id=metadata.get("intent_id") or "",
            intent_type=metadata.get("intent_type") or "",
        )
        record_runtime_intent_dead_letter(
            intent_id=metadata.get("intent_id"),
            run_id=metadata.get("run_id"),
            intent_type=metadata.get("intent_type"),
            attempt_id=metadata.get("attempt_id"),
            stream_message_id=message_id,
            reason=reason,
            error_class=error_class,
        )
        trimmed_count = self._enforce_stream_hard_cap(
            redis_client=redis_client,
            stream_hard_maxlen=stream_hard_maxlen,
        )
        if trimmed_count > 0:
            log_event(
                logger,
                logging.INFO,
                "runtime_intent_stream_trimmed",
                stream=RUNTIME_INTENT_STREAM,
                trimmed_count=trimmed_count,
            )
        log_event(
            logger,
            logging.ERROR,
            "dead_lettered",
            run_id=metadata.get("run_id"),
            intent_id=metadata.get("intent_id"),
            intent_type=metadata.get("intent_type"),
            attempt_id=metadata.get("attempt_id"),
            message_id=message_id,
            stream_message_id=message_id,
            dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
            delivery_count=delivery_count,
            reclaimed=reclaimed,
            reason=reason,
            error_class=error_class,
            dead_lettered_at=dead_lettered_at,
            error_message=reason,
        )
        record_transport_event("dead_lettered")
        self.stderr.write(
            self.style.WARNING(
                f"Dead-lettered runtime intent {message_id}: {reason}{self._format_metadata(metadata)}"
            )
        )

    def _log_consumer_lag(
        self,
        *,
        redis_client: Redis,
        lag_warning_threshold: int,
        lag_warning_threshold_ms: int,
    ) -> ConsumerLagSnapshot:
        groups = cast(list[RedisStreamGroupInfo], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM))
        stream_length = int(cast(int, redis_client.xlen(RUNTIME_INTENT_STREAM)))
        pending = 0
        lag = 0

        def _parse_group_info(raw: RedisStreamGroupInfo) -> tuple[str, int, int]:
            return (
                Command._to_str(raw.get("name", "")),
                Command._to_int(raw.get("pending", 0)),
                Command._to_int(raw.get("lag", 0)),
            )

        for group in groups:
            group_name, pending, lag = _parse_group_info(group)

            if group_name != RUNTIME_INTENT_CONSUMER_GROUP:
                continue

            break

        consumer_idle_ms = self._consumer_idle_ms(redis_client=redis_client)
        oldest_pending_idle_ms = self._oldest_pending_idle_ms(redis_client=redis_client)
        dead_letter_count = int(cast(int, redis_client.xlen(RUNTIME_INTENT_DEAD_LETTER_STREAM)))
        backlog = pending + lag

        update_transport_health(
            pending=pending,
            lag=lag,
            backlog=backlog,
            consumer_idle_ms=consumer_idle_ms,
            oldest_pending_idle_ms=oldest_pending_idle_ms,
            dead_letter_count=dead_letter_count,
        )

        lag_parts = [
            f"stream_length={stream_length}",
            f"pending={pending}",
            f"lag={lag}",
            f"backlog={backlog}",
            f"consumer_idle_ms={consumer_idle_ms}",
            f"oldest_pending_idle_ms={oldest_pending_idle_ms}",
            f"dead_letter_count={dead_letter_count}",
            f"warning_threshold={lag_warning_threshold}",
        ]
        threshold_breached = (
            backlog >= lag_warning_threshold
            or oldest_pending_idle_ms >= lag_warning_threshold_ms
            or consumer_idle_ms >= lag_warning_threshold_ms
        )
        writer = self.stderr.write if threshold_breached else self.stdout.write
        formatter = self.style.WARNING if threshold_breached else self.style.HTTP_INFO
        writer(formatter(f"Runtime intent consumer lag: {' '.join(lag_parts)}"))

        log_event(
            logger,
            logging.WARNING if threshold_breached else logging.INFO,
            "runtime_intent_transport_health",
            stream=RUNTIME_INTENT_STREAM,
            dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
            stream_length=stream_length,
            pending=pending,
            lag=lag,
            backlog=backlog,
            consumer_idle_ms=consumer_idle_ms,
            oldest_pending_idle_ms=oldest_pending_idle_ms,
            dead_letter_count=dead_letter_count,
            warning_threshold=lag_warning_threshold,
            status="warning" if threshold_breached else "ok",
        )

        return ConsumerLagSnapshot(
            stream_length=stream_length,
            pending=pending,
            lag=lag,
            backlog=backlog,
            consumer_idle_ms=consumer_idle_ms,
            oldest_pending_idle_ms=oldest_pending_idle_ms,
            dead_letter_count=dead_letter_count,
        )

    def _warn_if_no_progress(
        self,
        *,
        lag_snapshot: ConsumerLagSnapshot,
        last_progress_at: float,
        no_progress_threshold_seconds: int,
    ) -> None:
        progress_age_seconds = int(max(time.monotonic() - last_progress_at, 0))
        if lag_snapshot.backlog <= 0 or progress_age_seconds < no_progress_threshold_seconds:
            return

        log_event(
            logger,
            logging.WARNING,
            "runtime_intent_transport_stalled",
            stream=RUNTIME_INTENT_STREAM,
            dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
            backlog=lag_snapshot.backlog,
            pending=lag_snapshot.pending,
            lag=lag_snapshot.lag,
            consumer_idle_ms=lag_snapshot.consumer_idle_ms,
            oldest_pending_idle_ms=lag_snapshot.oldest_pending_idle_ms,
            progress_age_seconds=progress_age_seconds,
            no_progress_threshold_seconds=no_progress_threshold_seconds,
            status="warning",
        )

    def _exit_if_watchdog_backlog_stalled(
        self,
        *,
        lag_snapshot: ConsumerLagSnapshot,
        last_progress_at: float,
        no_progress_threshold_seconds: int,
        watchdog_backlog_threshold: int,
    ) -> None:
        if watchdog_backlog_threshold <= 0 or lag_snapshot.backlog < watchdog_backlog_threshold:
            return

        progress_age_seconds = int(max(time.monotonic() - last_progress_at, 0))
        if progress_age_seconds < no_progress_threshold_seconds:
            return

        log_event(
            logger,
            logging.ERROR,
            "runtime_intent_watchdog_triggered",
            stream=RUNTIME_INTENT_STREAM,
            dead_letter_stream=RUNTIME_INTENT_DEAD_LETTER_STREAM,
            backlog=lag_snapshot.backlog,
            pending=lag_snapshot.pending,
            lag=lag_snapshot.lag,
            progress_age_seconds=progress_age_seconds,
            watchdog_backlog_threshold=watchdog_backlog_threshold,
            recovery_action="process_exit_for_supervisor_restart",
        )
        raise SystemExit(75)

    def _reconcile_liveness(self, *, stale_run_after_seconds: int) -> None:
        result = reconcile_stale_runs(stale_after_seconds=stale_run_after_seconds)
        if result.scanned <= 0 and result.reconciled <= 0:
            return

        log_event(
            logger,
            logging.WARNING if result.reconciled else logging.INFO,
            "run_liveness_periodic_reconcile",
            stale_after_seconds=stale_run_after_seconds,
            scanned=result.scanned,
            reconciled=result.reconciled,
        )

    def _consumer_idle_ms(self, *, redis_client: Redis) -> int:
        try:
            consumers = cast(
                list[dict[str, Any]],
                redis_client.xinfo_consumers(RUNTIME_INTENT_STREAM, RUNTIME_INTENT_CONSUMER_GROUP),
            )
        except Exception:
            return 0

        idle_values: list[int] = []
        for consumer in consumers:
            raw_idle = consumer.get("idle") or consumer.get("idle_ms") or 0
            try:
                idle_values.append(int(raw_idle))
            except (TypeError, ValueError):
                continue
        return max(idle_values, default=0)

    def _oldest_pending_idle_ms(self, *, redis_client: Redis) -> int:
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
        if not pending_entries:
            return 0
        pending = pending_entries[0]
        raw_idle = pending.get("idle") or pending.get("time_since_delivered") or 0
        try:
            return max(int(raw_idle), 0)
        except (TypeError, ValueError):
            return 0

    def _trim_stream(
        self,
        *,
        redis_client: Redis,
        stream_retention_seconds: int,
    ) -> int:
        if stream_retention_seconds <= 0:
            return 0
        for group in cast(list[dict[str, Any]], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)):
            if str(group.get("name") or "") != RUNTIME_INTENT_CONSUMER_GROUP:
                continue
            if int(group.get("lag") or 0) > 0:
                return 0
            break

        cutoff_ms = int((time.time() - stream_retention_seconds) * 1000)
        if cutoff_ms <= 0:
            return 0
        trim_minid = f"{cutoff_ms}-0"
        oldest_pending_id = self._oldest_pending_id(redis_client=redis_client)
        if oldest_pending_id and self._compare_stream_ids(oldest_pending_id, trim_minid) < 0:
            trim_minid = oldest_pending_id

        trimmed = cast(
            int,
            redis_client.xtrim(
                RUNTIME_INTENT_STREAM,
                minid=trim_minid,
                approximate=True,
            ),
        )
        try:
            return max(int(trimmed), 0)
        except (TypeError, ValueError):
            return 0

    def _enforce_stream_hard_cap(
        self,
        *,
        redis_client: Redis,
        stream_hard_maxlen: int,
    ) -> int:
        if stream_hard_maxlen <= 0:
            return 0

        stream_length = int(cast(int, redis_client.xlen(RUNTIME_INTENT_STREAM)))
        if stream_length <= stream_hard_maxlen:
            return 0

        hard_cap_minid = self._hard_cap_minid(
            redis_client=redis_client,
            stream_hard_maxlen=stream_hard_maxlen,
        )
        if not hard_cap_minid:
            return 0

        last_delivered_id = self._last_delivered_id(redis_client=redis_client)
        if last_delivered_id and self._compare_stream_ids(last_delivered_id, hard_cap_minid) < 0:
            hard_cap_minid = last_delivered_id

        oldest_pending_id = self._oldest_pending_id(redis_client=redis_client)
        if oldest_pending_id and self._compare_stream_ids(oldest_pending_id, hard_cap_minid) < 0:
            hard_cap_minid = oldest_pending_id

        if self._compare_stream_ids(hard_cap_minid, "0-0") <= 0:
            return 0

        trimmed = cast(
            int,
            redis_client.xtrim(
                RUNTIME_INTENT_STREAM,
                minid=hard_cap_minid,
                approximate=True,
            ),
        )
        try:
            trimmed_count = max(int(trimmed), 0)
        except (TypeError, ValueError):
            trimmed_count = 0

        if trimmed_count > 0:
            log_event(
                logger,
                logging.WARNING,
                "runtime_intent_stream_hard_cap_trimmed",
                stream=RUNTIME_INTENT_STREAM,
                stream_length=stream_length,
                trimmed_count=trimmed_count,
                warning_threshold=stream_hard_maxlen,
                message=(
                    "Runtime intent stream exceeded hard cap; trimmed only entries behind "
                    "delivered and pending safety boundaries."
                ),
            )
        return trimmed_count

    def _hard_cap_minid(
        self,
        *,
        redis_client: Redis,
        stream_hard_maxlen: int,
    ) -> str:
        if stream_hard_maxlen <= 0:
            return ""
        entries = cast(
            list[tuple[str, dict[str, Any]]],
            redis_client.xrevrange(
                RUNTIME_INTENT_STREAM,
                max="+",
                min="-",
                count=stream_hard_maxlen,
            ),
        )
        if len(entries) < stream_hard_maxlen:
            return ""
        return str(entries[-1][0])

    def _last_delivered_id(self, *, redis_client: Redis) -> str:
        for group in cast(list[dict[str, Any]], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)):
            if str(group.get("name") or "") != RUNTIME_INTENT_CONSUMER_GROUP:
                continue
            return str(
                group.get("last-delivered-id") or group.get("last_delivered_id") or ""
            ).strip()
        return ""

    def _oldest_pending_id(self, *, redis_client: Redis) -> str:
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
        if not pending_entries:
            return ""
        return str(pending_entries[0].get("message_id") or "").strip()

    def _compare_stream_ids(self, left: str, right: str) -> int:
        left_ms, left_seq = self._parse_stream_id(left)
        right_ms, right_seq = self._parse_stream_id(right)
        if left_ms < right_ms:
            return -1
        if left_ms > right_ms:
            return 1
        if left_seq < right_seq:
            return -1
        if left_seq > right_seq:
            return 1
        return 0

    def _parse_stream_id(self, value: str) -> tuple[int, int]:
        head, _, tail = str(value or "").partition("-")
        try:
            return int(head), int(tail or "0")
        except ValueError:
            return 0, 0

    def _intent_metadata(self, fields: dict[str, Any]) -> dict[str, str]:
        try:
            intent = decode_runtime_intent_message(
                {str(key): str(value) for key, value in fields.items()}
            )
            return {
                "intent_id": str(intent.intent_id),
                "intent_type": intent.intent_type,
                "run_id": str(intent.run_id),
                "attempt_id": intent.attempt_id,
            }
        except Exception:
            raw_intent = str(fields.get("intent") or "").strip()
            if not raw_intent:
                return {}
            try:
                payload = json.loads(raw_intent)
            except json.JSONDecodeError:
                return {}
            if not isinstance(payload, dict):
                return {}
            metadata: dict[str, str] = {}
            for key in ("intent_id", "intent_type", "run_id", "attempt_id"):
                value = str(payload.get(key) or "").strip()
                if value:
                    metadata[key] = value
            return metadata

    def _format_metadata(self, metadata: dict[str, str]) -> str:
        if not metadata:
            return ""
        parts = [f"{key}={value}" for key, value in metadata.items() if value]
        if not parts:
            return ""
        return " (" + " ".join(parts) + ")"
