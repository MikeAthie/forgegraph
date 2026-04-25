import requests
import time
import os
import hmac
import hashlib
import json
import uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30

def test_post_api_runs_engine_events_receive_engine_callback():
    ENGINE_CALLBACK_SECRET = os.environ.get("ENGINE_CALLBACK_SECRET")
    session = requests.Session()

    # Helper functions for user registration and login to create run if needed
    def register_unique_user():
        unique_email = f"testuser_{uuid.uuid4().hex[:10]}@example.com"
        password = "TestPass123!"
        resp = session.post(f"{BASE_URL}/api/auth/register", json={"email": unique_email, "password": password}, timeout=TIMEOUT)
        assert resp.status_code == 201
        user = resp.json()
        assert "id" in user and "email" in user
        assert user["email"] == unique_email
        return unique_email, password

    def login_user(email, password):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert "access" in body
        # Verify refresh_token cookie exists but is HttpOnly (cannot be read here, but presence checked)
        assert "refresh_token" in resp.cookies or any(cookie.name == "refresh_token" for cookie in resp.cookies)
        return body["access"], resp.cookies.get("refresh_token")

    def create_graph_and_version(access_token):
        headers = {"Authorization": f"Bearer {access_token}"}
        # Create graph metadata
        graph_payload = {"name": f"TestGraph_{uuid.uuid4().hex[:8]}", "description": "Test graph description"}
        resp = session.post(f"{BASE_URL}/api/graphs/", json=graph_payload, headers=headers, timeout=TIMEOUT)
        assert resp.status_code == 201
        graph_data = resp.json().get("data")
        assert graph_data and "id" in graph_data
        graph_id = graph_data["id"]

        # Create graph version
        graph_json = {
            "nodes": [{"id": "output-1", "type": "output", "name": "Output", "config": {}}],
            "edges": [{"id": "edge-1", "from": "START", "to": "output-1"}]
        }
        resp = session.post(f"{BASE_URL}/api/graphs/{graph_id}/versions", json={"graph_json": graph_json}, headers=headers, timeout=TIMEOUT)
        assert resp.status_code == 201
        version_data = resp.json().get("data")
        assert version_data and "id" in version_data
        version_id = version_data["id"]
        return version_id

    def start_run(access_token, graph_version_id):
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {"graph_version_id": graph_version_id}
        resp = session.post(f"{BASE_URL}/api/runs/start", json=payload, headers=headers, timeout=TIMEOUT)
        assert resp.status_code == 201
        run_data = resp.json().get("data")
        assert run_data and "id" in run_data and "status" in run_data
        run_id = run_data["id"]
        return run_id

    def post_engine_event(run_id, tenant_id, event_id, timestamp, secret):
        raw_body = json.dumps({
            "type": "test_event",
            "run_id": run_id,
            "tenant_id": tenant_id,
            "event_id": event_id,
            "timestamp": timestamp
        }, separators=(',', ':'))

        msg = f"{timestamp}.{raw_body}".encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-ForgeGraph-Timestamp": str(timestamp),
            "X-ForgeGraph-Signature": signature
        }

        resp = session.post(f"{BASE_URL}/api/runs/engine-events", data=raw_body, headers=headers, timeout=TIMEOUT)
        return resp

    def post_engine_event_invalid_signature(raw_body, timestamp):
        headers = {
            "Content-Type": "application/json",
            "X-ForgeGraph-Timestamp": str(timestamp),
            "X-ForgeGraph-Signature": "invalidsignature"
        }
        resp = session.post(f"{BASE_URL}/api/runs/engine-events", data=raw_body, headers=headers, timeout=TIMEOUT)
        return resp

    def post_engine_event_missing_signature(raw_body, timestamp):
        headers = {
            "Content-Type": "application/json",
            "X-ForgeGraph-Timestamp": str(timestamp)
        }
        resp = session.post(f"{BASE_URL}/api/runs/engine-events", data=raw_body, headers=headers, timeout=TIMEOUT)
        return resp

    # If ENGINE_CALLBACK_SECRET is not set, only test invalid/missing signature returns 401
    if not ENGINE_CALLBACK_SECRET:
        # Prepare a raw minimal body
        timestamp = int(time.time() * 1000)
        raw_body = json.dumps({
            "type": "test_event",
            "run_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "timestamp": timestamp
        }, separators=(',', ':'))

        # Test missing signature
        resp = post_engine_event_missing_signature(raw_body, timestamp)
        assert resp.status_code == 401

        # Test invalid signature
        resp = post_engine_event_invalid_signature(raw_body, timestamp)
        assert resp.status_code == 401

        return

    # ENGINE_CALLBACK_SECRET is available, create a run and test valid events
    # Step 1: Register and login
    email, password = register_unique_user()
    access_token, _ = login_user(email, password)

    # Step 2: Create graph and version
    graph_version_id = create_graph_and_version(access_token)

    # Step 3: Start a run
    run_id = start_run(access_token, graph_version_id)

    # Get tenant_id from run details endpoint (requires auth)
    headers_auth = {"Authorization": f"Bearer {access_token}"}
    resp = session.get(f"{BASE_URL}/api/runs/{run_id}", headers=headers_auth, timeout=TIMEOUT)
    assert resp.status_code == 200
    run_detail = resp.json()
    tenant_id = run_detail.get("tenant_id")
    if not tenant_id:
        # Fallback: extract tenant_id from run_detail["data"] if wrapped
        if "data" in run_detail and "tenant_id" in run_detail["data"]:
            tenant_id = run_detail["data"]["tenant_id"]
    # If still missing tenant_id, use a dummy (should exist but fallback)
    if not tenant_id:
        tenant_id = str(uuid.uuid4())

    # Step 4: Prepare valid event payload
    event_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)
    raw_body = json.dumps({
        "type": "test_event",
        "run_id": run_id,
        "tenant_id": tenant_id,
        "event_id": event_id,
        "timestamp": timestamp
    }, separators=(',', ':'))

    # Send valid event - expect 200
    resp = post_engine_event(run_id, tenant_id, event_id, timestamp, ENGINE_CALLBACK_SECRET)
    assert resp.status_code == 200
    resp_json = resp.json()
    assert "data" in resp_json
    # duplicate should be False or not present on first send
    assert resp_json["data"].get("duplicate") in (None, False)

    # Resend same event_id with same timestamp and body - expect duplicate=true
    resp_dup = post_engine_event(run_id, tenant_id, event_id, timestamp, ENGINE_CALLBACK_SECRET)
    assert resp_dup.status_code == 200
    resp_dup_json = resp_dup.json()
    assert "data" in resp_dup_json
    assert resp_dup_json["data"].get("duplicate") is True