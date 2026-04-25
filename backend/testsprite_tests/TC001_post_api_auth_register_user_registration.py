import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
REGISTER_ENDPOINT = "/api/auth/register"
TIMEOUT = 30

def test_post_api_auth_register_user_registration():
    # Generate a unique email for registration using UUID
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "ValidPass123!"

    url = BASE_URL + REGISTER_ENDPOINT
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "email": unique_email,
        "password": password
    }

    # 1. First registration attempt with unique email, expect 201 and user payload containing id and email only
    response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    assert response.status_code == 201, f"Expected 201 Created but got {response.status_code}"
    json_data = response.json()
    # Expect top-level user payload with id and email only, no token payload
    assert "id" in json_data, "Response JSON missing 'id'"
    assert "email" in json_data, "Response JSON missing 'email'"
    assert json_data["email"] == unique_email, "Response email does not match registered email"
    # Confirm no token keys in the response
    disallowed_token_keys = ["access", "refresh", "token", "access_token", "refresh_token"]
    for key in disallowed_token_keys:
        assert key not in json_data, f"Token key '{key}' should not be in registration response"

    # 2. Duplicate registration attempt with the same email, expect 400 with some form of error keys (field-level or error wrapper)
    dup_response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    assert dup_response.status_code == 400, f"Expected 400 Bad Request on duplicate but got {dup_response.status_code}"
    dup_json = dup_response.json()
    # The error response may contain field-level validation keys like "email" or an error envelope, so check for presence of error keys
    # Accept if any known validation key or a generic error key is present
    error_keys = {"email", "detail", "errors", "non_field_errors"}
    if not any(key in dup_json for key in error_keys):
        # Also allow if any keys exist and are not id/email
        assert len(dup_json) > 0, "Expected error details in duplicate registration response"

test_post_api_auth_register_user_registration()