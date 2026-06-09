import pytest

from application.services.operating_model_packs import (
    OperatingModelPackError,
    build_operating_model_pack_health_payload,
    validate_required_operating_model_packs,
)


def test_operating_model_pack_health_reports_required_atlas_pack(monkeypatch) -> None:
    monkeypatch.delenv("OPERATING_MODEL_PACKS_DIR", raising=False)
    monkeypatch.setenv("REQUIRED_OPERATING_MODEL_PACKS", "digital_marketing_pro")

    payload = build_operating_model_pack_health_payload()

    assert payload["status"] == "ok"
    assert payload["missing_required_packs"] == []
    assert payload["missing_required_contents"] == []
    pack = next(item for item in payload["packs"] if item["pack_id"] == "digital_marketing_pro")
    assert pack["config_hash"].startswith("sha256:")
    assert {
        "atlas_agency_work_graph",
        "atlas_launch_deployment",
        "atlas_performance_review",
    }.issubset(set(pack["contains"]))


def test_required_operating_model_pack_validation_fails_for_missing_dir(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPERATING_MODEL_PACKS_DIR", str(tmp_path / "missing-packs"))
    monkeypatch.setenv("REQUIRED_OPERATING_MODEL_PACKS", "digital_marketing_pro")

    with pytest.raises(OperatingModelPackError) as exc_info:
        validate_required_operating_model_packs()

    assert exc_info.value.code == "required_operating_model_packs_unhealthy"
    assert exc_info.value.details[0]["missing_required_packs"] == ["digital_marketing_pro"]
