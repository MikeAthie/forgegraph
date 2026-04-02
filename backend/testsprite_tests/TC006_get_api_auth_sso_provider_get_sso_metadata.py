import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30

def test_get_api_auth_sso_provider_with_auth_and_without():
    session = requests.Session()

    # Generate unique email for registration
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "StrongPass!123"

    try:
        # Register user
        register_resp = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": unique_email, "password": password},
            timeout=TIMEOUT,
        )
        assert register_resp.status_code == 200, f"Registration failed: {register_resp.text}"
        register_json = register_resp.json()
        # Check required fields in registration response (user and token payload expected, but no 'user' key)
        assert isinstance(register_json, dict), "Registration response is not a JSON object"
        assert "email" in register_json, "Email missing in registration response"
        assert register_json["email"] == unique_email, "Registered email mismatch"

        # Login user
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": password},
            timeout=TIMEOUT,
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        login_json = login_resp.json()
        assert "access" in login_json, "Access token missing in login response JSON"
        assert "refresh" in login_json, "Refresh token missing in login response JSON"

        access_token = login_json["access"]

        # Use Bearer Authorization header for auth-required endpoints
        headers = {"Authorization": f"Bearer {access_token}"}

        # Authenticated GET /api/auth/sso/provider
        sso_resp = session.get(
            f"{BASE_URL}/api/auth/sso/provider",
            headers=headers,
            timeout=TIMEOUT,
        )
        assert sso_resp.status_code == 200, f"Authenticated SSO provider request failed: {sso_resp.text}"
        sso_json = sso_resp.json()
        # The PRD states SSO provider metadata is returned, no specific 'status' or 'state' fields guaranteed
        assert isinstance(sso_json, dict), "SSO provider response is not a JSON object"
        assert len(sso_json) > 0, "SSO provider response is empty"

        # Unauthenticated GET /api/auth/sso/provider should return 200
        unauth_resp = session.get(f"{BASE_URL}/api/auth/sso/provider", timeout=TIMEOUT)
        assert unauth_resp.status_code == 200, f"Unauthenticated SSO request did not return 200: {unauth_resp.status_code}"

    finally:
        # Logout the user if possible
        if 'access_token' in locals():
            try:
                logout_headers = {"Authorization": f"Bearer {access_token}"}
                logout_resp = session.post(f"{BASE_URL}/api/auth/logout", headers=logout_headers, timeout=TIMEOUT)
                assert logout_resp.status_code == 200, f"Logout failed: {logout_resp.status_code} {logout_resp.text}"
            except Exception:
                pass


test_get_api_auth_sso_provider_with_auth_and_without()
