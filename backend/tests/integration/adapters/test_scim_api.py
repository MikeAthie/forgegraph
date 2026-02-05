import pytest
from rest_framework.test import APIClient

from application.services.scim import hash_scim_token
from infrastructure.orm.models import SCIMToken, User

pytestmark = pytest.mark.django_db


def _scim_client(token: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_scim_create_and_deactivate_user(user):
    raw_token = "scim-test-token"
    SCIMToken.objects.create(
        tenant_id=user.default_organization_id,
        token_hash=hash_scim_token(raw_token),
    )
    client = _scim_client(raw_token)

    response = client.post(
        "/api/scim/v2/Users",
        {
            "userName": "scim-user@example.com",
            "name": {"givenName": "Scim", "familyName": "User"},
            "active": True,
        },
        format="json",
    )
    assert response.status_code == 201
    user_id = response.data["id"]

    delete_response = client.delete(f"/api/scim/v2/Users/{user_id}")
    assert delete_response.status_code == 204

    scim_user = User.objects.get(id=user_id)
    assert scim_user.is_active is False
