from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from infrastructure.orm.management.commands._legacy_gemini_bootstrap import (
    LegacyGeminiBootstrapError,
    safe_json_dump,
)
from infrastructure.orm.management.commands._legacy_openrouter_bootstrap import (
    DEFAULT_OPENROUTER_TEXT_MODEL,
    LEGACY_OPENROUTER_ENV,
    LEGACY_OPENROUTER_ENV_FALLBACK,
    import_legacy_openrouter_credential,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import DEFAULT_EMAIL


class Command(BaseCommand):
    help = "Import OPENROUTER into the Legacy organization as an encrypted OpenRouter BYOK key."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--env-var", default=LEGACY_OPENROUTER_ENV)
        parser.add_argument("--fallback-env-var", default=LEGACY_OPENROUTER_ENV_FALLBACK)
        parser.add_argument("--text-model", default=DEFAULT_OPENROUTER_TEXT_MODEL)
        parser.add_argument("--image-model", default=settings.OPENROUTER_IMAGE_MODEL)
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = import_legacy_openrouter_credential(
                email=str(options["email"]),
                env_var=str(options["env_var"]),
                fallback_env_var=str(options["fallback_env_var"]),
                text_model=str(options["text_model"]),
                image_model=str(options["image_model"]),
            )
        except LegacyGeminiBootstrapError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        if options["output_json"]:
            self.stdout.write(safe_json_dump(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Imported Legacy OpenRouter credential "
                f"(credential_id={payload['credential_id']}, key_present={payload['key_present']})"
            )
        )
