import requests

def test_metrics_endpoint_returns_prometheus_metrics():
    url = "http://localhost:9090/metrics"
    headers = {
        "Accept": "text/plain"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        assert False, f"HTTP request failed: {e}"

    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    content_type = response.headers.get("Content-Type", "")
    assert "text/plain" in content_type, f"Expected Content-Type 'text/plain', got {content_type}"
    content = response.text
    assert content.strip() != "", "Metrics response is empty"
    # Check for at least one Prometheus metric pattern (e.g., help or type lines)
    assert any(line.startswith("# HELP") or line.startswith("# TYPE") for line in content.splitlines()), \
        "Response does not contain Prometheus metric HELP or TYPE lines"

test_metrics_endpoint_returns_prometheus_metrics()