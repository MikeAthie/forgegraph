def test_operating_model_pack_health_api_reports_required_pack(api_client, monkeypatch) -> None:
    monkeypatch.delenv("OPERATING_MODEL_PACKS_DIR", raising=False)
    monkeypatch.setenv("REQUIRED_OPERATING_MODEL_PACKS", "digital_marketing_pro")

    response = api_client.get("/api/system/operating-model-packs/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["missing_required_packs"] == []
    pack = next(item for item in payload["packs"] if item["pack_id"] == "digital_marketing_pro")
    assert {
        "atlas_agency_work_graph",
        "atlas_launch_deployment",
        "atlas_performance_review",
    }.issubset(set(pack["contains"]))
