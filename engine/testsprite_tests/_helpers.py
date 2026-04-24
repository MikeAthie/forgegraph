import requests

METRICS_BASE_URL = "http://localhost:9090"
TIMEOUT = 30


def get_ready() -> requests.Response:
    return requests.get(f"{METRICS_BASE_URL}/ready", timeout=TIMEOUT)


def get_metrics() -> requests.Response:
    return requests.get(f"{METRICS_BASE_URL}/metrics", headers={"Accept": "text/plain"}, timeout=TIMEOUT)


def get_redis_health() -> requests.Response:
    return requests.get(f"{METRICS_BASE_URL}/health/redis", timeout=TIMEOUT)

