import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_graphs_create_new_workflow_graph():
    session = requests.Session()

    # Generate unique email for registration
    unique_email = f"testuser_{uuid.uuid4()}@example.com"
    password = "StrongPassw0rd!"

    try:
        # Register User
        register_resp = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": unique_email, "password": password},
            timeout=TIMEOUT,
        )
        assert register_resp.status_code == 200, f"Register failed: {register_resp.text}"
        register_json = register_resp.json()

        # Adjusted: registration response contains user fields at root level (not nested under 'user')
        assert "id" in register_json, "User id missing in register response"
        assert register_json["email"] == unique_email

        # Login User
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": password},
            timeout=TIMEOUT,
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        login_json = login_resp.json()
        assert "access" in login_json, "Login response missing access token"
        assert "refresh" in login_json, "Login response missing refresh token"

        # Extract access token
        access_token = login_json["access"]

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Successful graph creation with required fields (name, nodes, edges)
        graph_payload = {"name": "Test Workflow Graph", "nodes": [], "edges": []}
        create_resp = session.post(
            f"{BASE_URL}/api/graphs",
            json=graph_payload,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert create_resp.status_code == 200, f"Graph creation failed: {create_resp.text}"
        create_json = create_resp.json()
        assert "id" in create_json, "Graph response missing id"
        assert create_json["name"] == graph_payload["name"], "Graph name mismatch"
        assert "version_count" in create_json and create_json["version_count"] == 0, (
            "version_count should be 0"
        )
        assert "latest_version" in create_json and create_json["latest_version"] is None, (
            "latest_version should be null"
        )

        created_graph_id = create_json["id"]

        # Graph creation with optional description
        graph_payload_desc = {
            "name": "Test Workflow Graph with Desc",
            "description": "A description",
            "nodes": [],
            "edges": [],
        }
        create_desc_resp = session.post(
            f"{BASE_URL}/api/graphs",
            json=graph_payload_desc,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert create_desc_resp.status_code == 200, (
            f"Graph creation with desc failed: {create_desc_resp.text}"
        )
        create_desc_json = create_desc_resp.json()
        assert create_desc_json and create_desc_json.get("name") == graph_payload_desc["name"]
        assert "version_count" in create_desc_json and create_desc_json["version_count"] == 0
        assert "latest_version" in create_desc_json and create_desc_json["latest_version"] is None

        # Attempt graph creation missing required 'name' or missing required fields 'nodes' and 'edges'
        invalid_payloads = [
            {},
            {"description": "No name provided", "nodes": [], "edges": []},
            {"name": "Missing nodes and edges"},
            {"name": "Missing edges", "nodes": []},
        ]
        for payload in invalid_payloads:
            resp = session.post(
                f"{BASE_URL}/api/graphs",
                json=payload,
                headers=headers,
                timeout=TIMEOUT,
            )
            assert resp.status_code == 400, (
                f"Expected 400 for invalid payload, got {resp.status_code} for payload {payload}"
            )

    finally:
        # Logout user to invalidate session
        try:
            logout_resp = session.post(
                f"{BASE_URL}/api/auth/logout",
                headers=headers,
                timeout=TIMEOUT,
            )
            assert logout_resp.status_code == 200, f"Logout failed: {logout_resp.status_code}"
        except Exception:
            pass


test_post_api_graphs_create_new_workflow_graph()
