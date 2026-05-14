from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.services.communication_kafka import (
    build_configured_communication_kafka_publisher,
    communication_kafka_enabled,
    communication_kafka_topic,
)
from application.services.domain_event_outbox import publish_due_outbox_events


class Command(BaseCommand):
    help = "Publish committed communication outbox events to Kafka when explicitly enabled."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum outbox rows to publish per pass.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one publish pass and exit.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between publish passes when not using --once.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not communication_kafka_enabled():
            self.stdout.write(
                self.style.WARNING("COMMUNICATION_KAFKA_ENABLED is false; exiting.")
            )
            return

        limit = max(int(options.get("limit") or 1), 1)
        run_once = bool(options.get("once"))
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)
        topic = communication_kafka_topic()
        try:
            publisher = build_configured_communication_kafka_publisher()
        except Exception as exc:  # noqa: BLE001 - command should report config failures cleanly.
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Communication Kafka publisher starting: {topic}"))
        while True:
            result = publish_due_outbox_events(
                publisher=publisher,
                limit=limit,
                topic=topic,
            )
            if result.published or result.failed:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Published communication outbox pass "
                        f"(published={result.published}, failed={result.failed}, "
                        f"skipped={result.skipped})."
                    )
                )
            if run_once:
                return
            if not result.published and not result.failed:
                time.sleep(sleep_seconds)
