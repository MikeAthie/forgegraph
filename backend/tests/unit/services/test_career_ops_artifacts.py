from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_artifacts import write_career_ops_deliverable
from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AssetVersion,
    Graph,
    GraphVersion,
    Run,
    ServiceDeliverable,
    User,
)

pytestmark = pytest.mark.django_db


def _setup(user: User):
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(owner=user, organization=organization, name="CareerOps Artifact Co"),
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
    engagement = ensure_career_ops_application_engagement(company=company, actor=user)
    return engagement, run, opportunity


def test_write_career_ops_deliverable_versions_content_idempotently(user: User) -> None:
    engagement, run, opportunity = _setup(user)

    first_deliverable, first_version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=opportunity,
        deliverable_type="application_packet",
        title="Application packet",
        payload={"status": "blocked"},
    )
    second_deliverable, second_version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=opportunity,
        deliverable_type="application_packet",
        title="Application packet",
        payload={"status": "blocked"},
    )

    assert second_deliverable.id == first_deliverable.id
    assert second_version.id == first_version.id
    assert AssetVersion.objects.filter(asset=first_deliverable.artifact).count() == 1
    assert first_deliverable.visibility == "operator"
    assert first_deliverable.metadata_json["career_ops"]["live_ready"] is False


def test_write_career_ops_deliverable_new_payload_creates_new_version(user: User) -> None:
    engagement, run, opportunity = _setup(user)

    _, first_version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=opportunity,
        deliverable_type="job_evaluation_report",
        title="Evaluation",
        payload={"score": 1},
    )
    deliverable, second_version = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=opportunity,
        deliverable_type="job_evaluation_report",
        title="Evaluation",
        payload={"score": 2},
    )

    assert second_version.version_number == first_version.version_number + 1
    assert ServiceDeliverable.objects.filter(id=deliverable.id).count() == 1


def test_write_career_ops_deliverable_isolates_same_type_by_opportunity(user: User) -> None:
    engagement, run, first_opportunity = _setup(user)
    second_signal = record_scanned_job(
        company=engagement.company,
        user=user,
        posting={
            "title": "Staff AI Product Engineer",
            "company": "Beta AI",
            "url": "https://jobs.example.com/beta/456",
        },
    )
    second_opportunity = ensure_opportunity_for_signal(signal=second_signal, user=user)
    assert second_opportunity is not None

    first_deliverable, _ = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=first_opportunity,
        deliverable_type="application_packet",
        title="Application packet — Acme",
        payload={"opportunity": "acme"},
    )
    second_deliverable, _ = write_career_ops_deliverable(
        engagement=engagement,
        run=run,
        task=None,
        opportunity=second_opportunity,
        deliverable_type="application_packet",
        title="Application packet — Beta",
        payload={"opportunity": "beta"},
    )

    assert second_deliverable.id != first_deliverable.id
    assert second_deliverable.artifact_id != first_deliverable.artifact_id
    assert {
        deliverable.metadata_json["career_ops"]["opportunity_id"]
        for deliverable in ServiceDeliverable.objects.filter(
            engagement=engagement,
            deliverable_type="application_packet",
        )
    } == {
        str(first_opportunity.id),
        str(second_opportunity.id),
    }
