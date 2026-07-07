from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.atlas_prompt_delivery import run_atlas_prompt_delivery
from infrastructure.orm.models import User


class Command(BaseCommand):
    help = "Run an Atlas client delivery from one prompt, fully inside ForgeGraph."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default="admin@forgegraph.local")
        parser.add_argument("--prompt", default="")
        parser.add_argument("--prompt-file", default="")
        parser.add_argument("--phone", required=True)
        parser.add_argument("--no-send", action="store_true")
        parser.add_argument("--whatsapp-bridge-url", default="http://127.0.0.1:3008")
        parser.add_argument("--codex-command", default="")
        parser.add_argument("--codex-workdir", default="")
        parser.add_argument("--codex-timeout-seconds", type=int, default=600)
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        prompt = str(options.get("prompt") or "").strip()
        prompt_file = str(options.get("prompt_file") or "").strip()
        if prompt_file:
            prompt = Path(prompt_file).read_text(encoding="utf-8").strip()
        if not prompt:
            raise CommandError("Provide --prompt or --prompt-file.")

        user = (
            User.objects.filter(email=options["email"]).first()
            or User.objects.order_by("date_joined").first()
        )
        if user is None:
            raise CommandError("No ForgeGraph user exists for Atlas prompt delivery.")

        settings.ENABLE_CODEX_SESSION_RUNTIME = True
        if options.get("codex_command"):
            settings.CODEX_SESSION_COMMAND = str(options["codex_command"])
        workdir = str(options.get("codex_workdir") or "").strip()
        if workdir:
            workdir_path = Path(workdir)
            workdir_path.mkdir(parents=True, exist_ok=True)
            if not (workdir_path / ".git").exists():
                import subprocess

                subprocess.run(
                    ["git", "init"],
                    cwd=workdir_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            settings.CODEX_SESSION_WORKDIR = str(workdir_path)
        settings.CODEX_SESSION_TIMEOUT_SECONDS = int(options["codex_timeout_seconds"])

        result = run_atlas_prompt_delivery(
            user=user,
            prompt=prompt,
            phone_e164=str(options["phone"]),
            send=not bool(options["no_send"]),
            whatsapp_bridge_url=str(options["whatsapp_bridge_url"]),
        )
        payload = {
            "engagement_id": str(result.engagement_id),
            "whiteboard_id": str(result.whiteboard_id),
            "package_path": result.package_path,
            "package_sha256": result.package_sha256,
            "text_message_id": result.text_message_id,
            "media_message_id": result.media_message_id,
            "receipt_id": str(result.receipt_id) if result.receipt_id else None,
            "media_job_ids": result.media_job_ids,
        }
        if options.get("output_json"):
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(self.style.SUCCESS(json.dumps(payload, indent=2)))
