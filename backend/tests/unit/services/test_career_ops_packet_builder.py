from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.career_ops_packet_builder import build_career_ops_packet_payloads
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Asset, Graph, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Packet Co"))


def _opportunity(company: Graph, user: User):
    signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Senior AI Product Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.com/acme/123",
            "description": "Build Python FastAPI and RAG workflow systems. AWS Lambda is a plus.",
        },
    )
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    return opportunity


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


def test_build_packet_payloads_blocks_without_base_cv(user: User) -> None:
    company = _create_company(user)
    opportunity = _opportunity(company, user)

    payloads = build_career_ops_packet_payloads(company=company, opportunity=opportunity)

    assert payloads.blocked_reasons == ["missing_cv_source"]
    assert payloads.packet["status"] == "blocked"
    assert payloads.packet["quality"]["live_ready"] is False
    assert payloads.packet["quality"]["external_side_effects_allowed"] is False
    assert {ref["type"] for ref in payloads.packet["source_refs"]} >= {"opportunity", "job_url"}
    assert payloads.packet["alignment"]["status"] == "blocked"
    assert payloads.packet["artifacts"]["tailored_resume"] is None
    assert payloads.packet["artifacts"]["cover_letter"] is None


def test_build_packet_payloads_detects_base_cv_asset(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    opportunity = _opportunity(company, user)

    payloads = build_career_ops_packet_payloads(company=company, opportunity=opportunity)

    assert payloads.blocked_reasons == []
    assert payloads.packet["status"] == "draft"
    assert payloads.packet["quality"]["live_ready"] is False
    assert payloads.packet["quality"]["requires_candidate_approval"] is True
    assert payloads.packet["alignment"]["status"] == "aligned"

    resume = payloads.packet["artifacts"]["tailored_resume"]
    cover_letter = payloads.packet["artifacts"]["cover_letter"]
    ats_simulation = payloads.packet["artifacts"]["ats_simulation"]

    assert resume is not None
    assert resume["format"] == "ats_resume_v1"
    assert "FastAPI" in resume["plain_text"]
    assert "AWS Lambda" not in resume["plain_text"]
    assert cover_letter["status"] == "draft"
    assert cover_letter["format"] == "cover_letter_v1"
    assert cover_letter.get("status") != "draft_stub"
    assert ats_simulation["format"] == "career_ops_ats_simulation_v1"
    assert ats_simulation["atsScore"] >= 85
    assert ats_simulation["quality"]["external_side_effects_allowed"] is False
    assert payloads.packet["quality"]["external_side_effects_allowed"] is False
    assert payloads.packet["quality"]["ats_human_review_minimum_passed"] is True
    assert "ats_send_minimum_passed" in payloads.packet["quality"]


def test_build_packet_payloads_treats_live_search_snippet_status_as_unfetched_not_expired(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    opportunity = _opportunity(company, user)
    career_ops = dict(opportunity.metadata_json["career_ops"])
    career_ops.update(
        {
            "source_mode": "live_url_discovery",
            "posting_source_mode": "live_search_skill",
            "http_status": 200,
            "description": "Python FastAPI backend engineer for RAG workflows.",
            "apply_controls": ["Review manually"],
        }
    )
    opportunity.metadata_json = {**opportunity.metadata_json, "career_ops": career_ops}
    opportunity.save(update_fields=["metadata_json", "updated_at"])

    payloads = build_career_ops_packet_payloads(company=company, opportunity=opportunity)

    assert "posting_expired" not in payloads.blocked_reasons
    assert payloads.packet["artifacts"]["tailored_resume"] is not None
    assert payloads.packet["artifacts"]["cover_letter"] is not None
    assert payloads.packet["artifacts"]["ats_simulation"] is not None
