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
from application.services.career_ops_tasks import materialize_url_pipeline_tasks
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import DecisionRecord, Graph, GraphVersion, Run, User

pytestmark = pytest.mark.django_db


def _setup(user: User):
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(owner=user, organization=organization, name="CareerOps Approval Co"),
    )
    version = GraphVersion.objects.create(
        graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}}
    )
    run = Run.objects.create(
        owner=user, organization=organization, graph_version=version, status="running"
    )
    signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Senior AI Product Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.com/acme/123",
        },
    )
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    tasks = materialize_url_pipeline_tasks(
        company=company, run=run, opportunity_external_key=opportunity.external_key
    )
    approval_task = next(
        task for task in tasks if task.source_node_id == "stage_07_candidate_approval"
    )
    engagement = ensure_career_ops_application_engagement(company=company, actor=user)
    deliverable, version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=approval_task,
        opportunity=opportunity,
        deliverable_type="application_packet",
        title="Application packet",
        payload={"status": "blocked"},
    )
    return run, opportunity, approval_task, deliverable, version


def test_request_packet_approval_references_exact_packet_version(user: User) -> None:
    run, opportunity, approval_task, deliverable, packet_version = _setup(user)

    decision = request_packet_approval(
        run=run,
        approval_task=approval_task,
        opportunity=opportunity,
        packet_version=packet_version,
        deliverable_versions=[
            {"deliverable_id": str(deliverable.id), "asset_version_id": str(packet_version.id)}
        ],
    )
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
    assert DecisionRecord.objects.filter(organization=run.organization).count() == 1
    assert decision.context_json["career_ops"]["packet_asset_version_id"] == str(packet_version.id)
    approval_task.refresh_from_db()
    assert approval_task.current_decision_id == decision.id


def test_request_packet_approval_replay_preserves_resolved_status(user: User) -> None:
    run, opportunity, approval_task, deliverable, packet_version = _setup(user)
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
    decision.resolution_json = {"approved_by": "candidate"}
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
    assert replay.resolution_json == {"approved_by": "candidate"}
