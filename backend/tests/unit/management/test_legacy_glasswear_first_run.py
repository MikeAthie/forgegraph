from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

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
