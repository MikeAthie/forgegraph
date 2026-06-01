"""Integration tests for company alias APIs backed by Graph storage."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from rest_framework import status

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    GraphVersion,
    MemoryConfiguration,
    OrganizationMembership,
    User,
)

pytestmark = pytest.mark.django_db


def _member_in_owner_org(owner: User, *, role: str = "viewer") -> User:
    organization = owner.default_organization
    assert organization is not None
    member = User.objects.create_user(
        email=f"company-alias-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": role, "is_default": True},
    )
    return member


def _model_json() -> dict[str, object]:
    return {
        "nodes": [{"id": "n1", "type": "prompt", "name": "Plan"}],
        "edges": [],
        "metadata": {"company_profile": {"companyName": "Alias Co"}},
    }


def test_company_list_returns_accessible_companies_only(api_client, user):
    visible = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Visible Company",
    )
    restricted = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Restricted Company",
    )
    CompanyAccessPolicy.objects.create(
        organization=user.default_organization,
        company=restricted,
        assignment_required=True,
        org_admin_access_enabled=False,
    )

    member = _member_in_owner_org(user, role="viewer")
    api_client.force_authenticate(user=member)

    response = api_client.get("/api/companies/")

    assert response.status_code == status.HTTP_200_OK
    company_ids = {item["company_id"] for item in response.data["data"]}
    assert str(visible.id) in company_ids
    assert str(restricted.id) not in company_ids


def test_create_company_creates_graph_memory_config_and_access_policy(authenticated_client, user):
    response = authenticated_client.post(
        "/api/companies/",
        {"name": "Alias Company", "description": "Company-facing creation."},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.data["data"]
    assert data["id"] == data["company_id"] == data["workflow_definition_id"]
    assert data["storage_model"] == "Graph"
    assert data["name"] == "Alias Company"
    assert data["description"] == "Company-facing creation."
    assert data["setup_version_count"] == 0
    assert data["latest_setup_version"] is None

    company = cast(Graph, Graph.objects.get(id=data["company_id"]))
    assert company.owner == user
    assert company.organization == user.default_organization
    assert MemoryConfiguration.objects.filter(graph=company).exists()
    assert CompanyAccessPolicy.objects.filter(
        company=company,
        organization=user.default_organization,
    ).exists()


def test_create_company_requires_member_role(api_client, user):
    viewer = _member_in_owner_org(user, role="viewer")
    api_client.force_authenticate(user=viewer)

    response = api_client.post("/api/companies/", {"name": "Nope"}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"]["code"] == "FORBIDDEN"


def test_company_get_and_patch_enforce_company_assignment(api_client, user):
    company = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Assigned Company",
    )
    CompanyAccessPolicy.objects.create(
        organization=user.default_organization,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=False,
    )
    viewer = _member_in_owner_org(user, role="viewer")
    CompanyAssignment.objects.create(
        organization=user.default_organization,
        company=company,
        user=viewer,
        role="viewer",
        status="active",
        created_by=user,
    )
    api_client.force_authenticate(user=viewer)

    get_response = api_client.get(f"/api/companies/{company.id}")
    patch_response = api_client.patch(
        f"/api/companies/{company.id}",
        {"name": "Viewer Rename"},
        format="json",
    )

    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data["data"]["company_id"] == str(company.id)
    assert patch_response.status_code == status.HTTP_404_NOT_FOUND
    company.refresh_from_db()
    assert company.name == "Assigned Company"


def test_company_detail_denies_wrong_organization(api_client, user):
    company = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Private Company",
    )
    other = User.objects.create_user(
        email=f"company-alias-other-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(other)
    api_client.force_authenticate(user=other)

    response = api_client.get(f"/api/companies/{company.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_company_operating_model_version_alias_persists_graph_version(authenticated_client, user):
    company = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Model Company",
    )
    first = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    payload = _model_json()

    create_response = authenticated_client.post(
        f"/api/companies/{company.id}/operating-model-versions",
        {"model_json": payload},
        format="json",
    )
    latest_response = authenticated_client.get(
        f"/api/companies/{company.id}/operating-model-versions/latest"
    )

    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.data["data"]
    assert created["company_id"] == str(company.id)
    assert created["workflow_definition_id"] == str(company.id)
    assert created["version"] == first.version + 1
    assert created["model_json"] == payload
    assert "graph_json" not in created

    assert latest_response.status_code == status.HTTP_200_OK
    latest = latest_response.data["data"]
    assert latest["id"] == created["id"]
    assert latest["model_json"] == payload

    stored = GraphVersion.objects.get(id=created["id"])
    assert stored.graph == company
    assert stored.graph_json == payload
