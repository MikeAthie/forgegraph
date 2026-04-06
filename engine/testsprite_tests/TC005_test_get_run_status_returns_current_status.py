import requests
import uuid
import time

BASE_URL = "http://localhost:50051"
TIMEOUT = 30
AUTH_HEADER = {
    # Assuming some kind of token required; if no auth required, leave empty or remove
    # "Authorization": "Bearer YOUR_AUTH_TOKEN"
}

def test_get_run_status_returns_current_status():
    # Create a new run first via StartRun to get a valid run_id and start execution
    start_run_url = f"{BASE_URL}/grpc/EngineService/StartRun"
    get_run_status_url = f"{BASE_URL}/grpc/EngineService/GetRunStatus"
    cancel_run_url = f"{BASE_URL}/grpc/EngineService/CancelRun"

    run_id = str(uuid.uuid4())
    # A minimal valid graph_json and input_json that can be used to start a run
    graph_json = '{"nodes": [{"id": "node1","type": "prompt","parameters": {"text": "hello"}}], "edges": []}'
    input_json = '{}'
    callback_url = ""

    start_payload = {
        "run_id": run_id,
        "graph_json": graph_json,
        "input_json": input_json,
        "callback_url": callback_url
    }

    headers = {"Content-Type": "application/json"}
    headers.update(AUTH_HEADER)

    try:
        # 1. Start the run
        resp_start = requests.post(start_run_url, json=start_payload, headers=headers, timeout=TIMEOUT)
        assert resp_start.status_code == 200, f"StartRun returned unexpected status {resp_start.status_code}"
        data_start = resp_start.json()
        # accepted must be true
        accepted = data_start.get("accepted", None)
        assert accepted is True, f"StartRun response accepted is not True: {data_start}"

        # Wait briefly to allow run progress
        time.sleep(2)

        # 2. Query the run status
        status_payload = {"run_id": run_id}
        resp_status = requests.post(get_run_status_url, json=status_payload, headers=headers, timeout=TIMEOUT)
        assert resp_status.status_code == 200, f"GetRunStatus returned unexpected status {resp_status.status_code}"
        data_status = resp_status.json()

        # Validate presence of current status and current node info
        # Expected keys: status (string), current_node (object or string)
        status = data_status.get("status")
        current_node = data_status.get("current_node")

        assert status is not None and isinstance(status, str) and status != "", \
            f"Status missing or invalid in GetRunStatus response: {data_status}"
        assert current_node is not None, f"Current node missing in GetRunStatus response: {data_status}"

    finally:
        # Cleanup: cancel the run to clean resources
        cancel_payload = {"run_id": run_id}
        try:
            resp_cancel = requests.post(cancel_run_url, json=cancel_payload, headers=headers, timeout=TIMEOUT)
            assert resp_cancel.status_code == 200, f"CancelRun returned unexpected status {resp_cancel.status_code}"
        except Exception:
            pass  # Ignore exceptions during cleanup


test_get_run_status_returns_current_status()