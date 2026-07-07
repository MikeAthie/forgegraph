from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.codex_media_worker import CodexMediaWorker
from infrastructure.orm.models import Graph, Organization


class Command(BaseCommand):
    help = "Process queued ForgeGraph Codex media-generation jobs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--organization-id", default="")
        parser.add_argument("--company-id", default="")
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        organization = None
        company = None
        if options.get("organization_id"):
            organization = Organization.objects.filter(id=options["organization_id"]).first()
            if organization is None:
                raise CommandError(f"Organization not found: {options['organization_id']}")
        if options.get("company_id"):
            company = Graph.objects.filter(id=options["company_id"]).first()
            if company is None:
                raise CommandError(f"Company not found: {options['company_id']}")
        results = CodexMediaWorker().process_batch(
            limit=max(0, int(options["limit"])),
            organization=organization,
            company=company,
        )
        payload = {
            "processed": len(results),
            "results": [
                {
                    "job_id": str(result.job_id),
                    "status": result.status,
                    "error_code": result.error_code,
                }
                for result in results
            ],
        }
        if options.get("output_json"):
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Processed {payload['processed']} Codex media job(s).")
            )
