import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_auth_logout_invalidate_session():
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "StrongPass!234"
    register_url = f"{BASE_URL}/api/auth/register"
    login_url = f"{BASE_URL}/api/auth/login"
    logout_url = f"{BASE_URL}/api/auth/logout"

    # Register user
    register_data = {"email": unique_email, "password": password}
    register_resp = requests.post(register_url, json=register_data, timeout=TIMEOUT)
    assert register_resp.status_code == 201, f"Register failed: {register_resp.text}"
    user_payload = register_resp.json()
    assert "id" in user_payload and "email" in user_payload, (
        "Register response missing user id or email"
    )
    assert user_payload["email"] == unique_email

    # Login user
    login_data = {"email": unique_email, "password": password}
    login_resp = requests.post(login_url, json=login_data, timeout=TIMEOUT)
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    login_json = login_resp.json()
    assert "access" in login_json, "Login response missing access token"
    assert "refresh" not in login_json, "Refresh token should not be in JSON body"

    access_token = login_json["access"]

    # Extract refresh token cookie
    refresh_cookie = None
    for cookie in login_resp.cookies:
        if cookie.name == "refresh":
            refresh_cookie = cookie
            break
    # refresh token cookie may be HttpOnly, session cookie; its absence test later

    headers = {"Authorization": f"Bearer {access_token}"}
    cookies = {}
    if refresh_cookie is not None:
        cookies[refresh_cookie.name] = refresh_cookie.value

    # POST /api/auth/logout with valid Bearer token and refresh cookie
    logout_resp = requests.post(logout_url, headers=headers, cookies=cookies, timeout=TIMEOUT)
    # Per PRD and instructions, expect 204 No Content (per test case expects 204)
    # The PRD states "returns 204" for logout.
    assert logout_resp.status_code == 204, (
        f"Logout failed with status {logout_resp.status_code} body: {logout_resp.text}"
    )

    # Repeat logout to confirm idempotency when no refresh cookie (i.e., logged out already)
    logout_resp2 = requests.post(logout_url, headers=headers, timeout=TIMEOUT)
    assert logout_resp2.status_code == 204, (
        "Logout should be idempotent and return 204 even if refresh cookie absent"
    )

    # Also test logout with missing or invalid Authorization header to confirm it fails (not explicitly requested but good sanity)
    logout_resp_invalid = requests.post(logout_url, timeout=TIMEOUT)
    assert logout_resp_invalid.status_code in (401, 403), (
        "Logout without auth should fail with 401 or 403"
    )


test_post_api_auth_logout_invalidate_session()
