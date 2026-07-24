"""CareerOps state projection materializers."""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.utils import timezone

from application.services.career_ops_tracker import check_career_ops_pipeline_integrity
from infrastructure.orm.models import (
    CompanyOpportunity,
    DecisionRecord,
    Graph,
    ServiceDeliverable,
    StateProjection,
    TaskRecord,
)

CAREER_OPS_PIPELINE_PROJECTION_TYPE = "career_ops:pipeline_snapshot"


def materialize_career_ops_pipeline_projection(*, company: Graph) -> StateProjection:
    """Rebuild the CareerOps pipeline snapshot from durable ForgeGraph records."""

    opportunities = list(CompanyOpportunity.objects.filter(company=company).order_by("created_at"))
    opportunity_rows = [_opportunity_row(opportunity) for opportunity in opportunities]
    counts = Counter(row["application_status"] for row in opportunity_rows)
    json_state = {
        "generated_at": timezone.now().isoformat(),
        "opportunities": opportunity_rows,
        "counts": dict(counts),
        "integrity": check_career_ops_pipeline_integrity(company=company),
        "external_side_effects_allowed": False,
    }
    projection, _ = StateProjection.objects.update_or_create(
        company=company,
        program=None,
        projection_type=CAREER_OPS_PIPELINE_PROJECTION_TYPE,
        defaults={
            "organization": company.organization,
            "display_label": "CareerOps Pipeline Snapshot",
            "source_refs_json": [
                {"type": "company_opportunity", "id": str(opportunity.id)}
                for opportunity in opportunities
            ],
            "json_state": json_state,
            "markdown_summary": _markdown_summary(json_state),
            "generated_by": "system",
        },
    )
    return projection


def _opportunity_row(opportunity: CompanyOpportunity) -> dict[str, Any]:
    career_ops = _career_ops_metadata(opportunity.metadata_json)
    tasks = list(
        TaskRecord.objects.filter(
            organization=opportunity.organization,
            external_key__startswith=f"career_ops:url_pipeline:{opportunity.external_key}:",
        ).order_by("source_node_id")
    )
    decisions = list(
        DecisionRecord.objects.filter(
            organization=opportunity.organization,
            external_key__startswith=f"career_ops:packet:{opportunity.id}:approval:",
        ).order_by("created_at")
    )
    deliverables = []
    for deliverable in ServiceDeliverable.objects.filter(company=opportunity.company).order_by(
        "created_at"
    ):
        metadata = _career_ops_metadata(deliverable.metadata_json)
        if metadata.get("opportunity_id") == str(opportunity.id):
            deliverables.append(deliverable)
    return {
        "id": str(opportunity.id),
        "external_key": opportunity.external_key,
        "employer_name": career_ops.get("employer_name", ""),
        "role_title": career_ops.get("role_title", ""),
        "application_status": career_ops.get("application_status", "discovered"),
        "recent_application_cooldown": career_ops.get(
            "recent_application_cooldown", {"skip": False}
        ),
        "task_ids": [str(task.id) for task in tasks],
        "decision_ids": [str(decision.id) for decision in decisions],
        "deliverable_ids": [str(deliverable.id) for deliverable in deliverables],
        "next_action": _next_action(career_ops),
    }


def _next_action(career_ops: dict[str, Any]) -> str:
    if career_ops.get("recent_application_cooldown", {}).get("skip"):
        return "Skip due to recent same-employer same-role application cooldown."
    if career_ops.get("application_status") == "approval_pending":
        return "Review exact packet version before applying."
    return "Run CareerOps review."


def _career_ops_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    career_ops = (metadata or {}).get("career_ops", {})
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _markdown_summary(json_state: dict[str, Any]) -> str:
    total = len(json_state.get("opportunities", []))
    counts = json_state.get("counts", {})
    return f"CareerOps pipeline snapshot: {total} opportunities; statuses={counts}."
