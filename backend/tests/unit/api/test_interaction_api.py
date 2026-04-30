from __future__ import annotations

from typing import cast

import pytest

from infrastructure.orm.models import Graph, GraphVersion, InteractionEventRecord, Run

pytestmark = pytest.mark.django_db


def _create_company(user, *, name: str = "Atlas Growth Agency OS") -> Graph:
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Operate growth systems for clients.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {
                "company_profile": {
                    "companyName": name,
                    "objective": "Operate growth systems for clients.",
                    "autonomyMode": "assisted",
                }
            },
        },
    )
    return company


def test_post_interaction_event_creates_brief_and_event(authenticated_client, user):
    company = _create_company(user)

    response = authenticated_client.post(
        "/api/interaction/events",
        data={"company_id": str(company.id), "input": "Build a lead gen system"},
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["brief"]["objective"] == "Build a lead gen system"
    assert payload["brief"]["deliverable"] == "Lead gen system"
    assert payload["interpretation"]["intent_classification"] == "CREATE"
    assert payload["pm_action"]["action"] == "ASSUME_AND_CONTINUE"
    assert payload["plan_implications"]["execution_ready"] is False
    assert InteractionEventRecord.objects.count() == 1


def test_get_current_brief_returns_existing_backend_owned_state(authenticated_client, user):
    company = _create_company(user)
    authenticated_client.post(
        "/api/interaction/events",
        data={"company_id": str(company.id), "input": "Build a lead gen system"},
        format="json",
    )

    response = authenticated_client.get(
        "/api/interaction/briefs/current",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["brief"]["id"] is not None
    assert payload["brief"]["objective"] == "Build a lead gen system"


def test_current_brief_can_be_operation_scoped(authenticated_client, user):
    company = _create_company(user)
    version = company.versions.first()
    assert version is not None
    operation = Run.objects.create(
        owner=user,
        organization=company.organization,
        graph_version=version,
        status="running",
        input_json={"operation_brief": "Run a private appointment pilot."},
    )

    response = authenticated_client.post(
        "/api/interaction/events",
        data={
            "company_id": str(company.id),
            "operation_id": str(operation.id),
            "input": "We can't use paid ads",
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["brief"]["operation_id"] == str(operation.id)
    assert payload["brief"]["constraints"] == ["Cannot use paid ads"]
    assert payload["plan_implications"]["requires_plan_revision"] is True


def test_interaction_event_rejects_operation_from_another_company(authenticated_client, user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_version = other_company.versions.first()
    assert other_version is not None
    other_operation = Run.objects.create(
        owner=user,
        organization=other_company.organization,
        graph_version=other_version,
        status="running",
    )

    response = authenticated_client.post(
        "/api/interaction/events",
        data={
            "company_id": str(company.id),
            "operation_id": str(other_operation.id),
            "input": "We can't use paid ads",
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
