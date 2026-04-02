import requests
import uuid

BASE_URL = "http://localhost:50051"
START_RUN_PATH = "/grpc/EngineService/StartRun"
TIMEOUT = 30
AUTH_TOKEN = "Bearer dummy_token_for_auth"  # Replace with valid token if needed


def test_start_run_with_missing_required_fields_rejects_run():
    headers = {
        "Content-Type": "application/json",
        "Authorization": AUTH_TOKEN,
    }

    # Test cases with missing run_id or graph_json
    test_payloads = [
        # Missing run_id
        {
            "graph_json": "{\"nodes\": [], \"edges\": []}",
            "input_json": "{}",
            "callback_url": "http://callback.url"
        },
        # Missing graph_json
        {
            "run_id": str(uuid.uuid4()),
            "input_json": "{}",
            "callback_url": "http://callback.url"
        },
        # Missing both run_id and graph_json
        {
            "input_json": "{}",
            "callback_url": "http://callback.url"
        }
    ]

    for payload in test_payloads:
        try:
            response = requests.post(
                BASE_URL + START_RUN_PATH,
                json=payload,
                headers=headers,
                timeout=TIMEOUT
            )
        except requests.RequestException as e:
            assert False, f"Request failed: {e}"

        # According to PRD the response code is 200 even on missing required fields
        assert response.status_code == 200, f"Expected status 200 but got {response.status_code}"

        try:
            resp_json = response.json()
        except ValueError:
            assert False, "Response is not valid JSON"

        # accepted should be false
        accepted = resp_json.get("accepted")
        assert accepted is False, f"Expected accepted=false but got {accepted}"

        # error message indicating missing required fields should be present and be a non-empty string
        error_msg = resp_json.get("error")
        assert error_msg and isinstance(error_msg, str), "Expected error message indicating missing required fields"


test_start_run_with_missing_required_fields_rejects_run()