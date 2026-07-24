from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_approvals import request_packet_approval
from application.services.career_ops_artifacts import write_career_ops_deliverable
from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.career_ops_quality_gates import check_career_ops_packet_readiness
from application.services.career_ops_tasks import materialize_url_pipeline_tasks
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    GraphVersion,
    Run,
    ServiceDeliverable,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name=name))
    GraphVersion.objects.create(
        graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}}
    )
    return company


def _add_base_cv(company: Graph) -> None:
    organization = company.organization
    assert organization is not None
    Asset.objects.create(
        organization=organization,
        company=company,
        title="Base CV",
        asset_type="document",
        source_key="career_ops:cv_source",
        metadata_json={"career_ops": {"deliverable_type": "cv_source"}},
    )


def _posting(index: int, *, employer: str = "Acme AI") -> dict[str, object]:
    return {
        "title": f"Senior AI Product Engineer {index}",
        "company": employer,
        "url": f"https://jobs.example.com/{employer.lower().replace(' ', '-')}/{index}",
        "provider": "manual_url",
    }


def test_pipeline_keeps_deliverables_isolated_per_opportunity(user: User) -> None:
    company = _create_company(user, name="CareerOps Multi Opp Co")

    first = run_career_ops_url_pipeline(
        company=company, actor=user, posting=_posting(1), idempotency_key="multi:1"
    )
    second = run_career_ops_url_pipeline(
        company=company, actor=user, posting=_posting(2), idempotency_key="multi:2"
    )

    assert first.opportunity_id != second.opportunity_id
    assert len(set(first.deliverable_ids).intersection(second.deliverable_ids)) == 0
    assert ServiceDeliverable.objects.filter(company=company).count() == 6


def test_packet_readiness_rejects_packet_from_another_company_even_same_org(user: User) -> None:
    allowed_company = _create_company(user, name="Allowed CareerOps Co")
    other_company = _create_company(user, name="Other CareerOps Co")
    _add_base_cv(allowed_company)
    other_result = run_career_ops_url_pipeline(
        company=other_company,
        actor=user,
        posting=_posting(1, employer="Other AI"),
        idempotency_key="cross-company:other",
    )
    assert other_result.packet_asset_version_id is not None
    packet_version = AssetVersion.objects.get(id=other_result.packet_asset_version_id)

    readiness = check_career_ops_packet_readiness(
        company=allowed_company, packet_version=packet_version
    )

    assert readiness.status == "blocked"
    assert readiness.checks["packet_belongs_to_company"] == "blocked"
    assert readiness.live_send_allowed is False


def test_packet_readiness_blocks_tampered_side_effect_flag(user: User) -> None:
    company = _create_company(user, name="Tampered CareerOps Co")
    _add_base_cv(company)
    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting=_posting(1),
        idempotency_key="tampered:side-effect",
    )
    assert result.packet_asset_version_id is not None
    packet_version = AssetVersion.objects.get(id=result.packet_asset_version_id)
    provenance = packet_version.provenance_json
    provenance["career_ops"]["quality"]["external_side_effects_allowed"] = True
    packet_version.provenance_json = provenance
    packet_version.save(update_fields=["provenance_json"])

    readiness = check_career_ops_packet_readiness(company=company, packet_version=packet_version)

    assert readiness.status == "blocked"
    assert readiness.checks["side_effect_guard_disabled"] == "blocked"
    assert readiness.live_send_allowed is False


def test_request_packet_approval_replay_preserves_existing_approved_decision(user: User) -> None:
    company = _create_company(user, name="Approval Replay Co")
    organization = company.organization
    assert organization is not None
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=GraphVersion.objects.filter(graph=company).first(),
        status="running",
    )
    signal = record_scanned_job(company=company, user=user, posting=_posting(1))
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    approval_task = next(
        task
        for task in materialize_url_pipeline_tasks(
            company=company,
            run=run,
            opportunity_external_key=opportunity.external_key,
        )
        if task.source_node_id == "stage_07_candidate_approval"
    )
    engagement = ensure_career_ops_application_engagement(company=company, actor=user)
    deliverable, packet_version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=approval_task,
        opportunity=opportunity,
        deliverable_type="application_packet",
        title="Application packet",
        payload={
            "status": "draft",
            "opportunity": {"id": str(opportunity.id)},
            "source_refs": [{"type": "opportunity", "id": str(opportunity.id)}],
            "quality": {"external_side_effects_allowed": False},
        },
    )
    decision = request_packet_approval(
        run=run,
        approval_task=approval_task,
        opportunity=opportunity,
        packet_version=packet_version,
        deliverable_versions=[
            {"deliverable_id": str(deliverable.id), "asset_version_id": str(packet_version.id)}
        ],
    )
    decision.status = "approved"
    decision.resolution_json = {"approved_by": str(user.id)}
    decision.save(update_fields=["status", "resolution_json", "updated_at"])

    replay = request_packet_approval(
        run=run,
        approval_task=approval_task,
        opportunity=opportunity,
        packet_version=packet_version,
        deliverable_versions=[
            {"deliverable_id": str(deliverable.id), "asset_version_id": str(packet_version.id)}
        ],
    )

    assert replay.id == decision.id
    assert replay.status == "approved"
