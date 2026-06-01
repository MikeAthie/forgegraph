from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.services.domain_event_outbox import publish_due_outbox_events
from application.services.whiteboard_board_kafka import (
    build_configured_whiteboard_board_kafka_publisher,
    whiteboard_board_kafka_enabled,
    whiteboard_board_kafka_topic,
)


class Command(BaseCommand):
    help = "Publish committed whiteboard board outbox events to Kafka when explicitly enabled."
    stop_requested = False

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--once", action="store_true")
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
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)
        topic = whiteboard_board_kafka_topic()
        try:
            publisher = build_configured_whiteboard_board_kafka_publisher()
        except Exception as exc:  # noqa: BLE001 - management command should surface config failures.
            raise CommandError(str(exc)) from exc

        while True:
            result = publish_due_outbox_events(publisher=publisher, limit=limit, topic=topic)
            self.stdout.write(
                self.style.SUCCESS(
                    "Published whiteboard board outbox pass "
                    f"(published={result.published}, failed={result.failed}, skipped={result.skipped})."
                )
            )
            if run_once:
                return
            if not result.published and not result.failed:
                time.sleep(sleep_seconds)
