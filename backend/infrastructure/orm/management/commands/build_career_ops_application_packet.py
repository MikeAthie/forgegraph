"""Build CareerOps application drafts for an existing opportunity."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.career_ops_pipeline import (
    build_career_ops_application_packet_for_opportunity,
)
from application.services.career_ops_quality_gates import check_career_ops_packet_readiness
from infrastructure.orm.models import AssetVersion, CompanyOpportunity, Graph, User


class Command(BaseCommand):
    help = "Build no-side-effect CareerOps tailored CV, cover letter, and application packet for an opportunity."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--company-id", required=True)
        parser.add_argument("--user-id", required=True)
        parser.add_argument("--opportunity-id", required=True)
        parser.add_argument("--idempotency-key", required=True)

    def handle(self, *args: object, **options: object) -> None:
        company = Graph.objects.get(id=str(options["company_id"]))
        user = User.objects.get(id=str(options["user_id"]))
        opportunity = CompanyOpportunity.objects.get(
            id=str(options["opportunity_id"]), company=company
        )
        result = build_career_ops_application_packet_for_opportunity(
            company=company,
            actor=user,
            opportunity=opportunity,
            idempotency_key=str(options["idempotency_key"]),
        )
        if result.packet_asset_version_id is None:
            raise CommandError("CareerOps packet build did not produce a packet asset version.")
        packet_version = AssetVersion.objects.get(id=result.packet_asset_version_id)
        readiness = check_career_ops_packet_readiness(
            company=company, packet_version=packet_version
        )
        payload = {
            "status": "ok",
            "run_id": result.run_id,
            "opportunity_id": result.opportunity_id,
            "task_ids": result.task_ids,
            "decision_id": result.decision_id,
            "deliverable_ids": result.deliverable_ids,
            "projection_id": result.projection_id,
            "packet_asset_version_id": result.packet_asset_version_id,
            "tailored_resume_asset_version_id": result.tailored_resume_asset_version_id,
            "ats_resume_text_asset_version_id": result.ats_resume_text_asset_version_id,
            "ats_resume_html_asset_version_id": result.ats_resume_html_asset_version_id,
            "ats_resume_pdf_asset_version_id": result.ats_resume_pdf_asset_version_id,
            "ats_resume_parseability_report_asset_version_id": result.ats_resume_parseability_report_asset_version_id,
            "recruiter_evaluation_asset_version_id": result.recruiter_evaluation_asset_version_id,
            "cover_letter_asset_version_id": result.cover_letter_asset_version_id,
            "ats_simulation_asset_version_id": result.ats_simulation_asset_version_id,
            "blocked_reasons": result.blocked_reasons,
            "readiness": {
                "status": readiness.status,
                "checks": readiness.checks,
                "blockers": readiness.blockers,
                "live_send_allowed": readiness.live_send_allowed,
            },
            "external_side_effects_allowed": False,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
