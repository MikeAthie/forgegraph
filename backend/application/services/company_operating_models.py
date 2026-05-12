"""Company operating model installation read services."""

from __future__ import annotations

from typing import Any

from application.services.company_programs import program_payload
from application.services.operating_model_packs import installation_payload
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    CompanyProgram,
    EvaluationProfile,
    Graph,
    PeriodicReviewDefinition,
    PolicyPack,
    SignalTaxonomy,
)


def company_operating_model_payload(company: Graph) -> dict[str, Any]:
    installations = CompanyOperatingModelInstallation.objects.filter(
        company=company
    ).select_related("pack_release")
    programs = CompanyProgram.objects.filter(company=company).order_by("-updated_at")[:50]
    return {
        "company_id": str(company.id),
        "installed_packs": [installation_payload(item) for item in installations],
        "programs": [program_payload(program, include_stages=False) for program in programs],
        "evaluation_profiles": list(
            EvaluationProfile.objects.filter(company=company, status="active").values(
                "profile_id", "display_name", "mode"
            )
        ),
        "periodic_reviews": [
            {
                "id": str(item.id),
                "template_id": item.template_id,
                "display_name": item.display_name,
                "cadence": item.cadence,
                "evaluation_profile_id": item.evaluation_profile_key,
                "report_template_id": item.report_template_id,
                "history_projection_type": item.history_projection_type,
                "enabled": item.enabled,
            }
            for item in PeriodicReviewDefinition.objects.filter(company=company).order_by(
                "display_name"
            )[:50]
        ],
        "policy_packs": list(
            PolicyPack.objects.filter(company=company, status="active").values(
                "policy_pack_id", "display_name"
            )
        ),
        "signal_taxonomies": list(
            SignalTaxonomy.objects.filter(company=company, status="active").values(
                "taxonomy_id", "display_name"
            )
        ),
    }
