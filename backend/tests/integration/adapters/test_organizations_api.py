from __future__ import annotations

import pytest
from rest_framework.test import APIClient

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
