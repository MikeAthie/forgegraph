from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone

from application.services.inventory import create_reservation
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    InventoryProduct,
    InventoryReservation,
    InventoryStockUnit,
    Organization,
    OrganizationMembership,
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


def _create_product_with_units(company: Graph, *, quantity: int = 2) -> InventoryProduct:
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
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
    return product


def test_inventory_overview_allows_viewer(authenticated_client, user):
    company = _create_company(user)
    _create_product_with_units(company)
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.get("/api/inventory/overview", {"company_id": str(company.id)})

    assert response.status_code == 200
    inventory = response.json()["data"]["inventory"]
    assert inventory["summary"]["total_units"] == 2
    assert inventory["summary"]["low_stock_products"] == 1
    assert inventory["stock_state_summary"]["low_stock_count"] == 1
    assert inventory["products"][0]["sku"] == "SKU-1"
    assert inventory["products"][0]["stock_state"] == "low_stock"


def test_inventory_reservation_api_requires_member(authenticated_client, user):
    company = _create_company(user)
    product = _create_product_with_units(company)
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.post(
        "/api/inventory/reservations",
        data={
            "company_id": str(company.id),
            "product_id": str(product.id),
            "quantity": 1,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="reserve-denied",
    )

    assert response.status_code == 403


def test_inventory_reservation_api_is_idempotent(authenticated_client, user):
    company = _create_company(user)
    product = _create_product_with_units(company)
    payload = {
        "company_id": str(company.id),
        "product_id": str(product.id),
        "quantity": 1,
        "buyer_alias": "ig-lead-1",
    }

    first = authenticated_client.post(
        "/api/inventory/reservations",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="reserve-1",
    )
    second = authenticated_client.post(
        "/api/inventory/reservations",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="reserve-1",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["duplicate"] is True
    assert InventoryReservation.objects.filter(company=company).count() == 1
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


def test_inventory_reservation_api_rejects_idempotency_conflict(authenticated_client, user):
    company = _create_company(user)
    product = _create_product_with_units(company, quantity=3)
    payload = {
        "company_id": str(company.id),
        "product_id": str(product.id),
        "quantity": 1,
    }
    conflict_payload = {
        "company_id": str(company.id),
        "product_id": str(product.id),
        "quantity": 2,
    }

    first = authenticated_client.post(
        "/api/inventory/reservations",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="reserve-conflict",
    )
    second = authenticated_client.post(
        "/api/inventory/reservations",
        data=conflict_payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="reserve-conflict",
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_inventory_release_extend_and_order_shell_api(authenticated_client, user):
    company = _create_company(user)
    product = _create_product_with_units(company)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        quantity=1,
        actor=user,
        idempotency_key="service-reserve",
    )

    extend = authenticated_client.post(
        f"/api/inventory/reservations/{reservation.id}/extend",
        data={"minutes": 45},
        format="json",
        HTTP_IDEMPOTENCY_KEY="extend-1",
    )
    order = authenticated_client.post(
        f"/api/inventory/reservations/{reservation.id}/order-shell",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="order-1",
    )
    release = authenticated_client.post(
        f"/api/inventory/reservations/{reservation.id}/release",
        data={"reason": "changed mind"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="release-after-order",
    )

    assert extend.status_code == 200
    assert order.status_code == 201
    assert order.json()["data"]["order_shell"]["status"] == "pending_payment"
    assert release.status_code == 409
    reservation.refresh_from_db()
    assert reservation.status == "converted"
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


def test_inventory_expire_due_api_restores_stock(authenticated_client, user):
    company = _create_company(user)
    product = _create_product_with_units(company)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        quantity=1,
        actor=user,
        idempotency_key="expire-api",
    )
    reservation.expires_at = timezone.now() - timedelta(minutes=1)
    reservation.save(update_fields=["expires_at", "updated_at"])

    response = authenticated_client.post(
        "/api/inventory/reservations/expire-due",
        data={"company_id": str(company.id)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="expire-due-1",
    )

    assert response.status_code == 200
    assert response.json()["data"]["expired_count"] == 1
    assert InventoryReservation.objects.get(id=reservation.id).status == "expired"
    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 2


def test_inventory_api_hides_other_organization_inventory(authenticated_client, user):
    other_user = User.objects.create_user(email="inventory-other@example.com", password="pw123456")
    ensure_default_organization(other_user)
    other_company = _create_company(other_user, name="Other Inventory")
    _create_product_with_units(other_company)

    response = authenticated_client.get(
        "/api/inventory/overview",
        {"company_id": str(other_company.id)},
    )

    assert response.status_code == 404
