from __future__ import annotations

from typing import Any

from django.core.management import BaseCommand, CommandError

from config.runtime_validation import collect_runtime_validation_errors


class Command(BaseCommand):
    help = "Validate required runtime environment settings for production deployment."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Enforce production-only requirements such as callback secret and TLS config.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        errors = collect_runtime_validation_errors(strict=bool(options.get("strict")))
        if errors:
            for error in errors:
                self.stderr.write(f"- {error}")
            raise CommandError("Runtime environment validation failed.")
        self.stdout.write(self.style.SUCCESS("Runtime environment validation passed."))
