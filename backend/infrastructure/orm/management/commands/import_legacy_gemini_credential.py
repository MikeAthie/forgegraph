from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from infrastructure.orm.management.commands._legacy_gemini_bootstrap import (
    LEGACY_GEMINI_ENV,
    LegacyGeminiBootstrapError,
    import_legacy_gemini_credential,
    safe_json_dump,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import DEFAULT_EMAIL


class Command(BaseCommand):
    help = "Import GEMINI_LEGACY into the Legacy organization as an encrypted Google BYOK key."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--env-var", default=LEGACY_GEMINI_ENV)
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = import_legacy_gemini_credential(
                email=str(options["email"]),
                env_var=str(options["env_var"]),
            )
        except LegacyGeminiBootstrapError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        if options["output_json"]:
            self.stdout.write(safe_json_dump(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Imported Legacy Gemini credential "
                f"(credential_id={payload['credential_id']}, key_present={payload['key_present']})"
            )
        )
