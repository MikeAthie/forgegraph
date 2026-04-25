from _helpers import get_ready


def test_get_run_status_returns_current_status():
    response = get_ready()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert isinstance(payload["run_state_mode"], str)


test_get_run_status_returns_current_status()
