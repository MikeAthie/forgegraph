import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_get_api_auth_sso_provider_get_sso_metadata():
    session = requests.Session()

    # Create unique email for registration
    unique_email = f"testuser+{uuid.uuid4().hex}@example.com"
    password = "StrongP@ssword123"

    # Register user
    register_payload = {
        "email": unique_email,
        "password": password
    }
    r = session.post(
        f"{BASE_URL}/api/auth/register",
        json=register_payload,
        timeout=TIMEOUT
    )
    assert r.status_code == 201, f"Registration failed: {r.status_code} {r.text}"
    user_data = r.json()
    # Basic checks for user payload
    assert "id" in user_data, f"User id missing in registration response: {user_data}"
    assert user_data.get("email") == unique_email

    # Login user
    login_payload = {
        "email": unique_email,
        "password": password
    }
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json=login_payload,
        timeout=TIMEOUT
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    login_data = r.json()
    assert "access" in login_data, "Access token missing in login response"
    # Refresh token should NOT be in JSON response
    assert "refresh" not in login_data

    access_token = login_data["access"]
    # Extract refresh token from cookies
    refresh_cookie = None
    for c in session.cookies:
        if c.name == "refresh_token":
            refresh_cookie = c.value
            break
    # Refresh token cookie is HttpOnly so we can't see value in JS but requests sees it
    assert refresh_cookie is not None, "Refresh token cookie missing after login"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Authenticated GET /api/auth/sso/provider
    r = session.get(
        f"{BASE_URL}/api/auth/sso/provider",
        headers=headers,
        timeout=TIMEOUT
    )
    assert r.status_code == 200, f"Authorized SSO provider request failed: {r.status_code} {r.text}"

    sso_data = r.json()
    # Validate top-level status presence
    assert "status" in sso_data, f"SSO provider response missing 'status': {sso_data}"
    status = sso_data["status"]
    # status must have state key
    assert "state" in status, f"SSO provider 'status' missing 'state': {status}"
    # state could be 'unavailable' if no provider configured, accept any string
    # Accept status.state either 'unavailable' or other string values
    assert isinstance(status["state"], str), f"SSO provider status.state not a string: {status['state']}"

    # Unauthenticated request should return 401
    r = requests.get(
        f"{BASE_URL}/api/auth/sso/provider",
        timeout=TIMEOUT
    )
    assert r.status_code == 401, f"Unauthenticated request to SSO provider did not return 401: {r.status_code} {r.text}"


test_get_api_auth_sso_provider_get_sso_metadata()