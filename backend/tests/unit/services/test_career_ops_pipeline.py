from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_pipeline import (
    CareerOpsPipelineResult,
    ensure_career_ops_graph_version,
    run_career_ops_url_pipeline,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    GraphVersion,
    Run,
    ServiceDeliverable,
    StateProjection,
    TaskRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, with_version: bool = True) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(owner=user, organization=organization, name="CareerOps Pipeline Co"),
    )
    if with_version:
        GraphVersion.objects.create(
            graph=company,
            version=3,
            graph_json={"nodes": [], "edges": [], "metadata": {"existing": True}},
        )
    return company


def _posting(**overrides: object) -> dict[str, object]:
    posting: dict[str, object] = {
        "title": "Senior AI Product Engineer",
        "company": "Acme AI",
        "url": "https://jobs.ashbyhq.com/acme/123?utm_source=spam",
        "location": "Remote",
        "provider": "ashby",
        "description": "Build career operations systems.",
    }
    posting.update(overrides)
    return posting


def _base_cv(company: Graph) -> Asset:
    organization = company.organization
    assert organization is not None
    return Asset.objects.create(
        organization=organization,
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


def test_pipeline_result_contract_has_native_ids() -> None:
    fields = set(CareerOpsPipelineResult.__dataclass_fields__)
    assert {
        "run_id",
        "signal_id",
        "opportunity_id",
        "task_ids",
        "decision_id",
        "deliverable_ids",
        "projection_id",
        "blocked_reasons",
    }.issubset(fields)


def test_ensure_career_ops_graph_version_reuses_existing_latest(user: User) -> None:
    company = _create_company(user)

    version = ensure_career_ops_graph_version(company=company)

    assert version.version == 3
    assert GraphVersion.objects.filter(graph=company).count() == 1


def test_ensure_career_ops_graph_version_creates_minimal_contract(user: User) -> None:
    company = _create_company(user, with_version=False)

    version = ensure_career_ops_graph_version(company=company)

    assert version.version == 1
    assert version.graph_json["metadata"]["pack_id"] == "career_ops.v1"
    assert len(version.graph_json["nodes"]) == 12


def test_url_pipeline_end_to_end_materializes_native_contract(user: User) -> None:
    company = _create_company(user)

    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(),
        idempotency_key="manual:test",
    )

    assert result.run_id
    assert result.signal_id
    assert result.opportunity_id
    assert len(result.task_ids) == 6
    assert result.decision_id
    assert len(result.deliverable_ids) == 3
    assert result.projection_id
    assert "missing_cv_source" in result.blocked_reasons
    run_output = Run.objects.get(id=result.run_id).output_json
    assert isinstance(run_output, dict)
    assert run_output["career_ops"]["external_side_effects_allowed"] is False
    assert CompanySignal.objects.filter(company=company).count() == 1
    assert CompanyOpportunity.objects.filter(company=company).count() == 1
    assert TaskRecord.objects.filter(organization=company.organization).count() == 6
    assert (
        StateProjection.objects.get(id=result.projection_id).projection_type
        == "career_ops:pipeline_snapshot"
    )


