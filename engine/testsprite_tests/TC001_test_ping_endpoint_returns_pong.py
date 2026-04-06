import requests

def test_ping_endpoint_returns_pong():
    base_url = "http://localhost:50051"
    url = f"{base_url}/grpc/EngineService/Ping"
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()
        json_resp = response.json()
        # Assert status code is 200
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        # Assert response contains 'pong'
        assert "pong" in json_resp.get("message", "").lower() or json_resp.get("message") == "pong" or "pong" in response.text.lower(), \
            f"Response JSON does not contain 'pong': {json_resp}"
    except requests.RequestException as e:
        assert False, f"Request to Ping endpoint failed: {e}"

test_ping_endpoint_returns_pong()