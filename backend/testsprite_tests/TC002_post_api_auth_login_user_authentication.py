import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_auth_login_user_authentication():
    # Generate unique email for registration
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "TestPassword123!"

    register_url = f"{BASE_URL}/api/auth/register"
    login_url = f"{BASE_URL}/api/auth/login"

    headers = {"Content-Type": "application/json"}

    # Register user
    register_payload = {
        "email": unique_email,
        "password": password
    }
    resp = requests.post(register_url, json=register_payload, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 201, f"Expected 201 Created on register but got {resp.status_code}"
    register_json = resp.json()
    # Expect top-level user payload only (id and email), no token in response
    assert isinstance(register_json, dict), "Register response is not a JSON object"
    assert "id" in register_json, "Register response missing 'id'"
    assert register_json.get("email") == unique_email, "Register response has incorrect email"
    # No access or refresh token expected in register response, so ensure keys like 'access', 'refresh' are absent
    assert "access" not in register_json and "refresh" not in register_json

    # Test valid login
    login_payload = {
        "email": unique_email,
        "password": password
    }
    resp = requests.post(login_url, json=login_payload, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Expected 200 OK on login but got {resp.status_code}"
    login_json = resp.json()
    # Response JSON must contain access token
    assert isinstance(login_json, dict), "Login response is not a JSON object"
    assert "access" in login_json, "Login response JSON missing 'access' token"
    # Refresh token should NOT be in JSON body
    assert "refresh" not in login_json, "Login response JSON should NOT contain 'refresh' token"

    # Check cookies for refresh token (HttpOnly cookie)
    cookies = resp.cookies
    refresh_cookie = None
    for cookie in cookies:
        if cookie.name.lower() == "refresh" or cookie.name.lower() == "refresh_token":
            refresh_cookie = cookie
            break
    assert refresh_cookie is not None, "Refresh token HttpOnly cookie not set in login response"
    # Check the refresh cookie is HttpOnly by headers? The python requests cookies object doesn't expose HttpOnly flag,
    # so we check cookie presence only (HttpOnly enforced by server and browser).
    # We verify refresh does not appear in JSON as above, and presence as cookie.

    # Test invalid login credentials - expect 401
    invalid_login_payload = {
        "email": unique_email,
        "password": "WrongPassword!"
    }
    resp_invalid = requests.post(login_url, json=invalid_login_payload, headers=headers, timeout=TIMEOUT)
    assert resp_invalid.status_code == 401, f"Expected 401 Unauthorized for invalid credentials but got {resp_invalid.status_code}"


test_post_api_auth_login_user_authentication()