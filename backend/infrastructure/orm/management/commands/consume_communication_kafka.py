from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.services.communication_kafka import (
    build_configured_communication_kafka_consumer,
    communication_kafka_consumer_group,
    communication_kafka_enabled,
    communication_kafka_topic,
    consume_communication_kafka_events,
)


class Command(BaseCommand):
    help = "Consume committed communication Kafka metadata events into idempotent receipts."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum Kafka messages to poll per pass.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one consume pass and exit.",
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            help="Seconds to wait for each Kafka poll.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between consume passes when not using --once.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not communication_kafka_enabled():
            self.stdout.write(
                self.style.WARNING("COMMUNICATION_KAFKA_ENABLED is false; exiting.")
            )
            return

        limit = max(int(options.get("limit") or 1), 1)
        run_once = bool(options.get("once"))
        poll_timeout = max(float(options.get("poll_timeout") or 0), 0.1)
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)
        topic = communication_kafka_topic()
        consumer_group = communication_kafka_consumer_group()
        try:
            consumer = build_configured_communication_kafka_consumer()
        except Exception as exc:  # noqa: BLE001 - command should report config failures cleanly.
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Communication Kafka consumer starting: "
                f"topic={topic} group={consumer_group}"
            )
        )
        try:
            while True:
                result = consume_communication_kafka_events(
                    consumer=consumer,
                    consumer_group=consumer_group,
                    limit=limit,
                    poll_timeout_seconds=poll_timeout,
                )
                if result.handled or result.duplicates or result.ignored or result.failed:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Consumed communication Kafka pass "
                            f"(handled={result.handled}, duplicates={result.duplicates}, "
                            f"ignored={result.ignored}, failed={result.failed})."
                        )
                    )
                if run_once:
                    return
                if not (result.handled or result.duplicates or result.ignored or result.failed):
                    time.sleep(sleep_seconds)
        finally:
            consumer.close()
