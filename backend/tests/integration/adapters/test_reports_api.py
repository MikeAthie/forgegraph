from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework import status

from infrastructure.orm.models import Graph, GraphVersion, MemoryObservation, Run

pytestmark = pytest.mark.django_db


def _create_reportable_operation(user) -> tuple[Graph, Run]:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Atlas Growth Agency OS",
        description="Agency operating model",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {
                "company_profile": {
                    "client_context": {
                        "name": "Legacy",
                        "industry": "Luxury eyewear",
                        "market": "Mexico City",
                        "tier": "VIP",
                    }
                }
            },
        },
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        input_json={"operation_brief": "Legacy campaign architecture"},
        output_json={
            "positioning": "Quiet-status luxury eyewear.",
            "target_audience": "Mexico City VIP buyers.",
            "execution_plan": {"channels": ["private appointments"]},
            "risks": ["Slow reach"],
            "recommendations": ["Approve appointment-led pilot."],
            "decision_traces": [
                {
                    "decision": "Use appointment-led pilot.",
                    "alternatives": ["paid-first"],
                    "constraints": ["VIP tone"],
                    "departments": ["Strategy"],
                    "rationale": "Protect brand perception.",
                }
            ],
            "iteration_deltas": [
                {
                    "what_changed": "Paid media was reduced.",
                    "why_changed": "Brand perception risk was higher than lead risk.",
                    "trigger": "performance and brand conflict",
                }
            ],
            "memory_attributions": [
                {
                    "memory_title": "Luxury appointment precedent",
                    "changed_reasoning": "Memory supported private appointments.",
                }
            ],
        },
    )
    MemoryObservation.objects.create(
        tenant_id=organization.id,
        graph_id=graph.id,
        run_id=run.id,
        type="case",
        title="Luxury appointment precedent",
        content="Private appointments improved fit for VIP retail.",
        scope="run",
    )
    return graph, run


def test_strategy_report_api_generates_traceable_markdown(authenticated_client, user) -> None:
    company, operation = _create_reportable_operation(user)

    response = authenticated_client.post(
        "/api/reports/strategy-report",
        {
            "company_id": str(company.id),
            "operation_id": str(operation.id),
            "audience": "client",
            "format": "md",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["format"] == "md"
    assert payload["encoding"] == "text"
    assert "Client Strategy Report: Legacy" in payload["content"]
    assert "**Strategy:** Legacy campaign architecture" in payload["content"]
    assert "Approve appointment-led pilot" in payload["content"]
    assert "Requirements shaping the choice" in payload["content"]
    assert "Prior experience supported private appointments" in payload["content"]
    assert "**Operation:**" not in payload["content"]
    assert "Memory" not in payload["content"]
    assert "operation" not in payload["content"].lower()
    assert "constraint" not in payload["content"].lower()
    assert "iteration" not in payload["content"].lower()
    assert payload["traceability"]["key_decisions"][0]["kind"] in {"operation", "deliverable"}


def test_strategy_report_api_requires_authentication(api_client, user) -> None:
    company, operation = _create_reportable_operation(user)

    response = api_client.post(
        "/api/reports/strategy-report",
        {
            "company_id": str(company.id),
            "operation_id": str(operation.id),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
