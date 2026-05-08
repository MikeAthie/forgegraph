from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from django.utils import timezone

from application.services.inventory import (
    InventoryError,
    create_order_shell,
    create_reservation,
    expire_due_reservations,
    import_inventory_csv,
    inventory_overview_payload,
    release_reservation,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    InventoryEvent,
    InventoryProduct,
    InventoryReservation,
    InventoryStockUnit,
    Organization,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "Inventory Test Company") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Inventory test company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _write_csv(path: Path, *, quantity: int = 2, price: str = "$700.00") -> Path:
    path.write_text(
        "\n".join(
            [
                ",,,,,",
                ",#,Modelo,Nombre Comercial,Foto,Color, Costo Pesos ,Precio ajustado,Inventario",
                f",1,GR-8024,LENNON,,BLUE,$416.58,{price},{quantity}",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_inventory_csv_import_creates_products_and_stock_units(tmp_path, user):
    company = _create_company(user)
    csv_path = _write_csv(tmp_path / "inventory.csv", quantity=4)

    result = import_inventory_csv(company=company, csv_path=csv_path, actor=user)

    product = InventoryProduct.objects.get(company=company, sku="GR-8024")
    assert result.products_seen == 1
    assert result.products_created == 1
    assert result.stock_units_created == 4
    assert product.model == "LENNON"
    assert product.price_mxn == Decimal("700.00")
    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 4
    assert InventoryEvent.objects.filter(company=company, event_type="import").count() == 1


def test_inventory_csv_rerun_updates_metadata_without_deleting_reserved_units(tmp_path, user):
    company = _create_company(user)
    csv_path = _write_csv(tmp_path / "inventory.csv", quantity=3)
    import_inventory_csv(company=company, csv_path=csv_path, actor=user)
    product = InventoryProduct.objects.get(company=company, sku="GR-8024")
    create_reservation(
        company=company,
        product_id=str(product.id),
        quantity=1,
        actor=user,
        idempotency_key="hold-1",
    )

    _write_csv(csv_path, quantity=1, price="$720.00")
    result = import_inventory_csv(company=company, csv_path=csv_path, actor=user)

    product.refresh_from_db()
    assert product.price_mxn == Decimal("720.00")
    assert result.stock_units_removed == 2
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1
    assert InventoryStockUnit.objects.filter(product=product).exclude(status="removed").count() == 1


def test_create_reservation_locks_oldest_available_units(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    for unit_number in range(1, 4):
        InventoryStockUnit.objects.create(
            organization=_organization(company),
            company=company,
            product=product,
            unit_number=unit_number,
            status="available",
        )

    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        quantity=2,
        buyer_alias="buyer@example.com",
        note="phone 555-123-4567",
        actor=user,
        idempotency_key="reserve-1",
    )

    held_units = list(
        InventoryStockUnit.objects.filter(current_reservation=reservation).order_by("unit_number")
    )
    assert reservation.quantity == 2
    assert reservation.buyer_alias == "[redacted-email]"
    assert reservation.note == "phone [redacted-number]"
    assert [unit.unit_number for unit in held_units] == [1, 2]
    assert all(unit.status == "reserved" for unit in held_units)


def test_duplicate_reservation_reuses_same_hold(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=1,
        status="available",
    )

    first = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="same-key",
    )
    second = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="same-key",
    )

    assert second.id == first.id
    assert InventoryReservation.objects.filter(company=company).count() == 1
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


def test_inventory_overview_uses_canonical_stock_states(user):
    company = _create_company(user)
    counts = {
        "ACTIVE": 4,
        "LOW": 2,
        "LAST": 1,
        "SOLDOUT": 0,
    }
    for sku, quantity in counts.items():
        product = InventoryProduct.objects.create(
            organization=_organization(company),
            company=company,
            sku=sku,
            model=sku,
            price_mxn=100,
            cost_mxn=50,
        )
        for unit_number in range(1, quantity + 1):
            InventoryStockUnit.objects.create(
                organization=_organization(company),
                company=company,
                product=product,
                unit_number=unit_number,
                status="available",
            )
    archived = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="ARCHIVED",
        model="Archived",
        price_mxn=100,
        cost_mxn=50,
        status="archived",
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=archived,
        unit_number=1,
        status="available",
    )

    overview = inventory_overview_payload(company)
    states = {product["sku"]: product["stock_state"] for product in overview["products"]}

    assert overview["stock_state_summary"]["active_count"] == 1
    assert overview["stock_state_summary"]["low_stock_count"] == 1
    assert overview["stock_state_summary"]["last_piece_count"] == 1
    assert overview["stock_state_summary"]["sold_out_count"] == 1
    assert overview["summary"]["low_stock_products"] == 1
    assert overview["summary"]["last_piece_products"] == 1
    assert overview["summary"]["sold_out_products"] == 1
    assert states["ACTIVE"] == "active"
    assert states["LOW"] == "low_stock"
    assert states["LAST"] == "last_piece"
    assert states["SOLDOUT"] == "sold_out"
    assert states["ARCHIVED"] is None


def test_no_oversell_when_only_one_unit_remains(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=1,
        status="available",
    )

    create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="winner",
    )
    with pytest.raises(InventoryError, match="Only 0 available"):
        create_reservation(
            company=company,
            product_id=str(product.id),
            actor=user,
            idempotency_key="loser",
        )

    assert InventoryReservation.objects.filter(company=company, status="active").count() == 1
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


def test_release_and_expire_restore_available_stock(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    for unit_number in range(1, 3):
        InventoryStockUnit.objects.create(
            organization=_organization(company),
            company=company,
            product=product,
            unit_number=unit_number,
            status="available",
        )

    released = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="release-me",
    )
    release_reservation(reservation=released, actor=user)
    expiring = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="expire-me",
    )
    expiring.expires_at = timezone.now() - timedelta(minutes=1)
    expiring.save(update_fields=["expires_at", "updated_at"])

    expired = expire_due_reservations(company=company, actor=user)

    assert len(expired) == 1
    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 2
    assert InventoryReservation.objects.filter(company=company, status="released").count() == 1
    assert InventoryReservation.objects.filter(company=company, status="expired").count() == 1


def test_order_shell_conversion_keeps_units_reserved(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=1,
        status="available",
    )
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="convert-me",
    )

    order = create_order_shell(reservation=reservation, actor=user, idempotency_key="order-1")

    reservation.refresh_from_db()
    assert order.status == "pending_payment"
    assert reservation.status == "converted"
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


def test_inventory_overview_computes_counts_from_units(user):
    company = _create_company(user)
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        price_mxn=100,
        cost_mxn=50,
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=1,
        status="available",
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=2,
        status="sold",
    )

    payload = inventory_overview_payload(company)

    assert payload["summary"]["total_units"] == 2
    assert payload["summary"]["available_units"] == 1
    assert payload["summary"]["sold_units"] == 1
    assert payload["products"][0]["sku"] == "SKU-1"
