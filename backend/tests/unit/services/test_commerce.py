from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from django.utils import timezone

from application.services.commerce import (
    CommerceError,
    add_order_operator_note,
    commerce_overview_payload,
    create_operator_checkout_session,
    create_public_checkout_session,
    ensure_storefront_profile,
    handle_stripe_event,
    public_order_status_payload,
    storefront_products_payload,
    transition_fulfillment,
)
from application.services.inventory import create_reservation
from application.services.provider_credentials import import_provider_credential
from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import decrypt_api_key, encrypt_api_key
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import (
    APIKey,
    CommerceCashLedgerEntry,
    CommerceFulfillment,
    CommercePayment,
    CommerceStripeEvent,
    Graph,
    GraphVersion,
    InventoryOrderShell,
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
        photo_url="https://example.com/frame.jpg",
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
        name="Stripe Commerce Test",
        encrypted_key=encrypt_api_key("sk_test_legacy"),
        token_metadata={"revoked": False},
    )


def _stripe_session(session_id: str = "cs_test_123") -> SimpleNamespace:
    return SimpleNamespace(id=session_id, url=f"https://checkout.stripe.test/{session_id}")


def _patch_checkout(monkeypatch, session_id: str = "cs_test_123"):
    calls: list[dict[str, object]] = []

    def create(**kwargs):
        calls.append(kwargs)
        return _stripe_session(session_id)

    monkeypatch.setattr("application.services.commerce.stripe.checkout.Session.create", create)
    return calls


def _completed_event(session_id: str, event_id: str = "evt_completed_1") -> dict[str, object]:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "payment_intent": "pi_test_123",
                "created": int(timezone.now().timestamp()),
                "customer_details": {
                    "email": "buyer@example.com",
                    "name": "Buyer One",
                    "address": {"country": "MX", "city": "CDMX"},
                },
            }
        },
    }


def _expired_event(session_id: str, event_id: str = "evt_expired_1") -> dict[str, object]:
    return {
        "id": event_id,
        "type": "checkout.session.expired",
        "data": {
            "object": {
                "id": session_id,
                "created": int(timezone.now().timestamp()),
            }
        },
    }


def test_provider_credential_import_redacts_key(monkeypatch, user):
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    monkeypatch.setenv("STRIPE_TEST", "sk_test_secret_value")

    credential, result = import_provider_credential(
        organization=organization,
        user=user,
        provider="stripe",
        name="Stripe Commerce Test",
        env_var="STRIPE_TEST",
        purpose="commerce_test",
    )

    payload = result.as_dict()
    assert payload["provider"] == "stripe"
    assert payload["key_present"] is True
    assert "sk_test_secret_value" not in str(payload)
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "sk_test_secret_value"


def test_legacy_storefront_profile_uses_generic_slug_resolution(user):
    user = User.objects.create_user(email="legacy.glasswear.test@example.com", password="pw")
    ensure_default_organization(user)
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="owner")
    company = _create_company(user, legacy=True)

    payload = storefront_products_payload(company)

    assert payload["company_slug"] == "legacy-glasswear"
    assert payload["storefront_display_name"] == "Legacy Glasswear"


def test_operator_checkout_creates_stripe_session_and_payment(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    calls = _patch_checkout(monkeypatch)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )

    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-1",
    )

    payment = CommercePayment.objects.get(company=company)
    order = InventoryOrderShell.objects.get(company=company)
    reservation.refresh_from_db()
    assert result["checkout_url"].startswith("https://checkout.stripe.test/")
    assert payment.status == "pending"
    assert payment.amount_mxn == Decimal("700.00")
    assert order.status == "pending_payment"
    assert reservation.status == "converted"
    assert calls[0]["mode"] == "payment"
    assert calls[0]["line_items"][0]["price_data"]["currency"] == "mxn"


def test_operator_checkout_replays_existing_payment(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_test_same")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )

    first = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-same",
    )
    second = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-same",
    )

    assert second["stripe_session_id"] == first["stripe_session_id"]
    assert CommercePayment.objects.filter(company=company).count() == 1


def test_public_checkout_reserves_stock_before_stripe_session(user, monkeypatch):
    company = _create_company(user, legacy=True)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch)

    result = create_public_checkout_session(
        company=company,
        product_id=str(product.id),
        quantity=1,
        buyer_alias="ig-buyer",
        idempotency_key="public-checkout-1",
    )

    assert result["checkout_url"]
    assert InventoryReservation.objects.get(company=company).status == "converted"
    assert InventoryStockUnit.objects.filter(product=product, status="reserved").count() == 1
    assert CommercePayment.objects.get(company=company).metadata_json["source"] == "storefront"


def test_public_checkout_failure_releases_stock(user, monkeypatch):
    company = _create_company(user, legacy=True)
    product = _create_product(company)
    _stripe_key(company, user)

    def fail_create(**kwargs):
        _ = kwargs
        raise CommerceError("stripe_down", "Stripe unavailable.")

    monkeypatch.setattr(
        "application.services.commerce.stripe.checkout.Session.create",
        fail_create,
    )

    with pytest.raises(CommerceError):
        create_public_checkout_session(
            company=company,
            product_id=str(product.id),
            quantity=1,
            idempotency_key="public-failure",
        )

    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 2
    payment = CommercePayment.objects.get(company=company)
    assert payment.status == "failed"
    assert InventoryOrderShell.objects.get(company=company).status == "cancelled"


