import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_graphs_create_new_workflow_graph():
    session = requests.Session()
    unique_email = f"testuser_{int(time.time() * 1000)}@example.com"
    password = "StrongPass!234"

    # Register user
    register_resp = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": unique_email, "password": password},
        timeout=TIMEOUT
    )
    assert register_resp.status_code == 201, f"Register failed: {register_resp.text}"
    user_payload = register_resp.json()
    assert "id" in user_payload and "email" in user_payload
    assert user_payload["email"] == unique_email

    # Login user
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": unique_email, "password": password},
        timeout=TIMEOUT
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    login_json = login_resp.json()
    access_token = login_json.get("access")
    assert access_token is not None, "Access token missing in login response JSON"
    # refresh token only in HttpOnly cookie, so no 'refresh' key expected in JSON
    assert "refresh" not in login_json

    # Prepare auth headers
    headers = {"Authorization": f"Bearer {access_token}"}

    created_graph_id = None

    try:
        # Positive case: create a new graph with name and optional description
        graph_payload = {
            "name": "Test Graph " + str(uuid.uuid4()),
            "description": "Created by test case TC008"
        }
        create_resp = session.post(
            f"{BASE_URL}/api/graphs/",
            json=graph_payload,
            headers=headers,
            timeout=TIMEOUT
        )
        assert create_resp.status_code == 201, f"Graph creation failed: {create_resp.text}"
        create_data = create_resp.json()
        assert "data" in create_data, "Response missing data wrapper"
        graph_data = create_data["data"]
        assert "id" in graph_data and isinstance(graph_data["id"], str)
        assert graph_data["name"] == graph_payload["name"]
        assert graph_data.get("version_count") == 0
        assert graph_data.get("latest_version") is None
        created_graph_id = graph_data["id"]

        # Negative case: missing name field should return 400
        invalid_payload = {
            "description": "No name field"
        }
        invalid_resp = session.post(
            f"{BASE_URL}/api/graphs/",
            json=invalid_payload,
            headers=headers,
            timeout=TIMEOUT
        )
        assert invalid_resp.status_code == 400, f"Expected 400 for missing name, got {invalid_resp.status_code}"
    finally:
        # Cleanup: delete created graph if any
        if created_graph_id:
            del_resp = session.delete(
                f"{BASE_URL}/api/graphs/{created_graph_id}",
                headers=headers,
                timeout=TIMEOUT
            )
            # Accept 204 No Content or 404 Not Found (if already deleted)
            assert del_resp.status_code in (204, 404), f"Graph deletion failed: {del_resp.status_code} {del_resp.text}"


test_post_api_graphs_create_new_workflow_graph()