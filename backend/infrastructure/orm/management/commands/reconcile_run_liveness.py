from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from application.services.run_liveness import reconcile_stale_runs


class Command(BaseCommand):
    help = "Reconcile running runs that have stalled without backend-observed progress."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--stale-after-seconds",
            type=int,
            default=0,
            help="Override the stale-progress threshold in seconds.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of stale runs to reconcile in one pass.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        result = reconcile_stale_runs(
            stale_after_seconds=int(options.get("stale_after_seconds") or 0) or None,
            limit=int(options.get("limit") or 100),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"run_liveness scanned={result.scanned} reconciled={result.reconciled}"
            )
        )
