from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone

from application.services.career_ops_daily_discovery import run_career_ops_daily_discovery
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
    update_application_status,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import CompanyOpportunity, Graph, GraphVersion, StateProjection, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(owner=user, organization=organization, name="CareerOps Daily Co"),
    )
    GraphVersion.objects.create(
        graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}}
    )
    return company


def _posting(index: int) -> dict[str, object]:
    return {
        "title": f"Senior AI Product Engineer {index}",
        "company": "Acme AI",
        "url": f"https://jobs.example.com/acme/{index}",
        "provider": "manual_fixture",
    }


def test_daily_discovery_empty_postings_returns_noop_summary(user: User) -> None:
    company = _create_company(user)

    summary = run_career_ops_daily_discovery(
        company=company,
        actor=user,
        postings=[],
        idempotency_key="daily:test",
    )

    assert summary["status"] == "noop"
    assert summary["external_side_effects_allowed"] is False
    assert summary["processed_count"] == 0


def test_daily_discovery_limits_evaluations_and_materializes_projection(user: User) -> None:
    company = _create_company(user)

    summary = run_career_ops_daily_discovery(
        company=company,
        actor=user,
        postings=[_posting(1), _posting(2), _posting(3)],
        idempotency_key="daily:test",
        max_evaluations=2,
    )

    assert summary["status"] == "ok"
    assert summary["processed_count"] == 2
    assert len(summary["runs"]) == 2
    assert summary["external_side_effects_allowed"] is False
    assert CompanyOpportunity.objects.filter(company=company).count() == 2
    assert (
        StateProjection.objects.filter(
            company=company, projection_type="career_ops:pipeline_snapshot"
        ).count()
        == 1
    )
    assert "missing_cv_source" in summary["blocked_reasons"]


def test_daily_discovery_passes_custom_cooldown_to_pipeline(user: User) -> None:
    company = _create_company(user)
    previous_signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Senior AI Product Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.com/acme/old",
        },
    )
    previous_opportunity = ensure_opportunity_for_signal(signal=previous_signal, user=user)
    assert previous_opportunity is not None
    update_application_status(
        opportunity=previous_opportunity,
        status="applied",
        user=user,
        applied_at=timezone.now() - timedelta(days=45),
    )

    run_career_ops_daily_discovery(
        company=company,
        actor=user,
        postings=[
            {
                "title": "Senior AI Product Engineer",
                "company": "Acme AI",
                "url": "https://jobs.example.com/acme/new",
            }
        ],
        idempotency_key="daily:cooldown",
        cooldown_days=60,
    )

    new_opportunity = CompanyOpportunity.objects.get(company=company, external_key__contains="new")
    cooldown = new_opportunity.metadata_json["career_ops"]["recent_application_cooldown"]
    assert cooldown["skip"] is True
    assert cooldown["cooldown_days"] == 60
