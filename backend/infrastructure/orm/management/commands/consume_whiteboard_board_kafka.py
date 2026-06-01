from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.services.whiteboard_board_kafka import (
    build_configured_whiteboard_board_kafka_consumer,
    consume_whiteboard_board_kafka_events,
    whiteboard_board_kafka_consumer_group,
    whiteboard_board_kafka_enabled,
    whiteboard_board_kafka_topic,
)


class Command(BaseCommand):
    help = "Consume whiteboard board Kafka metadata events into idempotent receipts."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-timeout", type=float, default=1.0)
        parser.add_argument("--sleep", type=float, default=1.0)

    def handle(self, *args: Any, **options: Any) -> None:
        _ = args
        if not whiteboard_board_kafka_enabled():
            self.stdout.write(
                self.style.WARNING("WHITEBOARD_BOARD_KAFKA_ENABLED is false; exiting.")
            )
            return
        limit = max(int(options.get("limit") or 1), 1)
        run_once = bool(options.get("once"))
        poll_timeout = max(float(options.get("poll_timeout") or 0), 0.1)
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)
        topic = whiteboard_board_kafka_topic()
        consumer_group = whiteboard_board_kafka_consumer_group()
        try:
            consumer = build_configured_whiteboard_board_kafka_consumer()
        except Exception as exc:  # noqa: BLE001 - management command should surface config failures.
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Whiteboard board Kafka consumer starting: topic={topic} group={consumer_group}"
            )
        )
        try:
            while True:
                result = consume_whiteboard_board_kafka_events(
                    consumer=consumer,
                    consumer_group=consumer_group,
                    limit=limit,
                    poll_timeout_seconds=poll_timeout,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        "Consumed whiteboard board Kafka pass "
                        f"(handled={result.handled}, duplicates={result.duplicates}, "
                        f"ignored={result.ignored}, failed={result.failed}, "
                        f"commit_failed={result.commit_failed})."
                    )
                )
                if run_once:
                    return
                if not (
                    result.handled
                    or result.duplicates
                    or result.ignored
                    or result.failed
                    or result.commit_failed
                ):
                    time.sleep(sleep_seconds)
        finally:
            consumer.close()
