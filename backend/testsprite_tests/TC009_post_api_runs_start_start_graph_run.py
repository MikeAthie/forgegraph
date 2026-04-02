import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_runs_start_start_graph_run():
    session = requests.Session()
    unique_suffix = str(uuid.uuid4())
    test_email = f"testuser_{unique_suffix}@example.com"
    password = "testPassword123!"

    try:
        # Register user
        register_resp = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": password},
            timeout=TIMEOUT,
        )
        assert register_resp.status_code == 200, f"Register failed: {register_resp.text}"
        register_json = register_resp.json()
        # The register endpoint returns user object directly, not wrapped in 'user'
        assert isinstance(register_json, dict)
        assert register_json.get("email") == test_email

        # Login user
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": test_email, "password": password},
            timeout=TIMEOUT,
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        login_json = login_resp.json()
        access_token = login_json.get("access")
        refresh_token = login_json.get("refresh")
        assert access_token and isinstance(access_token, str)
        assert refresh_token and isinstance(refresh_token, str)

        # Setup auth header for further requests
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Create a graph with required fields (name, nodes, edges)
        graph_name = f"test-graph-{unique_suffix}"
        graph_payload = {
            "name": graph_name,
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "end"}
            ],
            "edges": [
                {"from": "n1", "to": "n2"}
            ]
        }
        create_graph_resp = session.post(
            f"{BASE_URL}/api/graphs",
            json=graph_payload,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert create_graph_resp.status_code == 200, f"Create graph failed: {create_graph_resp.text}"
        graph_data = create_graph_resp.json()
        assert graph_data and isinstance(graph_data, dict)
        graph_id = graph_data.get("id")
        assert graph_id and isinstance(graph_id, str)
        assert graph_data.get("name") == graph_name

        # Start a run with input
        input_json = {"input_key": "input_value"}
        run_start_payload = {"graph_id": graph_id, "input": input_json}
        start_run_resp = session.post(
            f"{BASE_URL}/api/runs/start",
            json=run_start_payload,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert start_run_resp.status_code == 200, f"Start run failed: {start_run_resp.text}"
        run_data = start_run_resp.json()
        assert run_data and isinstance(run_data, dict)
        run_id = run_data.get("run_id")
        assert run_id and isinstance(run_id, str)
        assert run_data.get("graph_id") == graph_id
        assert run_data.get("status") and isinstance(run_data.get("status"), str)
        # input returned might match or be None - no strict assertion since PRD doesn't specify

        # Attempt to start a run with a nonexistent graph_id -> expect 400 Validation error
        fake_graph_id = str(uuid.uuid4())
        bad_payload = {"graph_id": fake_graph_id, "input": {}}
        bad_run_resp = session.post(
            f"{BASE_URL}/api/runs/start",
            json=bad_payload,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert bad_run_resp.status_code == 400, f"Expected 400 for invalid graph_id, got {bad_run_resp.status_code}"

    finally:
        # Cleanup: delete graph if possible to avoid clutter
        try:
            if 'graph_id' in locals():
                session.delete(
                    f"{BASE_URL}/api/graphs/{graph_id}",
                    headers=headers,
                    timeout=TIMEOUT,
                )
        except Exception:
            pass


test_post_api_runs_start_start_graph_run()
