import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
REGISTER_ENDPOINT = "/api/auth/register"
TIMEOUT = 30


def test_post_api_auth_register_user_registration():
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "ValidPass123!"
    url = BASE_URL + REGISTER_ENDPOINT
    payload = {
        "email": unique_email,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    # Attempt to register with a unique email and valid password
    response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    assert response.status_code == 201, f"Expected 201 but got {response.status_code}"
    json_resp = response.json()
    # Expect top-level user payload containing id and email only, no token payload
    assert isinstance(json_resp, dict), "Response JSON is not a dictionary"
    assert "id" in json_resp, "User id missing in response"
    assert "email" in json_resp, "User email missing in response"
    assert json_resp["email"] == unique_email, "User email in response does not match"
    # Ensure no token keys present
    forbidden_token_keys = {"token", "tokens", "access", "refresh"}
    assert not any(k in json_resp for k in forbidden_token_keys), "Response should not contain tokens"

    # Attempt same registration again - expect 400 with validation error due to duplicate
    duplicate_response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    assert duplicate_response.status_code == 400, f"Expected 400 on duplicate but got {duplicate_response.status_code}"

    # Try invalid payloads for validation error (e.g., bad email and short password)
    invalid_payloads = [
        {"email": "notanemail", "password": password},
        {"email": unique_email.replace("@", ""), "password": password},  # malformed email
        {"email": f"another_{uuid.uuid4().hex}@example.com", "password": "short"},
        {"email": "", "password": password},
        {"email": "invalid@example.com", "password": ""}
    ]
    for invalid_data in invalid_payloads:
        resp = requests.post(url, json=invalid_data, headers=headers, timeout=TIMEOUT)
        assert resp.status_code == 400, f"Expected 400 for invalid data {invalid_data}, got {resp.status_code}"


test_post_api_auth_register_user_registration()