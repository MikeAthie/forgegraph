from __future__ import annotations

import logging
import signal
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.services.communication_kafka import (
    build_configured_communication_kafka_publisher,
    communication_kafka_enabled,
    communication_kafka_topic,
)
from application.services.domain_event_outbox import publish_due_outbox_events
from application.services.metrics import record_service_metric_sample
from application.services.structured_logging import log_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Publish committed communication outbox events to Kafka when explicitly enabled."
    stop_requested = False

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
        self._install_signal_handlers()
        if not communication_kafka_enabled():
            self.stdout.write(self.style.WARNING("COMMUNICATION_KAFKA_ENABLED is false; exiting."))
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
        try:
            while not self.stop_requested:
                try:
                    result = publish_due_outbox_events(
                        publisher=publisher,
                        limit=limit,
                        topic=topic,
                    )
                except Exception as exc:  # noqa: BLE001 - long-running worker should surface and retry.
                    log_event(
                        logger,
                        logging.ERROR,
                        "communication_kafka_publisher_pass_failed",
                        topic=topic,
                        error_class=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                    if run_once:
                        raise CommandError(str(exc)) from exc
                    self._sleep(sleep_seconds)
                    continue

                record_service_metric_sample(
                    metric_name="communication_kafka_publisher_heartbeat",
                    source="communication_kafka_publisher",
                    value=1,
                    unit="count",
                    dimensions={
                        "topic": topic,
                        "published": result.published,
                        "failed": result.failed,
                        "skipped": result.skipped,
                    },
                )
                log_event(
                    logger,
                    logging.INFO,
                    "communication_kafka_publisher_pass",
                    topic=topic,
                    status="completed",
                    payload={
                        "published": result.published,
                        "failed": result.failed,
                        "skipped": result.skipped,
                    },
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
                    self._sleep(sleep_seconds)
        finally:
            try:
                publisher.producer.flush(float(getattr(publisher, "flush_timeout_seconds", 5)))
            except Exception:  # noqa: BLE001 - process shutdown should continue.
                pass

    def _install_signal_handlers(self) -> None:
        def _request_stop(_signum: int, _frame: Any) -> None:
            self.stop_requested = True

        try:
            signal.signal(signal.SIGTERM, _request_stop)
            signal.signal(signal.SIGINT, _request_stop)
        except ValueError:
            return

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + max(float(seconds), 0.1)
        while not self.stop_requested and time.monotonic() < deadline:
            time.sleep(min(0.25, max(deadline - time.monotonic(), 0.0)))
