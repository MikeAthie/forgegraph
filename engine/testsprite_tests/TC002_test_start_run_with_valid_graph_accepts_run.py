import requests
import uuid
import time

BASE_URL = "http://localhost:50051"
START_RUN_PATH = "/grpc/EngineService/StartRun"
METRICS_PATH = "/metrics"
TIMEOUT = 30
AUTH_TOKEN = "Bearer test-auth-token"  # Replace with actual token if needed


def test_start_run_with_valid_graph_accepts_run():
    run_id = str(uuid.uuid4())
    graph_json = """
    {
      "nodes": [
        {
          "id": "node1",
          "type": "prompt",
          "properties": {
            "text": "Hello World"
          }
        }
      ],
      "edges": []
    }
    """
    input_json = "{}"
    callback_url = "http://localhost:6000/callback"

    headers = {
        "Authorization": AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "run_id": run_id,
        "graph_json": graph_json,
        "input_json": input_json,
        "callback_url": callback_url
    }

    try:
        # Start Run
        response = requests.post(
            f"{BASE_URL}{START_RUN_PATH}",
            json=payload,
            headers=headers,
            timeout=TIMEOUT,
        )
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
        resp_json = response.json()

        # Validate accepted == true
        assert "accepted" in resp_json, "Response missing 'accepted' field"
        assert resp_json["accepted"] is True, f"Run was not accepted: {resp_json}"

        # Wait briefly for execution to initiate and metrics to update
        time.sleep(2)

        # Check metrics endpoint for runtime telemetry (HTTP metrics check as per instructions)
        metrics_response = requests.get(
            f"{BASE_URL}{METRICS_PATH}",
            timeout=TIMEOUT,
        )
        assert metrics_response.status_code == 200, f"Expected 200 from metrics endpoint, got {metrics_response.status_code}"
        metrics_text = metrics_response.text
        # Assert there is some metrics text output (non-empty)
        assert metrics_text and len(metrics_text) > 0, "Metrics response is empty"

        # Optionally check that metrics output contains some indication of run execution 
        # (e.g. 'forgegraph_run' or similar metric names, adapting to common prometheus naming)
        assert "forgegraph" in metrics_text.lower() or "run" in metrics_text.lower(), "Metrics output does not contain expected telemetry data"

    finally:
        # Clean-up if needed could be done here (like cancelling the run), but not specified.
        pass


test_start_run_with_valid_graph_accepts_run()
