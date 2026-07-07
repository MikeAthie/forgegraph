"""CareerOps daily discovery handler shape."""

from __future__ import annotations

from typing import Any

from application.services.career_ops_graph_contract import CAREER_OPS_APPLIED_COOLDOWN_DAYS
from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.career_ops_projections import materialize_career_ops_pipeline_projection
from infrastructure.orm.models import Graph, User


def run_career_ops_daily_discovery(
    *,
    company: Graph,
    actor: User,
    postings: list[dict[str, Any]],
    idempotency_key: str,
    max_new_options: int = 10,
    max_evaluations: int = 5,
    cooldown_days: int = CAREER_OPS_APPLIED_COOLDOWN_DAYS,
) -> dict[str, Any]:
    """Process a bounded list of discovered postings without employer-facing side effects."""

    bounded_postings = postings[: max(0, min(max_new_options, max_evaluations))]
    if not bounded_postings:
        projection = materialize_career_ops_pipeline_projection(company=company)
        return {
            "status": "noop",
            "processed_count": 0,
            "runs": [],
            "projection_id": str(projection.id),
            "blocked_reasons": [],
            "external_side_effects_allowed": False,
        }

    runs: list[dict[str, Any]] = []
    blocked_reasons: set[str] = set()
    for index, posting in enumerate(bounded_postings, start=1):
        result = run_career_ops_url_pipeline(
            company=company,
            actor=actor,
            posting=posting,
            idempotency_key=f"{idempotency_key}:{index}",
            cooldown_days=cooldown_days,
        )
        runs.append(
            {
                "run_id": result.run_id,
                "opportunity_id": result.opportunity_id,
                "decision_id": result.decision_id,
                "packet_asset_version_id": result.packet_asset_version_id,
                "blocked_reasons": result.blocked_reasons,
            }
        )
        blocked_reasons.update(result.blocked_reasons)
    projection = materialize_career_ops_pipeline_projection(company=company)
    return {
        "status": "ok",
        "processed_count": len(runs),
        "runs": runs,
        "projection_id": str(projection.id),
        "blocked_reasons": sorted(blocked_reasons),
        "external_side_effects_allowed": False,
    }
