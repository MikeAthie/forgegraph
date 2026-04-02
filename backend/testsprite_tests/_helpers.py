import hashlib
import hmac
import json
import time
import uuid

import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
ENGINE_CALLBACK_SECRET = "dev_shared_secret"


def unique_email() -> str:
    return f"testsprite-{uuid.uuid4().hex}@example.com"


def register_user(session: requests.Session, password: str = "StrongPass!123") -> tuple[str, str, dict]:
    email = unique_email()
    response = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["email"] == email
    return email, password, user


def login_user(session: requests.Session, email: str, password: str) -> str:
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "access" in payload and payload["access"]
    assert "refresh" not in payload
    assert len(session.cookies) >= 1
    return payload["access"]


def bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def create_graph(
    session: requests.Session,
    access_token: str,
    *,
    name: str | None = None,
    description: str = "",
) -> dict:
    response = session.post(
        f"{BASE_URL}/api/graphs/",
        json={"name": name or f"Test Graph {uuid.uuid4().hex[:8]}", "description": description},
        headers=bearer_headers(access_token),
        timeout=TIMEOUT,
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    assert payload["id"]
    return payload


def valid_graph_json() -> dict:
    return {
        "nodes": [
            {"id": "output-1", "type": "output", "name": "Output", "config": {}},
        ],
        "edges": [
            {"id": "edge-1", "from": "START", "to": "output-1"},
        ],
    }


def create_graph_version(
    session: requests.Session,
    access_token: str,
    graph_id: str,
    graph_json: dict | None = None,
) -> dict:
    response = session.post(
        f"{BASE_URL}/api/graphs/{graph_id}/versions",
        json={"graph_json": graph_json or valid_graph_json()},
        headers=bearer_headers(access_token),
        timeout=TIMEOUT,
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    assert payload["id"]
    return payload


def start_run(
    session: requests.Session,
    access_token: str,
    graph_version_id: str,
    input_json: dict | None = None,
) -> requests.Response:
    return session.post(
        f"{BASE_URL}/api/runs/start",
        json={"graph_version_id": graph_version_id, "input_json": input_json or {}},
        headers=bearer_headers(access_token),
        timeout=TIMEOUT,
    )


def get_me(session: requests.Session, access_token: str) -> dict:
    response = session.get(
        f"{BASE_URL}/api/auth/me",
        headers=bearer_headers(access_token),
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    return response.json()


def sign_engine_event(payload: dict, *, timestamp_ms: str | None = None) -> tuple[str, str, str]:
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = timestamp_ms or str(int(time.time() * 1000))
    signature = hmac.new(
        ENGINE_CALLBACK_SECRET.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return body, timestamp, signature
