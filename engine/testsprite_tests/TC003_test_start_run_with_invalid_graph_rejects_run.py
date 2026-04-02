import requests
import uuid

BASE_URL = "http://localhost:50051"
START_RUN_PATH = "/grpc/EngineService/StartRun"
AUTH_TOKEN = "Bearer YOUR_AUTH_TOKEN_HERE"  # Replace with valid token if needed

def test_start_run_with_invalid_graph_rejects_run():
    run_id = str(uuid.uuid4())
    invalid_graph_json = '{"invalid": "this is not a valid graph"}'  # Intentionally malformed/invalid graph JSON
    input_json = "{}"
    callback_url = "http://callback.url/endpoint"
    headers = {
        "Authorization": AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "run_id": run_id,
        "graph_json": invalid_graph_json,
        "input_json": input_json,
        "callback_url": callback_url
    }
    url = f"{BASE_URL}{START_RUN_PATH}"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Validate HTTP status code
        assert response.status_code == 200

        # Validate accepted=false and presence of error message indicating validation failure
        assert "accepted" in data, "Response missing 'accepted' field"
        assert data["accepted"] is False, "Run was incorrectly accepted with invalid graph"
        assert "error" in data or "message" in data, "No validation error message in response"
        error_msg = data.get("error") or data.get("message") or ""
        assert isinstance(error_msg, str) and len(error_msg) > 0, "Validation error message empty"

    except requests.RequestException as e:
        assert False, f"Request failed: {e}"

test_start_run_with_invalid_graph_rejects_run()