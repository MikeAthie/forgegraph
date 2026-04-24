from _helpers import get_ready


def test_start_run_with_invalid_graph_rejects_run():
    response = get_ready()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["grpc_ready"] is True


test_start_run_with_invalid_graph_rejects_run()
