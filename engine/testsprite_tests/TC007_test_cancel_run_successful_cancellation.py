import requests
import uuid
import time

BASE_URL = "http://localhost:50051"
TIMEOUT = 30
HEADERS = {
    "Content-Type": "application/json"
}
# Placeholder auth header if needed; assume no auth per PRD on CancelRun, but StartRun requires auth.
# We'll include a simple bearer token header for StartRun and CancelRun assuming auth required.
AUTH_TOKEN = "test-auth-token"
HEADERS_AUTH = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AUTH_TOKEN}"
}

def test_cancel_run_successful_cancellation():
    run_id = str(uuid.uuid4())

    # A minimal valid graph_json (empty graph or a simple structure) and input_json for StartRun
    graph_json = '{"nodes":[], "edges":[]}'
    input_json = '{}'

    start_run_payload = {
        "run_id": run_id,
        "graph_json": graph_json,
        "input_json": input_json,
        "callback_url": "http://localhost/callback"
    }

    try:
        # Start the run first so we can cancel it
        start_run_resp = requests.post(
            f"{BASE_URL}/grpc/EngineService/StartRun",
            headers=HEADERS_AUTH,
            json=start_run_payload,
            timeout=TIMEOUT
        )
        assert start_run_resp.status_code == 200, f"StartRun unexpected status: {start_run_resp.status_code}"
        start_run_data = start_run_resp.json()
        assert "accepted" in start_run_data and start_run_data["accepted"], f"StartRun not accepted: {start_run_data}"

        # Wait briefly to ensure run is active and cancellable
        time.sleep(1)

        # Now cancel the run
        cancel_payload = {
            "run_id": run_id
        }
        cancel_resp = requests.post(
            f"{BASE_URL}/grpc/EngineService/CancelRun",
            headers=HEADERS_AUTH,
            json=cancel_payload,
            timeout=TIMEOUT
        )
        assert cancel_resp.status_code == 200, f"CancelRun failed with status {cancel_resp.status_code}"
        cancel_data = cancel_resp.json()
        # We expect a successful CancelRunResponse - the exact content is not specified, so just check response JSON exists
        assert cancel_data is not None, "CancelRun response JSON is None"

    finally:
        # Cleanup: attempt to cancel again in case test failed before cancellation
        try:
            requests.post(
                f"{BASE_URL}/grpc/EngineService/CancelRun",
                headers=HEADERS_AUTH,
                json={"run_id": run_id},
                timeout=TIMEOUT
            )
        except Exception:
            pass

test_cancel_run_successful_cancellation()