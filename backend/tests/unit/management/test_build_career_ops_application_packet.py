from __future__ import annotations

import json
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Asset, Graph, GraphVersion, ServiceDeliverable, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Packet Command Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


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


def test_build_career_ops_application_packet_command_builds_existing_opportunity_packet(user: User) -> None:
    company = _create_company(user)
    _base_cv(company)
    signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Backend Engineer, AI Platform",
            "company": "Acme AI",
            "url": "https://jobs.example.test/acme/backend-ai",
            "location": "Spain Remote",
            "description": "Python FastAPI PostgreSQL backend engineer for RAG workflows. AWS Lambda is a plus.",
            "provider": "fixture",
        },
    )
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    out = StringIO()

    call_command(
        "build_career_ops_application_packet",
        company_id=str(company.id),
        user_id=str(user.id),
        opportunity_id=str(opportunity.id),
        idempotency_key="packet-command:test",
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["opportunity_id"] == str(opportunity.id)
    assert payload["tailored_resume_asset_version_id"]
    assert payload["ats_resume_text_asset_version_id"]
    assert payload["ats_resume_html_asset_version_id"]
    assert payload["ats_resume_pdf_asset_version_id"]
    assert payload["ats_resume_parseability_report_asset_version_id"]
    assert payload["recruiter_evaluation_asset_version_id"]
    assert payload["cover_letter_asset_version_id"]
    assert payload["packet_asset_version_id"]
    assert payload["readiness"]["status"] == "blocked"
    assert payload["readiness"]["checks"]["tailored_resume_present"] == "pass"
    assert payload["readiness"]["checks"]["cover_letter_present"] == "pass"
    assert payload["readiness"]["checks"]["exact_version_approval_present"] == "blocked"
    assert payload["external_side_effects_allowed"] is False
    assert {
        deliverable.deliverable_type
        for deliverable in ServiceDeliverable.objects.filter(company=company, metadata_json__career_ops__opportunity_id=str(opportunity.id))
    } >= {
        "tailored_resume_html",
        "ats_resume_text",
        "ats_resume_html",
        "ats_resume_pdf",
        "ats_resume_parseability_report",
        "recruiter_evaluation_report",
        "cover_letter_draft",
        "application_packet",
    }
