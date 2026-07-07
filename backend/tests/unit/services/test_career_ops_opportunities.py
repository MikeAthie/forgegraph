from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone

from application.services.career_ops_graph_contract import CAREER_OPS_APPLIED_COOLDOWN_DAYS
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    normalize_job_key,
    record_scanned_job,
    should_skip_due_to_recent_application,
    update_application_status,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import CompanyOpportunity, CompanySignal, Graph, GraphVersion, User

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "CareerOps Test Company") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="CareerOps opportunity test company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _posting(**overrides: object) -> dict[str, object]:
    posting: dict[str, object] = {
        "title": "Senior AI Product Engineer",
        "company": "Acme AI",
        "url": "https://jobs.ashbyhq.com/acme/123?utm_source=spam",
        "location": "Remote",
        "provider": "ashby",
    }
    posting.update(overrides)
    return posting


def test_normalize_job_key_drops_tracking_query_params() -> None:
    assert normalize_job_key(
        company_name="Acme AI",
        role_title="Senior AI Product Engineer",
        url="https://jobs.ashbyhq.com/acme/123?utm_source=spam#apply",
    ) == "acme-ai:senior-ai-product-engineer:jobs.ashbyhq.com/acme/123"


def test_record_scanned_job_is_idempotent_by_normalized_url(user: User) -> None:
    company = _create_company(user)

    first = record_scanned_job(company=company, user=user, posting=_posting())
    second = record_scanned_job(
        company=company,
        user=user,
        posting=_posting(url="https://jobs.ashbyhq.com/acme/123?utm_campaign=again"),
    )

    assert second.id == first.id
    assert CompanySignal.objects.filter(company=company, source="career_ops_scan").count() == 1
    assert first.metadata_json["career_ops"]["application_status"] == "discovered"


def test_scanned_signal_creates_one_opportunity(user: User) -> None:
    company = _create_company(user)
    signal = record_scanned_job(company=company, user=user, posting=_posting())

    first = ensure_opportunity_for_signal(signal=signal, user=user)
    second = ensure_opportunity_for_signal(signal=signal, user=user)

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert CompanyOpportunity.objects.filter(company=company).count() == 1
    assert first.metadata_json["career_ops"]["employer_name"] == "Acme AI"
    assert first.metadata_json["career_ops"]["role_title"] == "Senior AI Product Engineer"


def test_recent_application_blocks_same_company_role_until_cooldown_expires(user: User) -> None:
    company = _create_company(user)
    signal = record_scanned_job(company=company, user=user, posting=_posting())
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    update_application_status(
        opportunity=opportunity,
        status="applied",
        user=user,
        applied_at=timezone.now() - timedelta(days=7),
    )

    result = should_skip_due_to_recent_application(
        company=company,
        posting=_posting(url="https://jobs.ashbyhq.com/acme/different-role-url"),
    )

    assert result["skip"] is True
    assert result["cooldown_days"] == CAREER_OPS_APPLIED_COOLDOWN_DAYS
    assert result["matched_opportunity_id"] == str(opportunity.id)


def test_application_cooldown_expires_after_30_days(user: User) -> None:
    company = _create_company(user)
    signal = record_scanned_job(company=company, user=user, posting=_posting())
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    update_application_status(
        opportunity=opportunity,
        status="applied",
        user=user,
        applied_at=timezone.now() - timedelta(days=31),
    )

    result = should_skip_due_to_recent_application(company=company, posting=_posting())

    assert result["skip"] is False
    assert result["reason"] == "cooldown_expired_or_no_match"
