import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
REGISTER_URL = f"{BASE_URL}/api/auth/register"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
AUTH_ME_URL = f"{BASE_URL}/api/auth/me"

TIMEOUT = 30


def test_tc005_get_api_auth_me_authenticated_user_profile():
    # Generate a unique email address for registration
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "TestPassword123!"

    # Register a new user
    register_payload = {
        "email": unique_email,
        "password": password
    }
    register_resp = requests.post(REGISTER_URL, json=register_payload, timeout=TIMEOUT)
    assert register_resp.status_code == 201, f"Unexpected register status: {register_resp.status_code}"
    register_data = register_resp.json()
    # Validate user payload has id and email (top-level)
    assert "id" in register_data and "email" in register_data, "Register response missing user id or email"

    # Login with the same user credentials
    login_payload = {
        "email": unique_email,
        "password": password
    }
    login_resp = requests.post(LOGIN_URL, json=login_payload, timeout=TIMEOUT)
    assert login_resp.status_code == 200, f"Unexpected login status: {login_resp.status_code}"
    login_json = login_resp.json()

    # Validate presence of access and refresh tokens in JSON body as per PRD
    assert "access" in login_json, "Login response missing access token"
    assert "refresh" in login_json, "Login response missing refresh token"

    access_token = login_json["access"]

    # Test GET /api/auth/me with valid Bearer token
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    auth_me_resp = requests.get(AUTH_ME_URL, headers=headers, timeout=TIMEOUT)
    assert auth_me_resp.status_code == 200, f"Expected 200 on /api/auth/me with auth, got {auth_me_resp.status_code}"
    auth_me_json = auth_me_resp.json()
    # Validate top-level user payload includes id and email
    assert "id" in auth_me_json and "email" in auth_me_json, "Authenticated user payload missing id or email"
    # Validate the email is the same as registered
    assert auth_me_json["email"] == unique_email, "Authenticated user email does not match registered email"

    # Test GET /api/auth/me without Authorization header, expect 401 Unauthorized
    no_auth_resp = requests.get(AUTH_ME_URL, timeout=TIMEOUT)
    assert no_auth_resp.status_code == 401, f"Expected 401 on /api/auth/me without auth, got {no_auth_resp.status_code}"


test_tc005_get_api_auth_me_authenticated_user_profile()
