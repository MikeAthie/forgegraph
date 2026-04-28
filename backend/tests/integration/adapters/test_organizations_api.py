from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from infrastructure.orm.models import Graph, GraphVersion, Organization, OrganizationMembership, Run

pytestmark = pytest.mark.django_db


def test_organization_me_exposes_memory_governance_capabilities(
    authenticated_client: APIClient,
):
    response = authenticated_client.get("/api/orgs/me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["role"] == "owner"
    assert data["governance"]["current_role_capabilities"] == {
        "can_view_observations": True,
        "can_delete_observations": True,
        "can_manage_retention": True,
        "can_export_memory_data": True,
        "can_manage_members": True,
    }
    assert data["governance"]["role_capabilities"]["member"] == {
        "can_view_observations": True,
        "can_delete_observations": True,
        "can_manage_retention": False,
        "can_export_memory_data": False,
        "can_manage_members": False,
    }
    assert data["governance"]["role_capabilities"]["viewer"] == {
        "can_view_observations": True,
        "can_delete_observations": False,
        "can_manage_retention": False,
        "can_export_memory_data": False,
        "can_manage_members": False,
    }
    assert data["organizations"][0]["id"] == str(data["organization"]["id"])
    assert data["organizations"][0]["is_default"] is True


def test_organization_list_returns_current_memberships(
    authenticated_client: APIClient,
    user,
):
    response = authenticated_client.get("/api/orgs/")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(user.default_organization_id)
    assert data[0]["role"] == "owner"
    assert data[0]["is_default"] is True


def test_organization_list_creates_default_when_missing(
    authenticated_client: APIClient,
    user,
):
    OrganizationMembership.objects.filter(user=user).delete()
    type(user).objects.filter(pk=user.pk).update(default_organization=None)
    user.default_organization = None
    user.default_organization_id = None

    response = authenticated_client.get("/api/orgs/")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["role"] == "owner"
    assert data[0]["is_default"] is True

    user.refresh_from_db()
    assert str(user.default_organization_id) == data[0]["id"]
    assert OrganizationMembership.objects.filter(
        user=user,
        organization_id=data[0]["id"],
        is_default=True,
    ).exists()


def test_create_organization_adds_owner_membership_and_switches_default(
    authenticated_client: APIClient,
    user,
):
    original_org_id = user.default_organization_id

    response = authenticated_client.post(
        "/api/orgs/",
        {"name": "New Venture"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "New Venture"
    assert data["role"] == "owner"
    assert data["is_default"] is True

    user.refresh_from_db()
    assert str(user.default_organization_id) == data["id"]
    assert user.default_organization_id != original_org_id
    assert OrganizationMembership.objects.filter(
        user=user,
        organization_id=data["id"],
        role="owner",
        is_default=True,
    ).exists()


def test_create_organization_accepts_slashless_collection_path(
    authenticated_client: APIClient,
):
    response = authenticated_client.post(
        "/api/orgs",
        {"name": "Slashless Venture"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "Slashless Venture"
    assert data["role"] == "owner"
    assert data["is_default"] is True


def test_switch_current_organization_requires_membership(
    authenticated_client: APIClient,
):
    other_org = Organization.objects.create(name="Other Organization")

    response = authenticated_client.patch(
        "/api/orgs/current",
        {"organization_id": str(other_org.id)},
        format="json",
    )

    assert response.status_code == 403


def test_switching_organization_scopes_graphs_and_runs(
    authenticated_client: APIClient,
    user,
):
    original_org_id = user.default_organization_id
    graph = Graph.objects.create(owner=user, name="Original Org Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    Run.objects.create(owner=user, graph_version=version, status="succeeded")

    create_response = authenticated_client.post(
        "/api/orgs/",
        {"name": "Second Organization"},
        format="json",
    )
    assert create_response.status_code == 201
    new_org_id = create_response.json()["data"]["id"]
    assert new_org_id != str(original_org_id)

    graph_list_response = authenticated_client.get("/api/graphs/")
    run_list_response = authenticated_client.get("/api/runs/")

    assert graph_list_response.status_code == 200
    assert run_list_response.status_code == 200
    assert graph_list_response.json()["data"] == []
    assert run_list_response.json()["data"] == []

    graph_create_response = authenticated_client.post(
        "/api/graphs/",
        {"name": "Second Org Graph"},
        format="json",
    )
    assert graph_create_response.status_code == 201
    assert graph_create_response.json()["data"]["organization_id"] == new_org_id

    graph.refresh_from_db()
    assert str(graph.organization_id) == str(original_org_id)
