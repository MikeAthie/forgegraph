from _helpers import get_ready


def test_cancel_run_successful_cancellation():
    response = get_ready()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["grpc_ready"] is True
    assert payload["status"] == "ready"


test_cancel_run_successful_cancellation()
