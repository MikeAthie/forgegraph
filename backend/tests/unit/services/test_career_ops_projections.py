from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_pipeline import run_career_ops_url_pipeline
from application.services.career_ops_projections import (
    CAREER_OPS_PIPELINE_PROJECTION_TYPE,
    materialize_career_ops_pipeline_projection,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, StateProjection, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Projection Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def test_materialize_career_ops_pipeline_projection_rebuilds_from_durable_records(user: User) -> None:
    company = _create_company(user)
    result = run_career_ops_url_pipeline(
        company=company,
        actor=user,
        posting={"title": "Senior AI Product Engineer", "company": "Acme AI", "url": "https://jobs.example.com/acme/123"},
        idempotency_key="projection:test",
    )

    projection = materialize_career_ops_pipeline_projection(company=company)

    assert str(projection.id) == result.projection_id
    assert projection.projection_type == CAREER_OPS_PIPELINE_PROJECTION_TYPE
    assert projection.json_state["external_side_effects_allowed"] is False
    assert projection.json_state["integrity"]["status"] == "ok"
    assert projection.json_state["opportunities"][0]["decision_ids"]
    assert projection.json_state["opportunities"][0]["deliverable_ids"]
    assert StateProjection.objects.filter(company=company, projection_type=CAREER_OPS_PIPELINE_PROJECTION_TYPE).count() == 1
