from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand

from application.workers.process_os_projection_events import process_pending_projection_events


class Command(BaseCommand):
    help = "Consume backend-owned domain events into OS read-model projections."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--organization-id",
            type=str,
            default="",
            help="Process projection events for a single organization.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Maximum domain events to read per organization per pass.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one projection pass and exit.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between projection passes when not using --once.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        organization_id = str(options.get("organization_id") or "").strip() or None
        batch_size = max(int(options.get("batch_size") or 1), 1)
        run_once = bool(options.get("once"))
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)

        self.stdout.write(self.style.SUCCESS("OS projection event worker starting."))
        while True:
            result = process_pending_projection_events(
                organization_id=organization_id,
                batch_size=batch_size,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Processed OS projection events "
                    f"(processed={result.processed}, skipped={result.skipped}, "
                    f"deadlettered={result.deadlettered})."
                )
            )
            if run_once:
                return
            time.sleep(sleep_seconds)
