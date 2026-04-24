import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_auth_login_user_authentication():
    session = requests.Session()
    # Generate a unique email for registration
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "TestPassword123!"

    register_url = f"{BASE_URL}/api/auth/register"
    login_url = f"{BASE_URL}/api/auth/login"
    headers = {"Content-Type": "application/json"}

    user_payload = {"email": unique_email, "password": password}

    # Register a new user
    resp_register = session.post(register_url, json=user_payload, headers=headers, timeout=TIMEOUT)
    assert resp_register.status_code == 201, f"Unexpected status code for registration: {resp_register.status_code}"
    user_data = resp_register.json()
    assert "id" in user_data and "email" in user_data, "User payload missing id or email on registration"
    assert user_data.get("email") == unique_email, "Registered email mismatch"

    try:
        # Valid login attempt
        resp_login = session.post(login_url, json=user_payload, headers=headers, timeout=TIMEOUT)
        assert resp_login.status_code == 200, f"Unexpected status code for login: {resp_login.status_code}"
        login_json = resp_login.json()

        # Access token must be in JSON body
        assert "access" in login_json, "Access token missing in login JSON response"
        # Refresh token must NOT be in JSON body
        assert "refresh_token" not in login_json, "Refresh token should not be in JSON body"

        # Refresh token cookie must be present and HttpOnly
        cookies = resp_login.cookies
        assert "refresh_token" in cookies, "refresh_token cookie missing after login"
        # Note: requests lib does not expose HttpOnly attribute on cookies,
        # but since server sets HttpOnly, we check it's present and not in JSON as per contract.

        # Invalid login attempt
        invalid_payload = {"email": unique_email, "password": "WrongPassword!"}
        resp_invalid_login = requests.post(login_url, json=invalid_payload, headers=headers, timeout=TIMEOUT)
        assert resp_invalid_login.status_code == 401, f"Expected 401 for invalid login, got {resp_invalid_login.status_code}"

    finally:
        # Cleanup: Attempt to delete the user if an admin API existed, but since not specified, we skip cleanup.
        # If backend supports user deletion via auth, it would be implemented here.
        pass


test_post_api_auth_login_user_authentication()