def test_url_pipeline_with_base_cv_persists_resume_and_cover_letter_deliverables(
    user: User,
) -> None:
    company = _create_company(user)
    _base_cv(company)

    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(),
        idempotency_key="manual:with-cv",
    )

    assert len(result.deliverable_ids) == 11
    deliverables = ServiceDeliverable.objects.filter(company=company)
    deliverable_types = {deliverable.deliverable_type for deliverable in deliverables}
    assert {
        "job_liveness_receipt",
        "job_evaluation_report",
        "tailored_resume_html",
        "ats_resume_text",
        "ats_resume_html",
        "ats_resume_pdf",
        "ats_resume_parseability_report",
        "recruiter_evaluation_report",
        "cover_letter_draft",
        "ats_simulation_report",
        "application_packet",
    } <= deliverable_types

    opportunity_id = result.opportunity_id
    assert opportunity_id is not None
    for deliverable_type in (
        "tailored_resume_html",
        "ats_resume_text",
        "ats_resume_html",
        "ats_resume_pdf",
        "ats_resume_parseability_report",
        "recruiter_evaluation_report",
        "cover_letter_draft",
        "ats_simulation_report",
    ):
        deliverable = deliverables.get(deliverable_type=deliverable_type)
        metadata = deliverable.metadata_json["career_ops"]
        assert metadata["opportunity_id"] == opportunity_id
        assert metadata["external_side_effects_allowed"] is False
        artifact = deliverable.artifact
        assert artifact is not None
        assert artifact.metadata_json["career_ops"]["opportunity_id"] == opportunity_id
        assert artifact.metadata_json["career_ops"]["external_side_effects_allowed"] is False
    pdf_asset = deliverables.get(deliverable_type="ats_resume_pdf").artifact
    assert pdf_asset is not None
    pdf_version = pdf_asset.versions.latest("created_at")
    assert pdf_version.mime_type == "application/pdf"
    assert pdf_version.content_hash
    assert pdf_version.provenance_json["career_ops"]["parseability_status"] == "passed"
    parseability_asset = deliverables.get(
        deliverable_type="ats_resume_parseability_report"
    ).artifact
    assert parseability_asset is not None
    parseability_payload = parseability_asset.versions.latest("created_at").provenance_json[
        "career_ops"
    ]
    assert parseability_payload["status"] == "passed"
    ats_asset = deliverables.get(deliverable_type="ats_simulation_report").artifact
    assert ats_asset is not None
    ats_payload = ats_asset.versions.latest("created_at").provenance_json["career_ops"]
    assert ats_payload["format"] == "career_ops_ats_simulation_v1"
    assert ats_payload["thresholds"] == {
        "human_review": 85,
        "send_ready": 90,
        "improvement_review": 70,
    }
    recruiter_asset = deliverables.get(deliverable_type="recruiter_evaluation_report").artifact
    assert recruiter_asset is not None
    recruiter_payload = recruiter_asset.versions.latest("created_at").provenance_json["career_ops"]
    assert recruiter_payload["format"] == "career_ops_recruiter_evaluation_v1"
    assert recruiter_payload["external_side_effects_allowed"] is False
    assert set(recruiter_payload["scores"]) >= {
        "presentation",
        "role_fit",
        "professional_delivery",
        "credibility",
        "ats_readability",
    }


def test_url_pipeline_isolates_resume_and_cover_letter_assets_by_opportunity(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)

    first = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(url="https://jobs.ashbyhq.com/acme/123"),
        idempotency_key="manual:first",
    )
    second = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(
            title="Staff AI Platform Engineer",
            company="Beta AI",
            url="https://jobs.ashbyhq.com/beta/456",
        ),
        idempotency_key="manual:second",
    )

    assert first.opportunity_id != second.opportunity_id
    for deliverable_type in (
        "tailored_resume_html",
        "ats_resume_text",
        "ats_resume_html",
        "ats_resume_pdf",
        "ats_resume_parseability_report",
        "recruiter_evaluation_report",
        "cover_letter_draft",
        "ats_simulation_report",
    ):
        deliverables = list(
            ServiceDeliverable.objects.filter(company=company, deliverable_type=deliverable_type)
        )
        assert len(deliverables) == 2
        assert {
            deliverable.metadata_json["career_ops"]["opportunity_id"]
            for deliverable in deliverables
        } == {
            first.opportunity_id,
            second.opportunity_id,
        }
        assert len({deliverable.artifact_id for deliverable in deliverables}) == 2


def test_url_pipeline_replay_does_not_duplicate_signal_opportunity_or_tasks(user: User) -> None:
    company = _create_company(user)

    first = run_career_ops_url_pipeline(
        company=company, actor=user, posting=_posting(), idempotency_key="manual:test"
    )
    second = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(url="https://jobs.ashbyhq.com/acme/123?utm_campaign=again"),
        idempotency_key="manual:test",
    )

    assert second.signal_id == first.signal_id
    assert second.opportunity_id == first.opportunity_id
    assert second.task_ids == first.task_ids
    assert CompanySignal.objects.filter(company=company).count() == 1
    assert CompanyOpportunity.objects.filter(company=company).count() == 1
    assert TaskRecord.objects.filter(organization=company.organization).count() == 6
    assert Run.objects.filter(organization=company.organization).count() == 2
