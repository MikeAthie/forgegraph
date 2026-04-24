import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_runs_start_start_graph_run():
    session = requests.Session()
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "StrongPass!234"

    # Register user
    register_resp = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": unique_email, "password": password},
        timeout=TIMEOUT,
    )
    assert register_resp.status_code == 201, f"Unexpected status {register_resp.status_code} on register"
    user_data = register_resp.json()
    assert isinstance(user_data, dict)
    assert "id" in user_data and "email" in user_data
    assert user_data["email"] == unique_email

    # Login user
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": unique_email, "password": password},
        timeout=TIMEOUT,
    )
    assert login_resp.status_code == 200, f"Unexpected status {login_resp.status_code} on login"
    login_json = login_resp.json()
    assert "access" in login_json
    assert "refresh_token" not in login_json
    access_token = login_json["access"]
    assert "refresh_token" in login_resp.cookies
    refresh_cookie = login_resp.cookies["refresh_token"]

    headers_auth = {"Authorization": f"Bearer {access_token}"}

    graph_metadata = None
    graph_version = None
    run_started = None

    try:
        # Create graph metadata
        graph_payload = {
            "name": "Test Graph for Run Start",
            "description": "Created during test_post_api_runs_start_start_graph_run",
        }
        graph_resp = session.post(
            f"{BASE_URL}/api/graphs/",
            json=graph_payload,
            headers=headers_auth,
            timeout=TIMEOUT,
        )
        assert graph_resp.status_code == 201, f"Unexpected status {graph_resp.status_code} creating graph"
        graph_data = graph_resp.json()
        assert "data" in graph_data
        graph_metadata = graph_data["data"]
        assert "id" in graph_metadata
        assert graph_metadata.get("version_count", 0) == 0
        assert graph_metadata.get("latest_version") is None
        graph_id = graph_metadata["id"]

        # Create graph version
        valid_graph_json = {
            "nodes": [
                {"id": "output-1", "type": "output", "name": "Output", "config": {}}
            ],
            "edges": [{"id": "edge-1", "from": "START", "to": "output-1"}],
        }
        version_resp = session.post(
            f"{BASE_URL}/api/graphs/{graph_id}/versions",
            json={"graph_json": valid_graph_json},
            headers=headers_auth,
            timeout=TIMEOUT,
        )
        assert version_resp.status_code == 201, f"Unexpected status {version_resp.status_code} creating graph version"
        version_data = version_resp.json()
        assert "data" in version_data
        graph_version = version_data["data"]
        assert "id" in graph_version
        graph_version_id = graph_version["id"]

        # Start run with valid graph_version_id and input_json
        input_json = {"input_key": "input_value"}
        run_start_resp = session.post(
            f"{BASE_URL}/api/runs/start",
            json={"graph_version_id": graph_version_id, "input_json": input_json},
            headers=headers_auth,
            timeout=TIMEOUT,
        )
        assert run_start_resp.status_code == 201, f"Unexpected status {run_start_resp.status_code} starting run"
        run_data = run_start_resp.json()
        assert "data" in run_data
        run_started = run_data["data"]
        assert "id" in run_started
        assert run_started["graph_version_id"] == graph_version_id
        assert "status" in run_started
        assert "input_json" in run_started
        assert run_started["input_json"] == input_json

        # Test with nonexistent graph_version_id returns 404
        fake_version_id = str(uuid.uuid4())
        nonexistent_resp = session.post(
            f"{BASE_URL}/api/runs/start",
            json={"graph_version_id": fake_version_id},
            headers=headers_auth,
            timeout=TIMEOUT,
        )
        assert nonexistent_resp.status_code == 404

    finally:
        # Cleanup: attempt to delete graph if created, deleting graph versions is not specified, so deleting graph only
        if graph_metadata and "id" in graph_metadata:
            try:
                del_resp = session.delete(
                    f"{BASE_URL}/api/graphs/{graph_metadata['id']}",
                    headers=headers_auth,
                    timeout=TIMEOUT,
                )
                # Accept 204 or 404 (already deleted)
                assert del_resp.status_code in (204, 404)
            except Exception:
                pass


test_post_api_runs_start_start_graph_run()