def test_completed_webhook_marks_order_paid_stock_sold_and_cash_ledger(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-1",
    )

    handled = handle_stripe_event(_completed_event(result["stripe_session_id"]))
    duplicate = handle_stripe_event(_completed_event(result["stripe_session_id"]))

    payment = CommercePayment.objects.get(company=company)
    order = InventoryOrderShell.objects.get(company=company)
    assert handled["status"] == "processed"
    assert duplicate["duplicate"] is True
    assert payment.status == "succeeded"
    assert order.status == "paid"
    assert InventoryStockUnit.objects.filter(product=product, status="sold").count() == 1
    assert CommerceCashLedgerEntry.objects.filter(company=company).count() == 1
    assert CommerceFulfillment.objects.filter(company=company, status="pending").count() == 1
    assert CommerceStripeEvent.objects.filter(stripe_event_id="evt_completed_1").count() == 1


def test_expired_webhook_releases_unpaid_reservation(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_expire")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-1",
    )

    handle_stripe_event(_expired_event(result["stripe_session_id"]))

    payment = CommercePayment.objects.get(company=company)
    order = InventoryOrderShell.objects.get(company=company)
    reservation.refresh_from_db()
    assert payment.status == "expired"
    assert order.status == "payment_expired"
    assert reservation.status == "expired"
    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 2


def test_expired_after_completed_does_not_release_sold_stock(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_paid_then_expired")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-1",
    )

    handle_stripe_event(_completed_event(result["stripe_session_id"], "evt_completed_paid"))
    expired = handle_stripe_event(_expired_event(result["stripe_session_id"], "evt_expired_stale"))

    assert expired["status"] == "ignored"
    assert InventoryOrderShell.objects.get(company=company).status == "paid"
    assert InventoryStockUnit.objects.filter(product=product, status="sold").count() == 1
    assert InventoryStockUnit.objects.filter(product=product, status="available").count() == 1


def test_completed_after_expired_with_unavailable_stock_requires_review(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company, quantity=1)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_late_completed")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-1",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-1",
    )
    handle_stripe_event(_expired_event(result["stripe_session_id"], "evt_expired_first"))
    InventoryStockUnit.objects.filter(product=product).update(status="sold")

    handle_stripe_event(_completed_event(result["stripe_session_id"], "evt_completed_late"))

    payment = CommercePayment.objects.get(company=company)
    order = InventoryOrderShell.objects.get(company=company)
    assert payment.status == "review_required"
    assert order.status == "payment_review_required"
    assert CommerceFulfillment.objects.get(company=company).status == "blocked"
    assert InventoryStockUnit.objects.filter(product=product, status="sold").count() == 1


def test_storefront_products_payload_exposes_safe_public_fields(user):
    company = _create_company(user, legacy=True)
    _create_product(company, quantity=1)

    payload = storefront_products_payload(company)

    product = payload["products"][0]
    assert product["sku"] == "SKU-1"
    assert product["available_units"] == 1
    assert "cost_mxn" not in product
    assert "notes" not in product


def test_public_order_status_payload_exposes_only_safe_fields(user, monkeypatch):
    company = _create_company(user, legacy=True)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_public_status")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-status",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-status",
    )
    handle_stripe_event(_completed_event(result["stripe_session_id"], "evt_status_completed"))
    order = InventoryOrderShell.objects.get(company=company)

    payload = public_order_status_payload(
        company_slug="legacy-glasswear",
        public_status_token=order.public_status_token,
    )

    assert payload is not None
    assert payload["order"]["reference"] == order.public_reference
    assert payload["order"]["payment_status"] == "succeeded"
    assert "stripe_session_id" not in str(payload)
    assert str(order.id) not in str(payload)


def test_fulfillment_transitions_and_overview_are_backend_owned(user, monkeypatch):
    company = _create_company(user)
    product = _create_product(company)
    _stripe_key(company, user)
    _patch_checkout(monkeypatch, session_id="cs_fulfillment")
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-fulfillment",
    )
    result = create_operator_checkout_session(
        company=company,
        actor=user,
        reservation_id=str(reservation.id),
        idempotency_key="checkout-fulfillment",
    )
    handle_stripe_event(_completed_event(result["stripe_session_id"], "evt_fulfillment"))
    order = InventoryOrderShell.objects.get(company=company)

    ready = transition_fulfillment(order=order, actor=user, action="mark-ready")
    shipped = transition_fulfillment(
        order=order,
        actor=user,
        action="ship",
        carrier="Local",
        tracking_number="TRACK-1",
    )
    note = add_order_operator_note(order=order, actor=user, note="Packed at counter.")
    overview = commerce_overview_payload(company)

    assert ready.status == "ready"
    assert shipped.status == "shipped"
    assert note.operator_note == "Packed at counter."
    assert overview["summary"]["orders_paid"] == 1
    assert overview["summary"]["fulfillment_shipped"] == 1
