import requests

def test_get_run_status_for_nonexistent_run_returns_404():
    base_url = "http://localhost:50051"
    path = "/grpc/EngineService/GetRunStatus"
    url = base_url + path
    headers = {
        "Content-Type": "application/json"
    }

    # Use a run_id we assume does not exist
    payload = {
        "run_id": "nonexistent-run-id-12345"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        assert False, f"Request failed with exception: {e}"

    # According to PRD, 404 should be returned if run is not found
    assert response.status_code == 404, f"Expected 404 status for nonexistent run_id, got {response.status_code}"
    # The response body is expected to indicate run not found; it's minimal per PRD.
    # Could check text or json if available
    # Since no exact schema, just validate presence of "not found" text (case insensitive)
    content = response.text.lower()
    assert "not found" in content or "404" in content, "Response does not indicate run not found"

test_get_run_status_for_nonexistent_run_returns_404()