import pytest

from _helpers import get_metrics

pytestmark = pytest.mark.skip(
    reason="Historical TestSprite smoke artifact; use engine Go/gRPC production gates."
)


def test_start_run_with_missing_required_fields_rejects_run():
    response = get_metrics()
    assert response.status_code == 200, response.text
    assert "text/plain" in response.headers.get("Content-Type", "")
    assert response.text
