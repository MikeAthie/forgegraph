from _helpers import get_redis_health


def test_get_run_status_for_nonexistent_run_returns_404():
    response = get_redis_health()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "healthy" in payload
    assert "error" in payload


test_get_run_status_for_nonexistent_run_returns_404()
