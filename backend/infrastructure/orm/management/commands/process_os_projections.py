from __future__ import annotations

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Compatibility alias for the incremental OS projection event worker."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--organization-id", type=str, default="")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--sleep", type=float, default=1.0)
        parser.add_argument(
            "--max-organizations",
            type=int,
            default=0,
            help="Deprecated; incremental projection processing ignores this option.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        call_command(
            "process_os_projection_events",
            organization_id=str(options.get("organization_id") or ""),
            batch_size=int(options.get("batch_size") or 100),
            once=bool(options.get("once")),
            sleep=float(options.get("sleep") or 1.0),
        )
