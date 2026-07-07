from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.career_ops_quality_gates import check_career_ops_packet_readiness
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    GraphVersion,
    ServiceDeliverable,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Quality Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def _packet_version(company: Graph, user: User) -> AssetVersion:
    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting={
            "title": "Senior AI Product Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.com/acme/123",
            "description": "Build Python FastAPI and RAG workflow systems. AWS Lambda is a plus.",
        },
        idempotency_key="quality:test",
    )
    asset_version_id = result.packet_asset_version_id
    assert asset_version_id is not None
    return AssetVersion.objects.get(id=asset_version_id)


def _base_cv(company: Graph) -> Asset:
    return Asset.objects.create(
        organization=company.organization,
        company=company,
        title="Base CV",
        asset_type="document",
        source_key="career_ops:cv_source",
        metadata_json={
            "summary": "Backend engineer building Python APIs and AI workflow systems.",
            "proof_points": [
                "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
                "Delivered RAG and agentic workflow prototypes with observability.",
            ],
            "career_ops": {"deliverable_type": "cv_source"},
        },
    )


def _deliverable_for_packet(packet_version: AssetVersion, deliverable_type: str) -> ServiceDeliverable:
    opportunity_id = packet_version.provenance_json["career_ops"]["opportunity"]["id"]
    return ServiceDeliverable.objects.get(
        company=packet_version.asset.company,
        deliverable_type=deliverable_type,
        metadata_json__career_ops__opportunity_id=opportunity_id,
    )


def test_packet_readiness_fails_closed_without_base_cv(user: User) -> None:
    company = _create_company(user)
    version = _packet_version(company, user)

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["base_cv_present"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_internal_leakage(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    version.provenance_json = {"career_ops": {"content": "This leaks Hermes prompt metadata_json"}}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["no_internal_leakage"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_missing_tailored_resume(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["tailored_resume"] = None
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["tailored_resume_present"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_missing_cover_letter(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["cover_letter"] = None
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["cover_letter_present"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_resume_without_required_ats_sections(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    resume = payload["artifacts"]["tailored_resume"]
    resume["sections"] = [section for section in resume["sections"] if section["heading"] != "EDUCATION"]
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_resume_structure"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_unsupported_candidate_claim(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    resume = payload["artifacts"]["tailored_resume"]
    resume["sections"][2]["items"].append({"text": "Shipped unsupported AWS Lambda systems."})
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["claim_source_map"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_internal_leakage_in_resume_text(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["tailored_resume"]["plain_text"] = "This leaks Hermes metadata_json prompt details."
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["no_document_internal_leakage"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_missing_ats_simulation_report(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["ats_simulation"] = None
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_simulation_report_present"] == "blocked"
    assert readiness.checks["ats_human_review_minimum"] == "blocked"
    assert readiness.checks["ats_send_minimum"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_human_review_when_ats_score_under_85(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["ats_simulation"]["atsScore"] = 84
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_simulation_report_present"] == "pass"
    assert readiness.checks["ats_human_review_minimum"] == "blocked"
    assert readiness.checks["ats_send_minimum"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_distinguishes_human_review_from_send_threshold(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    payload = version.provenance_json["career_ops"]
    payload["artifacts"]["ats_simulation"]["atsScore"] = 87
    version.provenance_json = {"career_ops": payload}
    version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_simulation_report_present"] == "pass"
    assert readiness.checks["ats_human_review_minimum"] == "pass"
    assert readiness.checks["ats_send_minimum"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_failed_ats_pdf_parseability_report(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    report_deliverable = _deliverable_for_packet(version, "ats_resume_parseability_report")
    report_version = report_deliverable.artifact.versions.latest("created_at")
    report_payload = report_version.provenance_json["career_ops"]
    report_payload["status"] = "blocked"
    report_payload["blockers"] = ["missing_section:EDUCATION"]
    report_version.provenance_json = {"career_ops": report_payload}
    report_version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_resume_pdf_present"] == "pass"
    assert readiness.checks["ats_resume_pdf_mime_type"] == "pass"
    assert readiness.checks["ats_resume_parseability_passed"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_missing_ats_pdf_deliverable(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)
    _deliverable_for_packet(version, "ats_resume_pdf").delete()

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["ats_resume_pdf_present"] == "blocked"
    assert readiness.checks["ats_resume_pdf_mime_type"] == "blocked"
    assert readiness.checks["ats_resume_parseability_passed"] == "pass"
    assert readiness.live_send_allowed is False


def test_packet_readiness_still_blocks_without_exact_version_approval_when_content_quality_passes(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    version = _packet_version(company, user)

    readiness = check_career_ops_packet_readiness(company=company, packet_version=version)

    assert readiness.status == "blocked"
    assert readiness.checks["tailored_resume_present"] == "pass"
    assert readiness.checks["cover_letter_present"] == "pass"
    assert readiness.checks["ats_resume_structure"] == "pass"
    assert readiness.checks["ats_simulation_report_present"] == "pass"
    assert readiness.checks["ats_resume_pdf_present"] == "pass"
    assert readiness.checks["ats_resume_pdf_mime_type"] == "pass"
    assert readiness.checks["ats_resume_parseability_passed"] == "pass"
    assert readiness.checks["ats_human_review_minimum"] == "pass"
    assert readiness.checks["ats_send_minimum"] in {"pass", "blocked"}
    assert readiness.checks["claim_source_map"] == "pass"
    assert readiness.checks["no_document_internal_leakage"] == "pass"
    assert readiness.checks["exact_version_approval_present"] == "blocked"
    assert readiness.live_send_allowed is False
