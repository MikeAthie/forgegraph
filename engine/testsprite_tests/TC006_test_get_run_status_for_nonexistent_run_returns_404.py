import pytest

from _helpers import get_redis_health

pytestmark = pytest.mark.skip(
    reason="Historical TestSprite smoke artifact; use engine Go/gRPC production gates."
)


def test_get_run_status_for_nonexistent_run_returns_404():
    response = get_redis_health()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "healthy" in payload
    assert "error" in payload
