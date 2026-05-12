from __future__ import annotations

from typing import Any, cast

import pytest

from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    OrganizationMembership,
    ProcessedCommand,
    Run,
    TaskLifecycleRecord,
)

pytestmark = pytest.mark.django_db


def _payload(**overrides):
    payload = {
        "company_name": "Acme Growth",
        "objective": "Plan, produce, and improve a repeatable outbound growth motion.",
        "blueprint_id": "digital_marketing_pro.v1",
        "services": ["Campaign planning", "Messaging", "Performance analysis"],
        "regions": ["US", "Mexico"],
        "autonomy_mode": "assisted",
        "ai_access_mode": "managed",
        "intelligence_provider": "openai",
    }
    payload.update(overrides)
    return payload


def test_compile_company_blueprint_is_read_only(authenticated_client):
    before = {
        "graphs": Graph.objects.count(),
        "versions": GraphVersion.objects.count(),
        "runs": Run.objects.count(),
        "processed_commands": ProcessedCommand.objects.count(),
    }

    response = authenticated_client.post(
        "/api/company-blueprints/compile",
        data=_payload(),
        format="json",
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert GraphValidator().validate(data["graph_json"], strict=True) == []
    assert data["template_ids"][0] == "operating_model_pack:digital_marketing_pro.v1"
    assert (
        data["graph_json"]["metadata"]["operating_model_pack"]["pack_id"]
        == "digital_marketing_pro.v1"
    )
    assert data["graph_json"]["metadata"]["company_profile"]["selectedServices"] == [
        "Campaign planning",
        "Messaging",
        "Performance analysis",
    ]
    assert data["graph_json"]["metadata"]["company_profile"]["regions"] == ["US", "Mexico"]
    assert Graph.objects.count() == before["graphs"]
    assert GraphVersion.objects.count() == before["versions"]
    assert Run.objects.count() == before["runs"]
    assert ProcessedCommand.objects.count() == before["processed_commands"]


def test_company_from_blueprint_requires_idempotency(authenticated_client):
    response = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=_payload(),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_company_from_blueprint_requires_member_role(authenticated_client, user):
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=_payload(),
        format="json",
        HTTP_IDEMPOTENCY_KEY="company-from-blueprint-viewer",
    )

    assert response.status_code == 403
    assert Graph.objects.count() == 0
    assert GraphVersion.objects.count() == 0
    assert Run.objects.count() == 0


def test_company_from_blueprint_byok_requires_credential(authenticated_client):
    response = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=_payload(ai_access_mode="byok"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="company-from-blueprint-byok-missing",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert Graph.objects.count() == 0
    assert GraphVersion.objects.count() == 0


def test_company_from_blueprint_creates_company_version_and_first_operation_idempotently(
    authenticated_client,
):
    payload = _payload(
        launch_first_operation=True,
        operation_brief="Prepare the first campaign learning brief.",
    )

    first = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="company-from-blueprint-1",
    )
    second = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="company-from-blueprint-1",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["company_id"] == second_data["company_id"]
    assert first_data["graph_version_id"] == second_data["graph_version_id"]
    assert first_data["first_operation_id"] == second_data["first_operation_id"]
    assert first_data["idempotent_replay"] is False
    assert second_data["idempotent_replay"] is True
    assert second_data["duplicate"] is True

    assert Graph.objects.count() == 1
    assert GraphVersion.objects.count() == 1
    assert Run.objects.count() == 1
    assert ProcessedCommand.objects.count() == 1

    company = Graph.objects.get()
    version = GraphVersion.objects.get()
    run = Run.objects.get()
    dispatch_graph_json = cast(dict[str, Any], run.dispatch_graph_json)
    assert version.graph == company
    assert run.graph_version == version
    assert run.status == "pending"
    assert run.input_json["operation_brief"] == "Prepare the first campaign learning brief."
    assert run.input_json["operating_model_pack"]["pack_id"] == "digital_marketing_pro.v1"
    assert dispatch_graph_json["metadata"]["company_profile"]["schema"] == "company_workspace.v1"
    assert dispatch_graph_json["metadata"]["llm_access"] == {
        "llm_mode": "managed",
        "provider": "openai",
        "api_key_present": False,
    }
    executable_nodes = [
        node
        for node in dispatch_graph_json["nodes"]
        if node.get("type") not in {"input", "output", "trigger", "note", "comment"}
    ]
    assert TaskLifecycleRecord.objects.filter(run=run).count() == len(executable_nodes)


def test_company_from_blueprint_without_launch_does_not_create_first_operation(
    authenticated_client,
):
    response = authenticated_client.post(
        "/api/companies/from-blueprint",
        data=_payload(launch_first_operation=False),
        format="json",
        HTTP_IDEMPOTENCY_KEY="company-from-blueprint-no-launch",
    )

    assert response.status_code == 201
    assert response.json()["data"]["first_operation_id"] is None
    assert Graph.objects.count() == 1
    assert GraphVersion.objects.count() == 1
    assert Run.objects.count() == 0
