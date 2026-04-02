import requests
import uuid

BASE_URL = "http://localhost:8000"
REGISTER_URL = f"{BASE_URL}/api/auth/register"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
REFRESH_URL = f"{BASE_URL}/api/auth/refresh"

def test_post_api_auth_refresh_token_refresh():
    # Create unique email for registration
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "TestPassword123!"

    # Register user
    register_payload = {
        "email": unique_email,
        "password": password
    }
    register_resp = requests.post(REGISTER_URL, json=register_payload, timeout=30)
    assert register_resp.status_code == 200, f"Registration failed: {register_resp.text}"
    register_json = register_resp.json()
    assert "id" in register_json, f"ID missing in registration response: {register_resp.text}"
    assert "email" in register_json, f"Email missing in registration response: {register_resp.text}"
    assert register_json["email"] == unique_email

    # Login user
    login_payload = {
        "email": unique_email,
        "password": password
    }
    login_resp = requests.post(LOGIN_URL, json=login_payload, timeout=30)
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    login_json = login_resp.json()
    assert "access" in login_json, f"Access token missing in login response: {login_resp.text}"
    assert "refresh" in login_json, f"Refresh token missing in login response: {login_resp.text}"

    refresh_token = login_json["refresh"]

    # --- Step 1: Refresh using the refresh token in JSON payload ---
    refresh_payload = {"refresh": refresh_token}
    refresh_resp1 = requests.post(REFRESH_URL, json=refresh_payload, timeout=30)
    assert refresh_resp1.status_code == 200, f"Refresh with JSON field failed: {refresh_resp1.text}"
    refresh_json1 = refresh_resp1.json()
    assert "access" in refresh_json1, f"New access token missing on refresh: {refresh_resp1.text}"

    # --- Step 2: Refresh using new access token does not return new refresh token as per PRD ---
    # Use the same refresh token again (simulate)
    refresh_payload2 = {"refresh": refresh_token}
    refresh_resp2 = requests.post(REFRESH_URL, json=refresh_payload2, timeout=30)
    assert refresh_resp2.status_code == 200, f"Second refresh failed: {refresh_resp2.text}"
    refresh_json2 = refresh_resp2.json()
    assert "access" in refresh_json2, f"New access token missing on second refresh: {refresh_resp2.text}"

    # --- Step 3: Attempt reuse of invalid refresh token (simulate by altering token) - expect 401 ---
    reuse_payload = {"refresh": "invalid_refresh_token_for_reuse_test"}
    reuse_resp = requests.post(REFRESH_URL, json=reuse_payload, timeout=30)
    assert reuse_resp.status_code == 401, f"Invalid refresh token should fail with 401 but got {reuse_resp.status_code}"

    # --- Step 4: Attempt refresh with invalid refresh token - expect 401 ---
    invalid_payload = {"refresh": "invalid_refresh_token_value"}
    invalid_resp = requests.post(REFRESH_URL, json=invalid_payload, timeout=30)
    assert invalid_resp.status_code == 401, f"Invalid refresh token should fail with 401 but got {invalid_resp.status_code}"


test_post_api_auth_refresh_token_refresh()
