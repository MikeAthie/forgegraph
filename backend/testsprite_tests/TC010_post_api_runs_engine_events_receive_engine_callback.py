import requests
import time
import hmac
import hashlib
import json


BASE_URL = "http://localhost:8000"
SECRET = b"dev_shared_secret"
TIMEOUT = 30


def test_post_api_runs_engine_events_receive_engine_callback():
    url = f"{BASE_URL}/api/runs/engine-events"
    # Sample event payload to send
    event_payload = {
        "event": "run_started",
        "run_id": "123e4567-e89b-12d3-a456-426614174000",
        "timestamp": int(time.time()),
        "details": {"example": "data"}
    }
    raw_body = json.dumps(event_payload).encode("utf-8")

    # Compute timestamp header for signature
    timestamp = str(int(time.time()))

    # Compute signature: HMAC-SHA256 over `${timestamp}.` + raw_body using SECRET
    message = (timestamp + ".").encode("utf-8") + raw_body
    signature = hmac.new(SECRET, message, hashlib.sha256).hexdigest()

    headers_valid = {
        "Content-Type": "application/json",
        "X-ForgeGraph-Timestamp": timestamp,
        "X-ForgeGraph-Signature": signature,
    }

    # Send request with valid signature
    try:
        resp = requests.post(url, headers=headers_valid, data=raw_body, timeout=TIMEOUT)
        assert resp.status_code == 200, f"Expected 200 OK for valid signature, got {resp.status_code}"
    except requests.RequestException as e:
        assert False, f"RequestException during valid signature test: {e}"

    # Send request with missing signature header (expect 401 or 403)
    headers_missing_sig = {
        "Content-Type": "application/json",
        "X-ForgeGraph-Timestamp": timestamp,
    }
    try:
        resp = requests.post(url, headers=headers_missing_sig, data=raw_body, timeout=TIMEOUT)
        assert resp.status_code in (401, 403), f"Expected 401 or 403 for missing signature, got {resp.status_code}"
    except requests.RequestException as e:
        assert False, f"RequestException during missing signature test: {e}"

    # Send request with invalid signature (expect 401 or 403)
    headers_invalid_sig = {
        "Content-Type": "application/json",
        "X-ForgeGraph-Timestamp": timestamp,
        "X-ForgeGraph-Signature": "invalidsignature",
    }
    try:
        resp = requests.post(url, headers=headers_invalid_sig, data=raw_body, timeout=TIMEOUT)
        assert resp.status_code in (401, 403), f"Expected 401 or 403 for invalid signature, got {resp.status_code}"
    except requests.RequestException as e:
        assert False, f"RequestException during invalid signature test: {e}"


test_post_api_runs_engine_events_receive_engine_callback()