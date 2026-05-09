from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
)
from infrastructure.orm.models import Graph, InventoryProduct, InventoryStockUnit


@pytest.mark.django_db
def test_import_legacy_inventory_phase2_uses_cost_analysis_csv():
    call_command(
        "seed_legacy_glasswear_phase0",
        password="LegacyPhase0!12345",
        output_json=True,
        stdout=StringIO(),
    )
    output = StringIO()

    call_command("import_legacy_inventory_phase2", output_json=True, stdout=output)

    payload = json.loads(output.getvalue())
    company = Graph.objects.get(id=payload["company_id"])
    assert payload["products_seen"] == 21
    assert payload["total_active_units"] == 62
    assert payload["stock_units_created"] == 62
    assert InventoryProduct.objects.filter(company=company).count() == 21
    assert (
        InventoryStockUnit.objects.filter(company=company).exclude(status="removed").count() == 62
    )
    assert set(
        InventoryProduct.objects.filter(company=company, anchor_model=True).values_list(
            "model",
            flat=True,
        )
    ) == {"TAYLOR", "ROBBIE", "VICE", "HUNT", "WATSON", "MAVERICK"}


@pytest.mark.django_db
def test_import_legacy_inventory_phase2_is_idempotent():
    call_command(
        "seed_legacy_glasswear_phase0",
        password="LegacyPhase0!12345",
        output_json=True,
        stdout=StringIO(),
    )
    first_output = StringIO()
    second_output = StringIO()

    call_command("import_legacy_inventory_phase2", output_json=True, stdout=first_output)
    call_command("import_legacy_inventory_phase2", output_json=True, stdout=second_output)

    first = json.loads(first_output.getvalue())
    second = json.loads(second_output.getvalue())
    company = Graph.objects.get(id=first["company_id"])
    assert first["user_id"] == str(company.owner_id)
    assert second["stock_units_created"] == 0
    assert second["total_active_units"] == 62
    assert InventoryProduct.objects.filter(company=company).count() == 21
    assert (
        InventoryStockUnit.objects.filter(company=company).exclude(status="removed").count() == 62
    )


@pytest.mark.django_db
def test_import_legacy_inventory_phase2_requires_phase0_workspace():
    output = StringIO()

    with pytest.raises(CommandError, match="Legacy user was not found"):
        call_command("import_legacy_inventory_phase2", output_json=True, stdout=output)

    assert DEFAULT_EMAIL == "legacy.glasswear.test@example.com"
