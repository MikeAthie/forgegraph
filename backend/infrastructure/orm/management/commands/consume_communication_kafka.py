from __future__ import annotations

import logging
import signal
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
from application.services.metrics import record_service_metric_sample
from application.services.structured_logging import log_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume committed communication Kafka metadata events into idempotent receipts."
    stop_requested = False

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
        self._install_signal_handlers()
        if not communication_kafka_enabled():
            self.stdout.write(self.style.WARNING("COMMUNICATION_KAFKA_ENABLED is false; exiting."))
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
                f"Communication Kafka consumer starting: topic={topic} group={consumer_group}"
            )
        )
        try:
            while not self.stop_requested:
                try:
                    result = consume_communication_kafka_events(
                        consumer=consumer,
                        consumer_group=consumer_group,
                        limit=limit,
                        poll_timeout_seconds=poll_timeout,
                    )
                except Exception as exc:  # noqa: BLE001 - long-running worker should surface and retry.
                    log_event(
                        logger,
                        logging.ERROR,
                        "communication_kafka_consumer_pass_failed",
                        topic=topic,
                        consumer_group=consumer_group,
                        error_class=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                    if run_once:
                        raise CommandError(str(exc)) from exc
                    self._sleep(sleep_seconds)
                    continue

                record_service_metric_sample(
                    metric_name="communication_kafka_consumer_heartbeat",
                    source="communication_kafka_consumer",
                    value=1,
                    unit="count",
                    dimensions={
                        "topic": topic,
                        "consumer_group": consumer_group,
                        "handled": result.handled,
                        "duplicates": result.duplicates,
                        "ignored": result.ignored,
                        "failed": result.failed,
                        "commit_failed": result.commit_failed,
                    },
                )
                log_event(
                    logger,
                    logging.INFO,
                    "communication_kafka_consumer_pass",
                    topic=topic,
                    consumer_group=consumer_group,
                    status="completed",
                    payload={
                        "handled": result.handled,
                        "duplicates": result.duplicates,
                        "ignored": result.ignored,
                        "failed": result.failed,
                        "commit_failed": result.commit_failed,
                        "empty_polls": result.empty_polls,
                    },
                )
                if (
                    result.handled
                    or result.duplicates
                    or result.ignored
                    or result.failed
                    or result.commit_failed
                ):
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Consumed communication Kafka pass "
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
                    self._sleep(sleep_seconds)
        finally:
            consumer.close()

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
