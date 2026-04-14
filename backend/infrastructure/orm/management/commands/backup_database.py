from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Create a JSON support backup using Django dumpdata (dev/support only, not production recovery)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Output path for the backup file.",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indent level.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output = str(options.get("output") or "").strip()
        indent = int(options.get("indent") or 2)
        if not output:
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            output = f"backups/forgegraph-backup-{timestamp}.json"

        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as fh:
            call_command("dumpdata", indent=indent, stdout=fh)

        self.stdout.write(self.style.SUCCESS(f"Backup written to {path.resolve()}"))
