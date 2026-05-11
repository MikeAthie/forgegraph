from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import call_command

from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import DEFAULT_EMAIL
from infrastructure.orm.models import CompanyOperationObjective, NodeRun, Run, TaskRecord

pytestmark = pytest.mark.django_db


def test_legacy_glasswear_first_run_serializes_bootstrap_evidence():
    out = StringIO()

    call_command(
        "legacy_glasswear_first_run",
        database="default",
        password="ForgeGraphLegacy!123",
        output_json=True,
        strict=True,
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["schema"] == "legacy_glasswear_first_run.v1"
    assert payload["verification_result"]["passed"] is True
    assert payload["observed_data"]["products_imported"] == 21
    assert payload["observed_data"]["active_units_imported"] == 62
    assert payload["observed_data"]["inventory_products_visible"] == 21
    assert payload["observed_data"]["inventory_total_units"] == 62
    assert payload["verification_result"]["checks"]["stock_semantics_agree"] is True
    assert payload["stock_semantics_report"]["definition_used"]


def test_seed_legacy_phase6_mock_objective_creates_backend_owned_task(tmp_path):
    call_command(
        "seed_legacy_glasswear_phase0",
        email=DEFAULT_EMAIL,
        password="ForgeGraphLegacy!123",
        output_json=True,
        stdout=StringIO(),
    )
    evidence_path = tmp_path / "legacy-phase6.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema": "legacy_phase6_evidence.v1",
                "observed_data": {
                    "stock_semantics_report": {
                        "active_count": 12,
                        "low_stock_count": 1,
                        "last_piece_count": 2,
                        "sold_out_count": 6,
                        "definition_used": "Only active products are counted.",
                    },
                    "visual_asset_briefs": [
                        _brief("GAGA", "NC-29046", "low_stock"),
                        _brief("HENDRIX", "NC-29026", "last_piece"),
                        _brief("WINEHOUSE", "YD-GN1127T", "last_piece"),
                        _brief("WATSON", "NG-1059", "active"),
                        _brief("MAVERICK", "NC-39025", "active"),
                    ],
                    "next_run_plan": [
                        "Review the briefs.",
                        "Approve gated publication drafts.",
                        "Keep procurement in zero-cash review.",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    out = StringIO()

    call_command(
        "seed_legacy_phase6_mock_objective",
        source_evidence_path=str(evidence_path),
        output_json=True,
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["schema"] == "legacy_phase6_mock_objective_seed.v1"
    assert payload["mock_provider_response"] is True
    assert payload["visual_asset_brief_count"] == 5

    run = Run.objects.get(id=payload["run_id"])
    run_output = cast(dict[str, Any], run.output_json)
    assert run.status == "succeeded"
    assert run_output["visual_asset_brief"]["mock_provider_response"] is True
    assert len(run_output["visual_asset_brief"]["visual_asset_briefs"]) == 5

    node_run = NodeRun.objects.get(id=payload["node_run_id"])
    node_output = cast(dict[str, Any], node_run.output_json)
    assert node_run.status == "succeeded"
    assert node_output["provider"] == "mock"

    task = TaskRecord.objects.get(id=payload["task_id"])
    assert task.status == "completed"
    assert task.current_step_id == node_run.id

    objective = CompanyOperationObjective.objects.get(id=payload["objective_contract_id"])
    integrity_gates = cast(dict[str, Any], objective.integrity_gates_json)
    assert objective.operation_id == run.id
    assert objective.success_score == 100
    assert integrity_gates["mock_provider_response"] is True


def _brief(product_name: str, sku: str, stock_state: str) -> dict[str, object]:
    return {
        "product_name": product_name,
        "sku": sku,
        "stock_state": stock_state,
        "shot_list": ["Hero product shot"],
        "caption_angle": f"{product_name} approval-gated caption angle.",
        "background_or_prop_needs": ["Existing studio surface"],
        "approval_task_title": f"Approve Visual Brief for {product_name}",
    }
