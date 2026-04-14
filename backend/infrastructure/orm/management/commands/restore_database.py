from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandError, call_command


class Command(BaseCommand):
    help = "Restore a JSON support backup created via backup_database (dev/support only)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--input",
            type=str,
            required=True,
            help="Path to the backup JSON file.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        input_path = str(options.get("input") or "").strip()
        if not input_path:
            raise CommandError("--input is required.")

        path = Path(input_path)
        if not path.exists():
            raise CommandError(f"Backup file not found: {path}")

        call_command("loaddata", str(path))
        self.stdout.write(self.style.SUCCESS(f"Backup restored from {path.resolve()}"))
