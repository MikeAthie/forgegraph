from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_evaluation import evaluate_career_ops_posting
from application.services.career_ops_liveness import classify_career_ops_liveness
from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyOpportunity,
    Graph,
    GraphVersion,
    ServiceDeliverable,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "CareerOps Reference Co") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name=name))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def _add_base_cv(company: Graph) -> None:
    Asset.objects.create(
        organization=company.organization,
        company=company,
        title="Base CV",
        asset_type="document",
        source_key="career_ops:cv_source",
        metadata_json={
            "career_ops": {"deliverable_type": "cv_source"},
            "summary": "Built production multi-agent AI systems, LLM evaluation pipelines, and HITL orchestration.",
            "proof_points": [
                "Built multi-agent workflow automation with human-in-the-loop approvals.",
                "Implemented LLM observability, evals, and production reliability dashboards.",
            ],
        },
    )


def _strong_agentic_posting() -> dict[str, object]:
    return {
        "title": "Senior AI Agent Platform Engineer",
        "company": "Acme AI",
        "url": "https://jobs.example.com/acme/agent-platform",
        "provider": "manual_url",
        "location": "Remote",
        "description": """
        We need a senior engineer to build multi-agent orchestration, HITL approval workflows,
        LLM evaluation pipelines, observability, reliability, and production automation.
        Apply now to join a remote platform team. Compensation range $180k-$230k.
        """,
        "apply_controls": ["Apply now"],
        "http_status": 200,
    }


def test_liveness_classifier_matches_reference_active_expired_and_bot_challenge() -> None:
    assert classify_career_ops_liveness(status=404, body_text="missing").result == "expired"
    assert (
        classify_career_ops_liveness(
            status=200,
            body_text="This job is no longer accepting applications for this position.",
        ).code
        == "expired_body"
    )
    assert (
        classify_career_ops_liveness(
            status=200,
            body_text="Just a moment while we verify you are human",
        ).result
        == "uncertain"
    )
    active = classify_career_ops_liveness(
        status=200,
        body_text="Senior AI Engineer " + ("build platform systems " * 40),
        apply_controls=["Apply now"],
    )
    assert active.result == "active"
    assert active.code == "apply_control_visible"


def test_evaluation_builds_a_to_g_blocks_and_score_recommendation_from_jd_and_cv() -> None:
    evaluation = evaluate_career_ops_posting(
        posting=_strong_agentic_posting(),
        candidate_facts={
            "summary": "Built production multi-agent AI systems, LLM evaluation pipelines, and HITL orchestration.",
            "proof_points": ["Built multi-agent workflows", "Implemented evals and observability"],
        },
    )

    assert evaluation["archetype"]["primary"] == "Agentic / Automation"
    assert set(evaluation["blocks"]) == {
        "A_role_summary",
        "B_cv_match",
        "C_level_strategy",
        "D_comp_research",
        "E_customization_plan",
        "F_interview_plan",
        "G_posting_legitimacy",
    }
    assert evaluation["score"] >= 4.5
    assert evaluation["tracker_status"] == "evaluated"
    assert evaluation["recommendation"] == "apply"
    assert len(evaluation["draft_application_answers"]) == 5
    assert evaluation["quality"]["source_backed_claims"] is True
    assert evaluation["quality"]["external_side_effects_allowed"] is False


def test_pipeline_stops_before_evaluation_packet_and_approval_for_expired_posting(user: User) -> None:
    company = _create_company(user)
    _add_base_cv(company)

    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting={
            "title": "Senior AI Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.com/acme/expired",
            "description": "This job is no longer accepting applications.",
            "http_status": 200,
        },
        idempotency_key="expired:reference",
    )

    assert result.decision_id is None
    assert result.packet_asset_version_id is None
    assert result.blocked_reasons == ["posting_expired"]
    assert ServiceDeliverable.objects.filter(company=company, deliverable_type="job_liveness_receipt").count() == 1
    assert ServiceDeliverable.objects.filter(company=company, deliverable_type="application_packet").count() == 0
    opportunity = CompanyOpportunity.objects.get(id=result.opportunity_id)
    assert opportunity.status == "lost"
    assert opportunity.metadata_json["career_ops"]["application_status"] == "discarded"


def test_pipeline_persists_reference_like_evaluation_packet_and_answers_for_strong_match(user: User) -> None:
    company = _create_company(user)
    _add_base_cv(company)

    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_strong_agentic_posting(),
        idempotency_key="strong:reference",
    )

    assert result.decision_id
    assert result.packet_asset_version_id
    assert result.blocked_reasons == []
    packet_version = AssetVersion.objects.get(id=result.packet_asset_version_id)
    packet = packet_version.provenance_json["career_ops"]
    assert packet["evaluation"]["score"] >= 4.5
    assert packet["evaluation"]["archetype"]["primary"] == "Agentic / Automation"
    assert len(packet["artifacts"]["application_answers"]) == 5
    opportunity = CompanyOpportunity.objects.get(id=result.opportunity_id)
    assert opportunity.metadata_json["career_ops"]["score"] >= 4.5
    assert opportunity.metadata_json["career_ops"]["tracker_status"] == "evaluated"
