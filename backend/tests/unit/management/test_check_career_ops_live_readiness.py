from __future__ import annotations

import json
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, User

pytestmark = pytest.mark.django_db


def test_check_career_ops_live_readiness_command_fails_closed(user: User) -> None:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Readiness Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    result = run_career_ops_url_pipeline(company=company, actor=user, posting={"title": "Senior AI Product Engineer", "company": "Acme AI", "url": "https://jobs.example.com/acme/123"}, idempotency_key="readiness:test")
    assert result.packet_asset_version_id is not None
    out = StringIO()

    call_command(
        "check_career_ops_live_readiness",
        company_id=str(company.id),
        packet_version_id=result.packet_asset_version_id,
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "blocked"
    assert payload["live_send_allowed"] is False
    assert payload["checks"]["base_cv_present"] == "blocked"
