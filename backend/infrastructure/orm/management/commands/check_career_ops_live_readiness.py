"""Check fail-closed CareerOps packet live readiness."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from application.services.career_ops_quality_gates import check_career_ops_packet_readiness
from infrastructure.orm.models import AssetVersion, Graph


class Command(BaseCommand):
    help = "Check whether a CareerOps packet version is live-ready."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--company-id", required=True)
        parser.add_argument("--packet-version-id", required=True)
        parser.add_argument("--json", action="store_true", dest="json_output")

    def handle(self, *args: object, **options: object) -> None:
        company = Graph.objects.get(id=options["company_id"])
        packet_version = AssetVersion.objects.get(id=options["packet_version_id"])
        result = check_career_ops_packet_readiness(company=company, packet_version=packet_version)
        self.stdout.write(
            json.dumps(
                {
                    "status": result.status,
                    "company_id": str(company.id),
                    "packet_version_id": str(packet_version.id),
                    "checks": result.checks,
                    "blockers": result.blockers,
                    "live_send_allowed": result.live_send_allowed,
                },
                sort_keys=True,
            )
        )
