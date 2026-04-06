import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status

pytestmark = pytest.mark.django_db

LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "auth-tests",
    }
}


def test_register_creates_user(api_client):
    response = api_client.post(
        "/api/auth/register",
        {"email": "newuser@example.com", "password": "testpassword123"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["email"] == "newuser@example.com"

    User = get_user_model()
    assert User.objects.filter(email="newuser@example.com").exists()


def test_register_rejects_duplicate_email(api_client, user):
    response = api_client.post(
        "/api/auth/register",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_login_returns_tokens(api_client, user):
    response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["access"]

    refresh_cookie = response.cookies.get(settings.AUTH_REFRESH_COOKIE)
    assert refresh_cookie is not None
    assert refresh_cookie.value


def test_me_requires_authentication(api_client, user):
    response = api_client.get("/api/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_me_returns_current_user_with_jwt(api_client, user):
    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = api_client.get("/api/auth/me")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user.email


def test_refresh_rotates_and_blacklists_old_refresh(api_client, user):
    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    refresh_cookie = login_response.cookies.get(settings.AUTH_REFRESH_COOKIE)
    assert refresh_cookie is not None
    old_refresh = refresh_cookie.value

    response = api_client.post("/api/auth/refresh", {}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["access"]

    rotated_cookie = response.cookies.get(settings.AUTH_REFRESH_COOKIE)
    assert rotated_cookie is not None
    assert rotated_cookie.value
    assert rotated_cookie.value != old_refresh

    # Old refresh should be blacklisted (ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION).
    api_client.cookies[settings.AUTH_REFRESH_COOKIE] = old_refresh
    response_reuse = api_client.post("/api/auth/refresh", {}, format="json")
    assert response_reuse.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    }


@override_settings(CACHES=LOC_MEM_CACHE)
def test_logout_blacklists_refresh_token(api_client, user):
    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]
    refresh_cookie = login_response.cookies.get(settings.AUTH_REFRESH_COOKIE)
    assert refresh_cookie is not None
    refresh = refresh_cookie.value

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logout_response = api_client.post("/api/auth/logout", {}, format="json")
    assert logout_response.status_code == status.HTTP_204_NO_CONTENT

    api_client.cookies[settings.AUTH_REFRESH_COOKIE] = refresh
    refresh_response = api_client.post("/api/auth/refresh", {}, format="json")
    assert refresh_response.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    }


@override_settings(CACHES=LOC_MEM_CACHE)
def test_logout_revokes_current_access_token_for_rest(api_client, user):
    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logout_response = api_client.post("/api/auth/logout", {}, format="json")
    assert logout_response.status_code == status.HTTP_204_NO_CONTENT

    me_response = api_client.get("/api/auth/me")
    assert me_response.status_code == status.HTTP_401_UNAUTHORIZED


@override_settings(CACHES=LOC_MEM_CACHE)
def test_ws_ticket_requires_authentication_and_returns_short_lived_ticket(api_client, user):
    response = api_client.post("/api/ws-ticket", {}, format="json")
    response = api_client.post("/api/auth/ws-ticket", {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = api_client.post("/api/ws-ticket", {}, format="json")
    response = api_client.post("/api/auth/ws-ticket", {}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["ticket"]
    assert response.data["expires_in_seconds"] == settings.AUTH_WS_TICKET_TTL_SECONDS

    assert response.data["org_id"] == str(user.default_organization_id)


@override_settings(CACHES=LOC_MEM_CACHE)
@override_settings(CACHES=LOC_MEM_CACHE)

def test_logout_is_idempotent_without_refresh_cookie(api_client, user):
    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]

    api_client.cookies.clear()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = api_client.post("/api/auth/logout", {}, format="json")
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_api_routes_require_auth_except_auth_endpoints(api_client, user):
    response = api_client.get("/api/graphs/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    login_response = api_client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

    response = api_client.get("/api/graphs/")
    assert response.status_code == status.HTTP_200_OK
