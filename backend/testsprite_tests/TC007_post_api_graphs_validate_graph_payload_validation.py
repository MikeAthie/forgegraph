import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_graphs_validate_graph_payload_validation():
    session = requests.Session()

    # Helper: Register a new user with unique email
    def register_user():
        email = f"testuser_{uuid.uuid4()}@example.com"
        password = "TestPass123!"
        resp = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 201, f"User registration failed: {resp.text}"
        user_data = resp.json()
        assert "id" in user_data and "email" in user_data
        return email, password

    # Helper: Login and get access token and refresh cookie
    def login_user(email, password):
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        json_body = resp.json()
        assert "access" in json_body, "No access token in login response"
        # Refresh token should be in HttpOnly cookie set by server; not in JSON
        refresh_cookie = resp.cookies.get("refresh_token")
        assert refresh_cookie is not None, "No refresh_token cookie in login response"
        return json_body["access"], refresh_cookie

    # Helpers for making authorized requests
    def auth_headers(token):
        return {"Authorization": f"Bearer {token}"}

    email, password = register_user()
    access_token, _ = login_user(email, password)

    url = f"{BASE_URL}/api/graphs/validate"
    headers = auth_headers(access_token)
    headers["Content-Type"] = "application/json"

    valid_graph_json = {
        "nodes": [
            {"id": "output-1", "type": "output", "name": "Output", "config": {}}
        ],
        "edges": [
            {"id": "edge-1", "from": "START", "to": "output-1"}
        ],
    }

    # 1. Positive case: valid graph_json, expect 200 with data.valid true
    payload_valid = {"graph_json": valid_graph_json}
    resp = session.post(url, json=payload_valid, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Valid graph: Expected 200 got {resp.status_code}"
    data = resp.json().get("data")
    assert data is not None, "Response missing data key for valid graph"
    assert isinstance(data.get("valid"), bool), "data.valid must be boolean"
    assert data.get("valid") is True, "Valid graph should return data.valid = true"

    # 2. Semantic invalid but structurally well-formed graph:
    # Use a graph_json that is structurally valid but semantically invalid.
    # For example, change "to" edge to a non-existent node id "nonexistent"
    invalid_semantic_graph = {
        "nodes": [
            {"id": "output-1", "type": "output", "name": "Output", "config": {}}
        ],
        "edges": [
            {"id": "edge-1", "from": "START", "to": "nonexistent"}
        ],
    }
    payload_invalid_semantic = {"graph_json": invalid_semantic_graph}
    resp = session.post(url, json=payload_invalid_semantic, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Semantic invalid graph: Expected 200 got {resp.status_code}"
    data = resp.json().get("data")
    assert data is not None, "Response missing data key for semantic invalid graph"
    assert isinstance(data.get("valid"), bool), "data.valid must be boolean"
    # valid must be false for semantically invalid graph
    assert data.get("valid") is False, "Semantic invalid graph should return data.valid = false"
    # Expect errors field exists for invalid graph
    assert "errors" in data and isinstance(data["errors"], (list, dict)), "Invalid graph should include errors"

    # 3. Missing graph_json returns 400 Bad Request
    payload_missing = {}
    resp = session.post(url, json=payload_missing, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 400, f"Missing graph_json: Expected 400 got {resp.status_code}"

    # Cleanup: logout user
    logout_url = f"{BASE_URL}/api/auth/logout"
    resp = session.post(logout_url, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 204, f"Logout failed: {resp.status_code}"


test_post_api_graphs_validate_graph_payload_validation()