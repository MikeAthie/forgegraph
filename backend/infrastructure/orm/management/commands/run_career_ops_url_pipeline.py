"""Run a dry-run CareerOps URL pipeline."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from infrastructure.orm.models import Graph, User


class Command(BaseCommand):
    help = "Run the backend-owned, no-side-effect CareerOps URL pipeline."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--company-id", required=True)
        parser.add_argument("--user-id", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--company-name", required=True)
        parser.add_argument("--url", required=True)
        parser.add_argument("--location", default="")
        parser.add_argument("--provider", default="manual_url")
        parser.add_argument("--description", default="")
        parser.add_argument("--idempotency-key", required=True)
        parser.add_argument("--json", action="store_true", dest="json_output")

    def handle(self, *args: object, **options: object) -> None:
        company = Graph.objects.get(id=str(options["company_id"]))
        user = User.objects.get(id=str(options["user_id"]))
        result = run_career_ops_url_pipeline(
            company=company,
            actor=user,
            posting={
                "title": options["title"],
                "company": options["company_name"],
                "url": options["url"],
                "location": options["location"],
                "provider": options["provider"],
                "description": options["description"],
            },
            idempotency_key=str(options["idempotency_key"]),
        )
        payload = {
            "status": "ok",
            "run_id": result.run_id,
            "signal_id": result.signal_id,
            "opportunity_id": result.opportunity_id,
            "task_ids": result.task_ids,
            "decision_id": result.decision_id,
            "deliverable_ids": result.deliverable_ids,
            "projection_id": result.projection_id,
            "packet_asset_version_id": result.packet_asset_version_id,
            "blocked_reasons": result.blocked_reasons,
            "external_side_effects_allowed": False,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
