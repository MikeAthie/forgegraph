import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_get_api_auth_me_authenticated_user_profile():
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "TestPassword123!"
    headers = {"Content-Type": "application/json"}

    access_token = None
    session = requests.Session()

    try:
        # Register the user
        register_payload = {"email": unique_email, "password": password}
        register_resp = session.post(
            f"{BASE_URL}/api/auth/register",
            json=register_payload,
            headers=headers,
            timeout=TIMEOUT
        )
        assert register_resp.status_code == 201
        user_data = register_resp.json()
        assert "id" in user_data
        assert user_data.get("email") == unique_email

        # Login the user
        login_payload = {"email": unique_email, "password": password}
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json=login_payload,
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        assert login_resp.status_code == 200
        login_json = login_resp.json()

        # access token must be present in JSON body
        assert "access" in login_json
        access_token = login_json["access"]
        # refresh_token should be set only in the HttpOnly cookie, not in JSON body
        assert "refresh_token" not in login_json

        # Check that refresh token cookie is set and HttpOnly (as best as possible)
        refresh_cookie = None
        for cookie in session.cookies:
            if cookie.name == "refresh_token":
                refresh_cookie = cookie
                break
        assert refresh_cookie is not None
        # HttpOnly can't be asserted from client side, but just ensure cookie is present

        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Request /api/auth/me with valid Bearer token
        profile_resp = session.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers,
            timeout=TIMEOUT
        )
        assert profile_resp.status_code == 200
        profile_json = profile_resp.json()
        assert isinstance(profile_json, dict)
        assert "email" in profile_json
        assert profile_json["email"] == unique_email
        assert "id" in profile_json
        assert profile_json["id"] == user_data["id"]

        # Request /api/auth/me without Authorization header should return 401
        noauth_resp = requests.get(f"{BASE_URL}/api/auth/me", timeout=TIMEOUT)
        assert noauth_resp.status_code == 401

    finally:
        # Cleanup: logout the user if access_token available to clear refresh cookies
        if access_token:
            try:
                logout_headers = {"Authorization": f"Bearer {access_token}"}
                logout_resp = session.post(
                    f"{BASE_URL}/api/auth/logout",
                    headers=logout_headers,
                    timeout=TIMEOUT
                )
                assert logout_resp.status_code == 204
            except Exception:
                # ignore logout errors to avoid masking test failures
                pass


test_get_api_auth_me_authenticated_user_profile()