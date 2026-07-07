from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
    update_application_status,
)
from application.services.career_ops_tracker import (
    check_career_ops_pipeline_integrity,
    normalize_career_ops_status,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Tracker Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def _opportunity(company: Graph, user: User, *, title: str, employer: str, url: str):
    signal = record_scanned_job(company=company, user=user, posting={"title": title, "company": employer, "url": url})
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    return opportunity


def test_normalize_career_ops_status_matches_reference_aliases_and_strips_noise() -> None:
    assert normalize_career_ops_status("**Enviada** 2026-06-17") == "applied"
    assert normalize_career_ops_status("CERRADA") == "discarded"
    assert normalize_career_ops_status("no aplicar") == "skip"
    assert normalize_career_ops_status("made up") is None


def test_pipeline_integrity_flags_duplicate_company_role_and_invalid_status(user: User) -> None:
    company = _create_company(user)
    first = _opportunity(company, user, title="Senior AI Engineer", employer="Acme AI", url="https://jobs.example.com/acme/1")
    second = _opportunity(company, user, title="Senior AI Engineer", employer="Acme AI", url="https://jobs.example.com/acme/2")
    update_application_status(opportunity=first, status="applied", user=user)
    second.metadata_json["career_ops"]["application_status"] = "made up"
    second.save(update_fields=["metadata_json", "updated_at"])

    result = check_career_ops_pipeline_integrity(company=company)

    assert result["status"] == "error"
    assert result["errors"]["invalid_statuses"][0]["status"] == "made up"
    assert result["warnings"]["duplicates"][0]["employer_name"] == "Acme AI"
    assert set(result["canonical_counts"]) >= {"applied", "invalid"}


def test_pipeline_integrity_reports_clean_state_for_unique_canonical_opportunities(user: User) -> None:
    company = _create_company(user)
    first = _opportunity(company, user, title="Senior AI Engineer", employer="Acme AI", url="https://jobs.example.com/acme/1")
    second = _opportunity(company, user, title="AI Product Manager", employer="Beta AI", url="https://jobs.example.com/beta/1")
    update_application_status(opportunity=first, status="evaluated", user=user)
    update_application_status(opportunity=second, status="skip", user=user)

    result = check_career_ops_pipeline_integrity(company=company)

    assert result["status"] == "ok"
    assert result["errors"] == {"invalid_statuses": []}
    assert result["warnings"] == {"duplicates": []}
    assert result["canonical_counts"] == {"evaluated": 1, "skip": 1}
