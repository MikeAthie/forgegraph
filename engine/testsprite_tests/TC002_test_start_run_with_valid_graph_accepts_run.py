from _helpers import get_ready


def test_start_run_with_valid_graph_accepts_run():
    response = get_ready()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["grpc_ready"] is True
    assert "run_state_mode" in payload
    assert "control_plane_configured" in payload


test_start_run_with_valid_graph_accepts_run()
