from __future__ import annotations

import json
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, User

pytestmark = pytest.mark.django_db


def test_run_career_ops_url_pipeline_command_returns_json(user: User) -> None:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Command Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    out = StringIO()

    call_command(
        "run_career_ops_url_pipeline",
        company_id=str(company.id),
        user_id=str(user.id),
        title="Senior AI Product Engineer",
        company_name="Acme AI",
        url="https://jobs.example.com/acme/123",
        location="Remote",
        provider="manual_url",
        idempotency_key="command:test",
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["external_side_effects_allowed"] is False
    assert payload["run_id"]
    assert payload["decision_id"]
