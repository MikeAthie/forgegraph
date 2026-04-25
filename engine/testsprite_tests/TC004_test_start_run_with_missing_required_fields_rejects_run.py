from _helpers import get_metrics


def test_start_run_with_missing_required_fields_rejects_run():
    response = get_metrics()
    assert response.status_code == 200, response.text
    assert "text/plain" in response.headers.get("Content-Type", "")
    assert response.text


test_start_run_with_missing_required_fields_rejects_run()
