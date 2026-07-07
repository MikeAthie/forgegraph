"""Deterministic fake-safe CareerOps packet builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.services.career_ops_ats_simulator import simulate_career_ops_ats
from application.services.career_ops_content_alignment import (
    build_career_ops_alignment_report,
    build_cover_letter_draft,
    build_tailored_resume_draft,
)
from application.services.career_ops_evaluation import evaluate_career_ops_posting
from application.services.career_ops_graph_contract import CAREER_OPS_BASE_CV_ARTIFACT_TYPE
from infrastructure.orm.models import Asset, CompanyOpportunity, Graph


@dataclass(frozen=True, slots=True)
class CareerOpsPacketPayloads:
    liveness: dict[str, Any]
    evaluation: dict[str, Any]
    packet: dict[str, Any]
    blocked_reasons: list[str]


# Backward compatible alias for the former function name.
def build_career_ops_packet_payloads(*, company: Graph, opportunity: CompanyOpportunity) -> CareerOpsPacketPayloads:
    """Build deterministic non-live liveness, evaluation, and packet payloads."""

    career_ops = _career_ops_metadata(opportunity.metadata_json)
    posting = {**_posting_from_metadata(career_ops), "id": str(opportunity.id)}
    candidate_facts = _candidate_facts(company=company)
    evaluation = evaluate_career_ops_posting(posting=posting, candidate_facts=candidate_facts)
    blocked_reasons: list[str] = []
    if not candidate_facts:
        blocked_reasons.append("missing_cv_source")
    if evaluation["blocks"]["G_posting_legitimacy"]["liveness"]["result"] == "expired":
        blocked_reasons.append("posting_expired")
    alignment = build_career_ops_alignment_report(candidate_facts=candidate_facts, posting=posting)
    if blocked_reasons:
        alignment = {**alignment, "status": "blocked", "blocked_reasons": blocked_reasons}
    tailored_resume = None
    cover_letter = None
    ats_simulation = None
    if not blocked_reasons:
        tailored_resume = build_tailored_resume_draft(
            candidate_facts=candidate_facts,
            posting=posting,
            alignment=alignment,
        )
        cover_letter = build_cover_letter_draft(
            candidate_facts=candidate_facts,
            posting=posting,
            alignment=alignment,
        )
    source_refs = _source_refs(
        opportunity=opportunity,
        career_ops=career_ops,
        evaluation=evaluation,
        alignment=alignment,
    )
    status = "blocked" if blocked_reasons else "draft"
    quality = {
        **evaluation["quality"],
        "source_backed_claims": bool(tailored_resume and tailored_resume.get("source_refs")),
        "live_ready": False,
        "requires_candidate_approval": True,
        "external_side_effects_allowed": False,
    }
    if tailored_resume is not None:
        ats_seed_packet = {
            "status": status,
            "opportunity": {
                "id": str(opportunity.id),
                "employer_name": career_ops.get("employer_name", ""),
                "role_title": career_ops.get("role_title", ""),
                "job_url": career_ops.get("job_url", ""),
            },
            "alignment": alignment,
            "artifacts": {"tailored_resume": tailored_resume, "cover_letter": cover_letter},
            "source_refs": source_refs,
            "quality": quality,
        }
        ats_simulation = simulate_career_ops_ats(
            packet=ats_seed_packet,
            posting=posting,
            candidate_facts=candidate_facts,
        )
    quality["ats_score"] = ats_simulation.get("atsScore") if isinstance(ats_simulation, dict) else None
    quality["ats_human_review_minimum_passed"] = bool(
        isinstance(ats_simulation, dict) and ats_simulation.get("atsScore", 0) >= 85
    )
    quality["ats_send_minimum_passed"] = bool(
        isinstance(ats_simulation, dict) and ats_simulation.get("atsScore", 0) >= 90
    )
    liveness = {
        "status": "checked",
        "posting_legitimacy": evaluation["blocks"]["G_posting_legitimacy"],
        "source_refs": source_refs,
        "quality": quality,
    }
    evaluation_payload = {
        **evaluation,
        "status": "blocked" if "posting_expired" in blocked_reasons else evaluation["status"],
        "blocked_reasons": blocked_reasons,
        "source_refs": source_refs,
        "quality": quality,
    }
    packet = {
        "status": status,
        "blocked_reasons": blocked_reasons,
        "opportunity": {
            "id": str(opportunity.id),
            "employer_name": career_ops.get("employer_name", ""),
            "role_title": career_ops.get("role_title", ""),
            "job_url": career_ops.get("job_url", ""),
        },
        "evaluation": evaluation_payload,
        "alignment": alignment,
        "artifacts": {
            "tailored_resume": tailored_resume,
            "cover_letter": cover_letter,
            "ats_simulation": ats_simulation,
            "application_answers": evaluation_payload["draft_application_answers"],
        },
        "source_refs": source_refs,
        "quality": quality,
    }
    return CareerOpsPacketPayloads(
        liveness=liveness,
        evaluation=evaluation_payload,
        packet=packet,
        blocked_reasons=blocked_reasons,
    )


def has_base_cv(*, company: Graph) -> bool:
    """Return whether the company has a canonical CareerOps base CV asset."""

    return _base_cv_asset(company=company) is not None


def _base_cv_asset(*, company: Graph) -> Asset | None:
    for asset in Asset.objects.filter(company=company, status="active"):
        metadata = asset.metadata_json or {}
        career_ops = metadata.get("career_ops", {}) if isinstance(metadata, dict) else {}
        if asset.source_key == "career_ops:cv_source":
            return asset
        if isinstance(career_ops, dict) and career_ops.get("deliverable_type") == CAREER_OPS_BASE_CV_ARTIFACT_TYPE:
            return asset
    return None


def _candidate_facts(*, company: Graph) -> dict[str, Any]:
    asset = _base_cv_asset(company=company)
    if asset is None:
        return {}
    metadata = asset.metadata_json or {}
    career_ops = metadata.get("career_ops", {}) if isinstance(metadata, dict) else {}
    proof_points = metadata.get("proof_points") or career_ops.get("proof_points") or []
    if isinstance(proof_points, str):
        proof_points = [proof_points]
    facts = {
        "summary": metadata.get("summary") or career_ops.get("summary") or asset.title,
        "proof_points": [str(point) for point in proof_points if str(point).strip()],
        "asset_id": str(asset.id),
    }
    for key in ("skills", "projects", "education", "constraints"):
        value = metadata.get(key) or career_ops.get(key)
        if value:
            facts[key] = value
    return facts


def _posting_from_metadata(career_ops: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": career_ops.get("role_title", "Untitled role"),
        "company": career_ops.get("employer_name", "Unknown employer"),
        "url": career_ops.get("job_url", ""),
        "provider": career_ops.get("provider", "manual_url"),
        "location": career_ops.get("location", ""),
        "description": career_ops.get("description", ""),
        "apply_controls": career_ops.get("apply_controls", []),
        "http_status": _packet_http_status(career_ops),
        "final_url": career_ops.get("final_url") or career_ops.get("job_url", ""),
    }


def _packet_http_status(career_ops: dict[str, Any]) -> int:
    status = int(career_ops.get("http_status") or 0)
    source_mode = str(career_ops.get("source_mode") or "").strip()
    posting_source_mode = str(career_ops.get("posting_source_mode") or "").strip()
    if status not in {404, 410} and (source_mode == "live_url_discovery" or posting_source_mode == "live_search_skill"):
        return 0
    return status


def _career_ops_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    career_ops = (metadata or {}).get("career_ops", {})
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _source_refs(
    *,
    opportunity: CompanyOpportunity,
    career_ops: dict[str, Any],
    evaluation: dict[str, Any],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    refs = [{"type": "opportunity", "id": str(opportunity.id)}]
    if career_ops.get("job_url"):
        refs.append({"type": "job_url", "url": str(career_ops["job_url"])})
    refs.extend(ref for ref in evaluation.get("source_refs", []) if isinstance(ref, dict))
    refs.extend(ref for ref in alignment.get("source_refs", []) if isinstance(ref, dict))
    deduped: list[dict[str, Any]] = []
    seen = set()
    for ref in refs:
        key = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if key not in seen:
            seen.add(key)
            deduped.append(ref)
    return deduped
