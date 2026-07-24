"""Fail-closed CareerOps packet readiness checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from application.services.career_ops_content_alignment import (
    ATS_REQUIRED_SECTIONS,
    INTERNAL_LEAKAGE_TOKENS,
    OPTIMIZED_BACKEND_SECTIONS,
)
from application.services.career_ops_packet_builder import has_base_cv
from infrastructure.orm.models import (
    AssetVersion,
    CompanyOpportunity,
    DecisionRecord,
    Graph,
    ServiceDeliverable,
)


@dataclass(frozen=True, slots=True)
class CareerOpsReadinessResult:
    status: str
    checks: dict[str, str]
    blockers: list[str]
    live_send_allowed: bool = False


def check_career_ops_packet_readiness(
    *, company: Graph, packet_version: AssetVersion
) -> CareerOpsReadinessResult:
    """Return read-only readiness for a packet version, failing closed by default."""

    checks: dict[str, str] = {}
    checks["base_cv_present"] = "pass" if has_base_cv(company=company) else "blocked"
    checks["packet_belongs_to_company"] = (
        "pass" if packet_version.asset.company_id == company.id else "blocked"
    )
    source_refs = _source_refs(packet_version)
    checks["source_refs_present"] = "pass" if source_refs else "blocked"
    checks["no_internal_leakage"] = (
        "pass" if not _has_internal_leakage(packet_version.provenance_json) else "blocked"
    )
    checks["employer_identity_matches"] = (
        "pass"
        if _has_company_opportunity_ref(company=company, packet_version=packet_version)
        else "blocked"
    )
    payload = _career_ops_payload(packet_version)
    artifacts = _artifacts(payload)
    tailored_resume = artifacts.get("tailored_resume")
    cover_letter = artifacts.get("cover_letter")
    ats_simulation = artifacts.get("ats_simulation")
    checks["tailored_resume_present"] = "pass" if _is_draft_payload(tailored_resume) else "blocked"
    checks["cover_letter_present"] = "pass" if _is_draft_payload(cover_letter) else "blocked"
    checks["ats_simulation_report_present"] = (
        "pass" if _is_ats_simulation_report(ats_simulation) else "blocked"
    )
    checks["ats_human_review_minimum"] = (
        "pass" if _ats_score_at_least(ats_simulation, 85) else "blocked"
    )
    checks["ats_send_minimum"] = "pass" if _ats_score_at_least(ats_simulation, 90) else "blocked"
    ats_pdf_version = _ats_resume_pdf_version(company=company, packet_version=packet_version)
    parseability_report = _ats_resume_parseability_report(
        company=company, packet_version=packet_version
    )
    checks["ats_resume_pdf_present"] = "pass" if ats_pdf_version is not None else "blocked"
    checks["ats_resume_pdf_mime_type"] = (
        "pass"
        if ats_pdf_version is not None and ats_pdf_version.mime_type == "application/pdf"
        else "blocked"
    )
    checks["ats_resume_parseability_passed"] = (
        "pass" if _parseability_report_passed(parseability_report) else "blocked"
    )
    checks["ats_resume_pdf_exact_version_bound"] = (
        "pass"
        if _ats_pdf_bound_to_packet(
            company=company, packet_version=packet_version, pdf_version=ats_pdf_version
        )
        else "blocked"
    )
    checks["ats_resume_structure"] = (
        "pass" if _has_required_ats_sections(tailored_resume) else "blocked"
    )
    checks["claim_source_map"] = (
        "pass"
        if _has_claim_source_map(packet=payload, resume=tailored_resume, cover_letter=cover_letter)
        else "blocked"
    )
    checks["no_document_internal_leakage"] = (
        "pass"
        if not _has_document_internal_leakage(resume=tailored_resume, cover_letter=cover_letter)
        else "blocked"
    )
    checks["exact_version_approval_present"] = (
        "pass"
        if _has_exact_version_approval(company=company, packet_version=packet_version)
        else "blocked"
    )
    checks["side_effect_guard_disabled"] = (
        "pass"
        if _side_effect_guard_disabled(company=company, packet_version=packet_version)
        else "blocked"
    )
    blockers = [name for name, status in checks.items() if status != "pass"]
    return CareerOpsReadinessResult(
        status="ready" if not blockers else "blocked",
        checks=checks,
        blockers=blockers,
        live_send_allowed=False,
    )


def _source_refs(packet_version: AssetVersion) -> list[Any]:
    payload = _career_ops_payload(packet_version)
    refs = payload.get("source_refs", []) if isinstance(payload, dict) else []
    return refs if isinstance(refs, list) else []


def _has_company_opportunity_ref(*, company: Graph, packet_version: AssetVersion) -> bool:
    opportunity_id = _payload_opportunity_id(packet_version)
    if not opportunity_id:
        return False
    return CompanyOpportunity.objects.filter(id=opportunity_id, company=company).exists()


def _payload_opportunity_id(packet_version: AssetVersion) -> str | None:
    payload = _career_ops_payload(packet_version)
    if not isinstance(payload, dict):
        return None
    opportunity = payload.get("opportunity", {})
    if isinstance(opportunity, dict) and opportunity.get("id"):
        return str(opportunity["id"])
    for ref in _source_refs(packet_version):
        if isinstance(ref, dict) and ref.get("type") == "opportunity" and ref.get("id"):
            return str(ref["id"])
    return None


def _career_ops_payload(packet_version: AssetVersion) -> dict[str, Any]:
    provenance = packet_version.provenance_json or {}
    career_ops = provenance.get("career_ops", {}) if isinstance(provenance, dict) else {}
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    artifacts = payload.get("artifacts", {}) if isinstance(payload, dict) else {}
    return artifacts if isinstance(artifacts, dict) else {}


def _is_draft_payload(value: object) -> bool:
    return isinstance(value, dict) and value.get("status") == "draft"


def _is_ats_simulation_report(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("format") == "career_ops_ats_simulation_v1"
        and isinstance(value.get("atsScore"), int | float)
        and _quality_flag(value, "external_side_effects_allowed") is False
    )


def _ats_score_at_least(value: object, threshold: int) -> bool:
    if not _is_ats_simulation_report(value):
        return False
    assert isinstance(value, dict)
    score = value.get("atsScore")
    return isinstance(score, int | float) and score >= threshold


def _ats_resume_pdf_version(*, company: Graph, packet_version: AssetVersion) -> AssetVersion | None:
    deliverable = _opportunity_deliverable(
        company=company,
        packet_version=packet_version,
        deliverable_type="ats_resume_pdf",
    )
    if deliverable is None or deliverable.artifact is None:
        return None
    metadata = (
        deliverable.metadata_json.get("career_ops", {})
        if isinstance(deliverable.metadata_json, dict)
        else {}
    )
    version_id = str(metadata.get("asset_version_id") or "") if isinstance(metadata, dict) else ""
    if version_id:
        version = AssetVersion.objects.filter(id=version_id, asset=deliverable.artifact).first()
        if version is not None:
            return version
    return (
        AssetVersion.objects.filter(asset=deliverable.artifact).order_by("-version_number").first()
    )


def _ats_resume_parseability_report(
    *, company: Graph, packet_version: AssetVersion
) -> dict[str, Any] | None:
    deliverable = _opportunity_deliverable(
        company=company,
        packet_version=packet_version,
        deliverable_type="ats_resume_parseability_report",
    )
    if deliverable is None or deliverable.artifact is None:
        return None
    version = (
        AssetVersion.objects.filter(asset=deliverable.artifact).order_by("-version_number").first()
    )
    if version is None:
        return None
    payload = _career_ops_payload(version)
    return payload if isinstance(payload, dict) else None


def _opportunity_deliverable(
    *, company: Graph, packet_version: AssetVersion, deliverable_type: str
) -> ServiceDeliverable | None:
    opportunity_id = _payload_opportunity_id(packet_version)
    if not opportunity_id:
        return None
    return (
        ServiceDeliverable.objects.filter(
            company=company,
            deliverable_type=deliverable_type,
            metadata_json__career_ops__opportunity_id=opportunity_id,
        )
        .select_related("artifact")
        .first()
    )


def _parseability_report_passed(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("format") == "career_ops_ats_resume_parseability_v1"
        and value.get("status") == "passed"
        and value.get("external_side_effects_allowed") is False
    )


def _ats_pdf_bound_to_packet(
    *, company: Graph, packet_version: AssetVersion, pdf_version: AssetVersion | None
) -> bool:
    if pdf_version is None or pdf_version.asset.company_id != company.id:
        return False
    opportunity_id = _payload_opportunity_id(packet_version)
    payload = _career_ops_payload(pdf_version)
    return bool(opportunity_id and payload.get("opportunity_id") == opportunity_id)


def _has_required_ats_sections(resume: object) -> bool:
    if not isinstance(resume, dict):
        return False
    sections = resume.get("sections", [])
    if not isinstance(sections, list):
        return False
    headings = [
        str(section.get("heading") or "") for section in sections if isinstance(section, dict)
    ]
    return tuple(headings) in {ATS_REQUIRED_SECTIONS, OPTIMIZED_BACKEND_SECTIONS}


def _has_claim_source_map(*, packet: dict[str, Any], resume: object, cover_letter: object) -> bool:
    if not isinstance(resume, dict) or not isinstance(cover_letter, dict):
        return False
    if not _quality_flag(resume, "source_backed_claims") or not _quality_flag(
        cover_letter, "source_backed_claims"
    ):
        return False
    if not _quality_flag(packet.get("alignment", {}), "no_invented_candidate_facts"):
        return False
    if not _non_empty_claim_map(resume) or not _non_empty_claim_map(cover_letter):
        return False
    return _section_claims_have_sources(resume)


def _quality_flag(payload: object, key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    quality = payload.get("quality", {})
    return isinstance(quality, dict) and quality.get(key) is True


def _non_empty_claim_map(payload: dict[str, Any]) -> bool:
    claim_map = payload.get("claim_source_map", [])
    if not isinstance(claim_map, list) or not claim_map:
        return False
    return all(
        isinstance(item, dict) and item.get("claim") and item.get("source_ref")
        for item in claim_map
    )


def _section_claims_have_sources(resume: dict[str, Any]) -> bool:
    sections = resume.get("sections", [])
    if not isinstance(sections, list):
        return False
    for section in sections:
        if not isinstance(section, dict):
            return False
        if section.get("heading") not in {"SELECTED EXPERIENCE", "PROJECTS", "EDUCATION"}:
            continue
        items = section.get("items", [])
        if not isinstance(items, list):
            return False
        for item in items:
            if isinstance(item, dict) and item.get("text") and not item.get("source_ref"):
                return False
            if not isinstance(item, dict) and str(item).strip():
                return False
    return True


def _has_exact_version_approval(*, company: Graph, packet_version: AssetVersion) -> bool:
    opportunity_id = _payload_opportunity_id(packet_version)
    if (
        not opportunity_id
        or not CompanyOpportunity.objects.filter(id=opportunity_id, company=company).exists()
    ):
        return False
    for decision in DecisionRecord.objects.filter(
        organization=company.organization, decision_type="human_approval"
    ):
        career_ops = (decision.context_json or {}).get("career_ops", {})
        if not isinstance(career_ops, dict):
            continue
        if career_ops.get("packet_asset_version_id") != str(packet_version.id):
            continue
        if career_ops.get("packet_asset_id") != str(packet_version.asset_id):
            continue
        if career_ops.get("opportunity_id") != opportunity_id:
            continue
        return decision.status == "approved"
    return False


def _side_effect_guard_disabled(*, company: Graph, packet_version: AssetVersion) -> bool:
    if packet_version.asset.company_id != company.id:
        return False
    guard_sources: list[object] = [
        packet_version.provenance_json,
        packet_version.asset.metadata_json,
    ]
    guard_sources.extend(
        deliverable.metadata_json
        for deliverable in ServiceDeliverable.objects.filter(artifact=packet_version.asset)
    )
    return not any(_contains_side_effect_enabled(source) for source in guard_sources) and any(
        _contains_side_effect_disabled(source) for source in guard_sources
    )


def _contains_side_effect_enabled(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "external_side_effects_allowed" and child is True:
                return True
            if _contains_side_effect_enabled(child):
                return True
    if isinstance(value, list):
        return any(_contains_side_effect_enabled(child) for child in value)
    return False


def _contains_side_effect_disabled(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "external_side_effects_allowed" and child is False:
                return True
            if _contains_side_effect_disabled(child):
                return True
    if isinstance(value, list):
        return any(_contains_side_effect_disabled(child) for child in value)
    return False


def _has_internal_leakage(value: object) -> bool:
    for text in _string_values(value):
        lowered = text.casefold()
        if any(token in lowered for token in INTERNAL_LEAKAGE_TOKENS):
            return True
    return False


def _has_document_internal_leakage(*, resume: object, cover_letter: object) -> bool:
    document_parts = []
    if isinstance(resume, dict):
        document_parts.extend([resume.get("plain_text"), resume.get("sections")])
    if isinstance(cover_letter, dict):
        document_parts.append(cover_letter.get("paragraphs"))
    return _has_internal_leakage(document_parts)


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values = []
        for child in value.values():
            values.extend(_string_values(child))
        return values
    if isinstance(value, list | tuple):
        values = []
        for child in value:
            values.extend(_string_values(child))
        return values
    try:
        json.dumps(value, default=str)
    except TypeError:
        return [str(value)]
    return []
