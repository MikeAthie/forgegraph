import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def register_user(session, email, password):
    url = f"{BASE_URL}/api/auth/register"
    resp = session.post(url, json={"email": email, "password": password}, timeout=TIMEOUT)
    assert resp.status_code == 200
    user_data = resp.json()
    assert "email" in user_data
    assert "token" in user_data
    assert user_data["email"] == email
    return user_data


def login_user(session, email, password):
    url = f"{BASE_URL}/api/auth/login"
    resp = session.post(url, json={"email": email, "password": password}, timeout=TIMEOUT)
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data
    assert "refresh" in data
    # Removed cookie check as per PRD, refresh token is in JSON body
    return data["access"], data.get("refresh")


def test_post_api_graphs_validate_graph_payload_validation():
    session = requests.Session()

    # Unique email for registration
    unique_email = f"test-{uuid.uuid4()}@example.com"
    password = "ComplexP@ssw0rd!"

    # Register user
    register_user(session, unique_email, password)

    # Login user and get access token and refresh token
    access_token, refresh_token = login_user(session, unique_email, password)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    endpoint = f"{BASE_URL}/api/graphs/validate"

    # 1) Valid graph_json: expect 200 with data.valid == True
    valid_graph_json = {
        # Minimal valid graph example with nodes and edges per typical graph structure
        "nodes": [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "end"},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    payload_valid = {"graph": valid_graph_json}

    resp = session.post(endpoint, json=payload_valid, headers=headers, timeout=TIMEOUT)
    assert resp.status_code == 200
    resp_json = resp.json()
    assert "data" in resp_json
    assert "valid" in resp_json["data"]
    assert resp_json["data"]["valid"] is True

    # 2) Structurally invalid but well-formed graph_json: expect 200 with data.valid == False and errors
    invalid_graph_json = {
        # well-formed but missing required elements, e.g. missing edges key
        "nodes": [],
    }
    payload_invalid_structured = {"graph": invalid_graph_json}

    resp2 = session.post(
        endpoint, json=payload_invalid_structured, headers=headers, timeout=TIMEOUT
    )
    assert resp2.status_code == 200
    resp_json2 = resp2.json()
    assert "data" in resp_json2
    assert "valid" in resp_json2["data"]
    assert resp_json2["data"]["valid"] is False
    assert "errors" in resp_json2["data"]
    assert isinstance(resp_json2["data"]["errors"], list)
    assert len(resp_json2["data"]["errors"]) > 0

    # 3) Missing graph key: expect 400 Bad Request
    payload_missing_graph_json = {}

    resp3 = session.post(
        endpoint, json=payload_missing_graph_json, headers=headers, timeout=TIMEOUT
    )
    assert resp3.status_code == 400


test_post_api_graphs_validate_graph_payload_validation()
