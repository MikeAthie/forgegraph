from __future__ import annotations

import json
import socket
import time
from typing import Any, cast

from django.core.management.base import BaseCommand
from redis import Redis

from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_STREAM,
    RuntimeIntentError,
    build_runtime_intent_redis_client,
    decode_runtime_intent_message,
    ensure_runtime_intent_group,
    process_runtime_intent_message,
)


class Command(BaseCommand):
    help = "Consume backend-owned runtime write intents from the Redis stream."

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
            help="Discard messages that exceed this many delivery attempts.",
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
            help="Emit a warning when consumer lag reaches this threshold.",
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
        while True:
            claimed_messages = self._claim_stale_messages(
                redis_client=redis_client,
                consumer=consumer,
                claim_idle_ms=claim_idle_ms,
                count=count,
            )
            processed_any = self._process_messages(
                redis_client=redis_client,
                consumer=consumer,
                messages=claimed_messages,
                max_deliveries=max_deliveries,
            )

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
                processed_any = (
                    self._process_messages(
                        redis_client=redis_client,
                        consumer=consumer,
                        messages=messages,
                        max_deliveries=max_deliveries,
                    )
                    or processed_any
                )

            now = time.monotonic()
            if processed_any or now - last_lag_log_at >= lag_log_interval_seconds:
                self._log_consumer_lag(
                    redis_client=redis_client,
                    lag_warning_threshold=lag_warning_threshold,
                )
                last_lag_log_at = now

            if once:
                return

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
    ) -> bool:
        processed_any = False
        for message_id, fields in messages:
            processed_any = True
            metadata = self._intent_metadata(fields)
            if (
                self._delivery_count(
                    redis_client=redis_client,
                    message_id=str(message_id),
                    consumer=consumer,
                )
                > max_deliveries
            ):
                self._discard_message(
                    redis_client=redis_client,
                    message_id=str(message_id),
                    reason=(
                        f"delivery count exceeded {max_deliveries}{self._format_metadata(metadata)}"
                    ),
                )
                continue

            try:
                result = process_runtime_intent_message(
                    stream_message_id=str(message_id),
                    fields={str(key): str(value) for key, value in fields.items()},
                )
            except RuntimeIntentError as exc:
                self._discard_message(
                    redis_client=redis_client,
                    message_id=str(message_id),
                    reason=f"invalid runtime intent: {exc}{self._format_metadata(metadata)}",
                )
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

            redis_client.xack(
                RUNTIME_INTENT_STREAM,
                RUNTIME_INTENT_CONSUMER_GROUP,
                message_id,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Runtime intent {message_id} processed with result '{result}'"
                    f"{self._format_metadata(metadata)}."
                )
            )
        return processed_any

    def _delivery_count(
        self,
        *,
        redis_client: Redis,
        message_id: str,
        consumer: str,
    ) -> int:
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
            return 1
        pending = pending_entries[0]
        if isinstance(pending, dict):
            raw_count = pending.get("times_delivered") or pending.get("delivery_count") or 1
            try:
                return int(raw_count)
            except (TypeError, ValueError):
                return 1
        return 1

    def _discard_message(
        self,
        *,
        redis_client: Redis,
        message_id: str,
        reason: str,
    ) -> None:
        self.stderr.write(self.style.WARNING(f"Discarding runtime intent {message_id}: {reason}"))
        redis_client.xack(
            RUNTIME_INTENT_STREAM,
            RUNTIME_INTENT_CONSUMER_GROUP,
            message_id,
        )

    def _log_consumer_lag(
        self,
        *,
        redis_client: Redis,
        lag_warning_threshold: int,
    ) -> None:
        stream_length = redis_client.xlen(RUNTIME_INTENT_STREAM)
        pending = 0
        lag = None
        for group in cast(list[dict[str, Any]], redis_client.xinfo_groups(RUNTIME_INTENT_STREAM)):
            group_name = str(group.get("name") or "")
            if group_name != RUNTIME_INTENT_CONSUMER_GROUP:
                continue
            pending = int(group.get("pending") or 0)
            if "lag" in group:
                raw_lag = group.get("lag")
                lag = None if raw_lag is None else int(raw_lag)
            break

        lag_parts = [
            f"stream_length={stream_length}",
            f"pending={pending}",
        ]
        if lag is not None:
            lag_parts.append(f"lag={lag}")
        effective_lag = lag if lag is not None else pending
        writer = self.stderr.write if effective_lag >= lag_warning_threshold else self.stdout.write
        formatter = (
            self.style.WARNING if effective_lag >= lag_warning_threshold else self.style.HTTP_INFO
        )
        lag_parts.append(f"warning_threshold={lag_warning_threshold}")
        writer(formatter(f"Runtime intent consumer lag: {' '.join(lag_parts)}"))

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
