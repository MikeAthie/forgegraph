import requests

def test_metrics_endpoint_returns_prometheus_metrics():
    url = "http://localhost:9090/metrics"
    headers = {
        "Accept": "text/plain"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        content_type = response.headers.get("Content-Type", "")
        assert "text/plain" in content_type, f"Expected 'text/plain' content type, got {content_type}"
        content = response.text
        # Basic validation that response contains typical Prometheus metric identifiers
        assert "runtime" in content or "engine" in content or "prometheus" in content or "# HELP" in content or "# TYPE" in content, \
            "Prometheus metrics text not found in response content"
    except requests.RequestException as e:
        assert False, f"Request to /metrics endpoint failed: {e}"

test_metrics_endpoint_returns_prometheus_metrics()