from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from django.test import override_settings

from application.services.commerce import ensure_storefront_profile, handle_stripe_event
from application.services.inventory import create_reservation
from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import (
    APIKey,
    CommerceFulfillment,
    CommercePayment,
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


def _create_company(user: User, *, legacy: bool = False) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Legacy Glasswear" if legacy else "Commerce Test Company",
            description="Commerce test company.",
            external_source=EXTERNAL_SOURCE if legacy else "",
            external_ref=EXTERNAL_REF if legacy else "",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    ensure_storefront_profile(
        company=company,
        slug="legacy-glasswear" if legacy else "commerce-test-company",
        display_name=company.name,
        currency="mxn",
    )
    return company


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _create_product(company: Graph, *, quantity: int = 2) -> InventoryProduct:
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        name="Model 1",
        price_mxn=Decimal("700.00"),
        cost_mxn=Decimal("350.00"),
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


def _stripe_key(company: Graph, user: User) -> APIKey:
    return APIKey.objects.create(
        organization=_organization(company),
        user=user,
        provider="stripe",
        name="Legacy Stripe Test",
        encrypted_key=encrypt_api_key("sk_test_legacy"),
        token_metadata={"revoked": False},
    )


def _patch_checkout(monkeypatch, session_id: str = "cs_test_123"):
    def create(**kwargs):
        _ = kwargs
        return SimpleNamespace(id=session_id, url=f"https://checkout.stripe.test/{session_id}")

    monkeypatch.setattr("application.services.commerce.stripe.checkout.Session.create", create)


def test_operator_checkout_api_requires_idempotency(authenticated_client, user):
    company = _create_company(user)
    product = _create_product(company)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )

    response = authenticated_client.post(
        "/api/commerce/checkout-sessions",
        data={"company_id": str(company.id), "reservation_id": str(reservation.id)},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_operator_checkout_api_requires_member(authenticated_client, user):
    company = _create_company(user)
    product = _create_product(company)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.post(
        "/api/commerce/checkout-sessions",
        data={"company_id": str(company.id), "reservation_id": str(reservation.id)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-denied",
    )

    assert response.status_code == 403


def test_operator_checkout_api_is_idempotent(authenticated_client, user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_operator")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    payload = {"company_id": str(company.id), "reservation_id": str(reservation.id)}

    first = authenticated_client.post(
        "/api/commerce/checkout-sessions",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-1",
    )
    second = authenticated_client.post(
        "/api/commerce/checkout-sessions",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-1",
    )
    conflict = authenticated_client.post(
        "/api/commerce/checkout-sessions",
        data={
            "company_id": str(company.id),
            "order_shell_id": first.json()["data"]["order_shell"]["id"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-1",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["duplicate"] is True
    assert conflict.status_code == 409
    assert CommercePayment.objects.filter(company=company).count() == 1


def test_storefront_products_are_public_and_safe(api_client, user):
    company = _create_company(user, legacy=True)
    _create_product(company)

    response = api_client.get("/api/storefront/legacy-glasswear/products")

    assert response.status_code == 200
    product = response.json()["data"]["products"][0]
    assert product["sku"] == "SKU-1"
    assert "cost_mxn" not in product
    assert "notes" not in product


def test_public_checkout_requires_idempotency(api_client, user):
    company = _create_company(user, legacy=True)
    product = _create_product(company)

    response = api_client.post(
        "/api/storefront/legacy-glasswear/checkout-sessions",
        data={"product_id": str(product.id), "quantity": 1},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_public_checkout_reserves_stock_and_returns_stripe_url(api_client, user, monkeypatch):
    company = _create_company(user, legacy=True)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_public")

    response = api_client.post(
        "/api/storefront/legacy-glasswear/checkout-sessions",
        data={"product_id": str(product.id), "quantity": 1, "buyer_alias": "ig-buyer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="public-checkout-1",
    )

    assert response.status_code == 201
    assert response.json()["data"]["checkout_url"].endswith("/cs_public")
    assert InventoryReservation.objects.get(company=company).status == "converted"
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1


@override_settings(COMMERCE_STRIPE_WEBHOOK_SECRET="whsec_test")
def test_storefront_stripe_webhook_rejects_invalid_signature(api_client):
    response = api_client.post(
        "/api/storefront/stripe/webhook",
        data=b'{"id":"evt_1"}',
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="invalid",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_commerce_overview_and_orders_require_viewer(authenticated_client, user):
    company = _create_company(user)

    overview = authenticated_client.get("/api/commerce/overview", {"company_id": str(company.id)})
    orders = authenticated_client.get("/api/commerce/orders", {"company_id": str(company.id)})

    assert overview.status_code == 200
    assert overview.json()["data"]["commerce"]["summary"]["orders_total"] == 0
    assert orders.status_code == 200
    assert orders.json()["data"]["orders"] == []


def test_public_order_status_is_safe(api_client, user, monkeypatch):
    company = _create_company(user, legacy=True)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_public_status")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-public-status",
    )
    from application.services.commerce import create_operator_checkout_session

    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-public-status",
    )
    handle_stripe_event(
        {
            "id": "evt_public_status",
            "type": "checkout.session.completed",
            "data": {"object": {"id": result["stripe_session_id"], "payment_intent": "pi_status"}},
        }
    )
    order = company.inventory_order_shells.get()

    response = api_client.get(
        f"/api/storefront/legacy-glasswear/orders/{order.public_status_token}"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["order"]["reference"] == order.public_reference
    assert "stripe_session_id" not in str(payload)
    assert str(order.id) not in str(payload)


def test_fulfillment_action_api_requires_member_and_is_idempotent(
    authenticated_client, user, monkeypatch
):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_fulfill_api")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-fulfill-api",
    )
    from application.services.commerce import create_operator_checkout_session

    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-fulfill-api",
    )
    handle_stripe_event(
        {
            "id": "evt_fulfill_api",
            "type": "checkout.session.completed",
            "data": {"object": {"id": result["stripe_session_id"], "payment_intent": "pi_api"}},
        }
    )
    order = company.inventory_order_shells.get()

    first = authenticated_client.post(
        f"/api/commerce/orders/{order.id}/fulfillment/mark-ready",
        data={"note": "ready"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="fulfill-ready",
    )
    second = authenticated_client.post(
        f"/api/commerce/orders/{order.id}/fulfillment/mark-ready",
        data={"note": "ready"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="fulfill-ready",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["duplicate"] is True
    assert CommerceFulfillment.objects.get(order=order).status == "ready"
