"""Backend-owned commerce checkout and Stripe webhook services."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from application.services.inventory import (
    InventoryError,
    create_order_shell,
    create_reservation,
    inventory_order_shell_payload,
    inventory_reservation_payload,
)
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    CommerceCashLedgerEntry,
    CommerceFulfillment,
    CommerceFulfillmentEvent,
    CommercePayment,
    CommerceStorefrontProfile,
    CommerceStripeEvent,
    Graph,
    InventoryEvent,
    InventoryOrderShell,
    InventoryProduct,
    InventoryReservation,
    InventoryStockUnit,
    User,
)

try:
    import stripe
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    stripe = None  # type: ignore[assignment]

DEFAULT_STOREFRONT_CURRENCY = "mxn"


class CommerceError(ValueError):
    """Domain error for commerce commands."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def create_operator_checkout_session(
    *,
    company: Graph,
    actor: User,
    idempotency_key: str,
    reservation_id: str = "",
    order_shell_id: str = "",
) -> dict[str, Any]:
    """Create or replay a Stripe Checkout Session from an operator hold/order."""

    if not idempotency_key:
        raise CommerceError("idempotency_key_required", "Idempotency-Key is required.")
    existing = _payment_for_idempotency(company=company, idempotency_key=idempotency_key)
    if existing is not None and existing.checkout_url:
        return checkout_session_payload(existing)

    order = _resolve_operator_order(
        company=company,
        actor=actor,
        idempotency_key=idempotency_key,
        reservation_id=reservation_id,
        order_shell_id=order_shell_id,
    )
    payment = _ensure_payment_for_order(
        order=order,
        actor=actor,
        idempotency_key=idempotency_key,
        source="operator",
    )
    try:
        return _create_checkout_session_for_payment(payment=payment, source="operator")
    except Exception:
        _mark_checkout_creation_failed(payment=payment, reason="stripe_session_creation_failed")
        raise


def create_public_checkout_session(
    *,
    company: Graph,
    idempotency_key: str,
    product_id: str = "",
    sku: str = "",
    quantity: int = 1,
    buyer_alias: str = "",
) -> dict[str, Any]:
    """Reserve stock first, then create a Stripe Checkout Session for the storefront."""

    if not idempotency_key:
        raise CommerceError("idempotency_key_required", "Idempotency-Key is required.")
    existing = _payment_for_idempotency(company=company, idempotency_key=idempotency_key)
    if existing is not None and existing.checkout_url:
        return checkout_session_payload(existing)

    try:
        reservation = create_reservation(
            company=company,
            product_id=product_id,
            sku=sku,
            quantity=quantity,
            buyer_alias=buyer_alias,
            channel="storefront",
            note="Public storefront checkout hold.",
            actor=None,
            idempotency_key=f"storefront:{idempotency_key}",
        )
        order = create_order_shell(
            reservation=reservation,
            actor=None,
            idempotency_key=f"storefront-order:{idempotency_key}",
        )
    except InventoryError as exc:
        raise CommerceError(exc.code, exc.message) from exc

    payment = _ensure_payment_for_order(
        order=order,
        actor=None,
        idempotency_key=idempotency_key,
        source="storefront",
    )
    try:
        return _create_checkout_session_for_payment(payment=payment, source="storefront")
    except Exception:
        _mark_checkout_creation_failed(payment=payment, reason="stripe_session_creation_failed")
        raise


def storefront_products_payload(company: Graph) -> dict[str, Any]:
    """Return public-safe product inventory for a storefront listing."""

    profile = storefront_profile_for_company(company)
    products = list(
        InventoryProduct.objects.filter(company=company, status="active")
        .annotate(
            available_units=Count(
                "stock_units",
                filter=Q(stock_units__status="available"),
            )
        )
        .order_by("model", "sku")
    )
    return {
        "company_id": str(company.id),
        "company_slug": profile.slug if profile is not None else slug_for_company(company),
        "storefront_display_name": profile.display_name if profile is not None else company.name,
        "currency": (profile.currency if profile is not None else DEFAULT_STOREFRONT_CURRENCY),
        "products": [
            {
                "id": str(product.id),
                "sku": product.sku,
                "model": product.model,
                "name": product.name,
                "variant": product.variant,
                "color": product.color,
                "photo_url": product.photo_url,
                "price_amount": str(_product_price_amount(product)),
                "price_mxn": str(product.price_mxn),
                "currency": product.currency or DEFAULT_STOREFRONT_CURRENCY,
                "anchor_model": product.anchor_model,
                "scarcity_tag": product.scarcity_tag,
                "available_units": int(getattr(product, "available_units", 0) or 0),
                "sold_out": int(getattr(product, "available_units", 0) or 0) < 1,
            }
            for product in products
        ],
    }


def ensure_storefront_profile(
    *,
    company: Graph,
    slug: str | None = None,
    display_name: str | None = None,
    enabled: bool = True,
    currency: str = DEFAULT_STOREFRONT_CURRENCY,
    stripe_credential: APIKey | None = None,
    metadata: dict[str, Any] | None = None,
) -> CommerceStorefrontProfile:
    """Create or update the backend-owned storefront profile for a company."""

    selected_slug = _slugify(slug or company.name)
    selected_currency = str(currency or DEFAULT_STOREFRONT_CURRENCY).strip().lower()[:8]
    defaults = {
        "organization": company.organization,
        "slug": selected_slug,
        "display_name": (display_name or company.name).strip()[:255],
        "enabled": enabled,
        "currency": selected_currency,
        "stripe_credential": stripe_credential,
        "metadata_json": metadata or {},
    }
    profile, _ = CommerceStorefrontProfile.objects.update_or_create(
        company=company,
        defaults=defaults,
    )
    return profile


def storefront_profile_for_company(company: Graph) -> CommerceStorefrontProfile | None:
    return (
        CommerceStorefrontProfile.objects.select_related("stripe_credential")
        .filter(company=company)
        .first()
    )


def company_for_storefront_slug(company_slug: str) -> Graph | None:
    slug = _slugify(company_slug)
    profile = (
        CommerceStorefrontProfile.objects.select_related("company", "company__organization")
        .filter(slug=slug, enabled=True)
        .first()
    )
    if profile is not None:
        return profile.company
    for company in Graph.objects.select_related("organization").all().order_by("created_at"):
        if slug_for_company(company) == slug:
            return cast(Graph, company)
    return None


def slug_for_company(company: Graph) -> str:
    profile = storefront_profile_for_company(company)
    if profile is not None:
        return profile.slug
    return _slugify(company.name)


def handle_stripe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply a verified Stripe webhook event exactly once."""

    event_id = str(_object_get(event, "id") or "").strip()
    event_type = str(_object_get(event, "type") or "").strip()
    if not event_id:
        raise CommerceError("invalid_stripe_event", "Stripe event is missing id.")

    existing = CommerceStripeEvent.objects.filter(stripe_event_id=event_id).first()
    if existing is not None:
        return {
            "event_id": existing.stripe_event_id,
            "event_type": existing.event_type,
            "status": existing.status,
            "duplicate": True,
        }

    data_object = _object_to_dict(_nested_get(event, "data", "object") or {})
    session_id = str(data_object.get("id") or "")
    payment = (
        CommercePayment.objects.select_related("organization", "company")
        .filter(stripe_session_id=session_id)
        .first()
        if session_id
        else None
    )

    status = "ignored"
    error_message = ""
    try:
        if event_type == "checkout.session.completed":
            if payment is None:
                error_message = "Checkout session was not found in backend commerce payments."
            else:
                status = _mark_checkout_completed(
                    payment=payment,
                    session=data_object,
                    event_id=event_id,
                )
        elif event_type == "checkout.session.expired":
            if payment is None:
                error_message = "Checkout session was not found in backend commerce payments."
            else:
                status = _mark_checkout_expired(
                    payment=payment,
                    session=data_object,
                    event_id=event_id,
                )
    except Exception as exc:
        CommerceStripeEvent.objects.create(
            organization=payment.organization if payment is not None else None,
            company=payment.company if payment is not None else None,
            stripe_event_id=event_id,
            event_type=event_type,
            status="failed",
            payload_json=_json_safe(event),
            error_message=str(exc)[:1000],
            processed_at=timezone.now(),
        )
        raise

    record = CommerceStripeEvent.objects.create(
        organization=payment.organization if payment is not None else None,
        company=payment.company if payment is not None else None,
        stripe_event_id=event_id,
        event_type=event_type,
        status=status,
        payload_json=_json_safe(event),
        error_message=error_message,
        processed_at=timezone.now(),
    )
    return {
        "event_id": record.stripe_event_id,
        "event_type": record.event_type,
        "status": record.status,
        "duplicate": False,
    }


def checkout_session_payload(payment: CommercePayment) -> dict[str, Any]:
    payment = (
        CommercePayment.objects.select_related("order", "reservation", "product", "company")
        .filter(id=payment.id)
        .first()
        or payment
    )
    return {
        "checkout_url": payment.checkout_url,
        "stripe_session_id": payment.stripe_session_id,
        "payment": commerce_payment_payload(payment),
        "order_shell": inventory_order_shell_payload(payment.order),
        "reservation": inventory_reservation_payload(payment.reservation),
    }


def commerce_payment_payload(payment: CommercePayment) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "company_id": str(payment.company_id),
        "reservation_id": str(payment.reservation_id),
        "order_id": str(payment.order_id),
        "product_id": str(payment.product_id),
        "provider": payment.provider,
        "status": payment.status,
        "amount_mxn": str(payment.amount_mxn),
        "currency": payment.currency,
        "quantity": payment.quantity,
        "stripe_session_id": payment.stripe_session_id,
        "stripe_payment_intent_id": payment.stripe_payment_intent_id,
        "checkout_url": payment.checkout_url,
        "latest_event_id": payment.latest_event_id,
        "customer_email": payment.customer_email,
        "customer_name": payment.customer_name,
        "error_message": payment.error_message,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "expired_at": payment.expired_at.isoformat() if payment.expired_at else None,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
    }


def commerce_overview_payload(company: Graph) -> dict[str, Any]:
    """Return operator-facing commerce operations summary for a company."""

    orders = InventoryOrderShell.objects.filter(company=company)
    payments = CommercePayment.objects.filter(company=company)
    fulfillments = CommerceFulfillment.objects.filter(company=company)
    cash_total = CommerceCashLedgerEntry.objects.filter(
        company=company, entry_type="sale"
    ).values_list("amount_mxn", flat=True)
    revenue_mxn = sum((Decimal(amount) for amount in cash_total), Decimal("0.00"))
    stuck_statuses = {"payment_review_required", "payment_expired", "cancelled"}
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "storefront": storefront_profile_payload(storefront_profile_for_company(company)),
        "summary": {
            "orders_total": orders.count(),
            "orders_paid": orders.filter(status="paid").count(),
            "orders_pending_payment": orders.filter(status="pending_payment").count(),
            "orders_stuck": orders.filter(status__in=stuck_statuses).count(),
            "payments_succeeded": payments.filter(status="succeeded").count(),
            "payments_review_required": payments.filter(status="review_required").count(),
            "fulfillment_pending": fulfillments.filter(status="pending").count(),
            "fulfillment_ready": fulfillments.filter(status="ready").count(),
            "fulfillment_blocked": fulfillments.filter(status="blocked").count(),
            "fulfillment_shipped": fulfillments.filter(status="shipped").count(),
            "fulfillment_delivered": fulfillments.filter(status="delivered").count(),
            "cash_sales_mxn": str(revenue_mxn.quantize(Decimal("0.01"))),
        },
        "stuck_orders": [
            commerce_order_payload(order)
            for order in _commerce_orders_queryset(company).filter(status__in=stuck_statuses)[:10]
        ],
        "recent_orders": [
            commerce_order_payload(order) for order in _commerce_orders_queryset(company)[:10]
        ],
        "fulfillment_events": [
            fulfillment_event_payload(event)
            for event in CommerceFulfillmentEvent.objects.filter(company=company)
            .select_related("fulfillment", "order", "actor_user")
            .order_by("-created_at")[:20]
        ],
    }


def commerce_orders_payload(company: Graph) -> dict[str, Any]:
    return {
        "company_id": str(company.id),
        "orders": [commerce_order_payload(order) for order in _commerce_orders_queryset(company)],
    }


def commerce_order_payload(order: InventoryOrderShell) -> dict[str, Any]:
    payment = getattr(order, "commerce_payment", None)
    fulfillment = getattr(order, "commerce_fulfillment", None)
    reservation = order.reservation
    product = reservation.product
    return {
        "id": str(order.id),
        "company_id": str(order.company_id),
        "order_number": order.order_number,
        "public_reference": order.public_reference,
        "status": order.status,
        "product": {
            "id": str(product.id),
            "sku": product.sku,
            "model": product.model,
            "name": product.name,
            "photo_url": product.photo_url,
        },
        "quantity": reservation.quantity,
        "buyer_alias": reservation.buyer_alias,
        "channel": reservation.channel,
        "payment": commerce_payment_payload(payment) if payment is not None else None,
        "fulfillment": fulfillment_payload(fulfillment) if fulfillment is not None else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "payment_expired_at": order.payment_expired_at.isoformat()
        if order.payment_expired_at
        else None,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def public_order_status_payload(
    *, company_slug: str, public_status_token: str
) -> dict[str, Any] | None:
    company = company_for_storefront_slug(company_slug)
    if company is None:
        return None
    order = (
        _commerce_orders_queryset(company)
        .filter(public_status_token=public_status_token.strip())
        .first()
    )
    if order is None:
        return None
    profile = storefront_profile_for_company(company)
    payment = getattr(order, "commerce_payment", None)
    fulfillment = getattr(order, "commerce_fulfillment", None)
    product = order.reservation.product
    return {
        "storefront": public_storefront_profile_payload(profile, fallback_company=company),
        "order": {
            "reference": order.public_reference or order.order_number,
            "status": order.status,
            "payment_status": payment.status if payment is not None else "pending",
            "fulfillment_status": fulfillment.status if fulfillment is not None else "not_ready",
            "item": {
                "sku": product.sku,
                "model": product.model,
                "name": product.name,
                "quantity": order.reservation.quantity,
            },
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "updated_at": order.updated_at.isoformat(),
        },
    }


def storefront_profile_payload(profile: CommerceStorefrontProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "id": str(profile.id),
        "company_id": str(profile.company_id),
        "slug": profile.slug,
        "display_name": profile.display_name,
        "enabled": profile.enabled,
        "currency": profile.currency,
    }


def public_storefront_profile_payload(
    profile: CommerceStorefrontProfile | None, *, fallback_company: Graph | None = None
) -> dict[str, Any] | None:
    if profile is None and fallback_company is None:
        return None
    company = (
        fallback_company
        if fallback_company is not None
        else cast(CommerceStorefrontProfile, profile).company
    )
    return {
        "slug": profile.slug if profile is not None else slug_for_company(company),
        "display_name": profile.display_name if profile is not None else company.name,
        "currency": profile.currency if profile is not None else DEFAULT_STOREFRONT_CURRENCY,
    }


def fulfillment_payload(fulfillment: CommerceFulfillment | None) -> dict[str, Any] | None:
    if fulfillment is None:
        return None
    return {
        "id": str(fulfillment.id),
        "order_id": str(fulfillment.order_id),
        "payment_id": str(fulfillment.payment_id),
        "reservation_id": str(fulfillment.reservation_id),
        "status": fulfillment.status,
        "reason_code": fulfillment.reason_code,
        "operator_note": fulfillment.operator_note,
        "carrier": fulfillment.carrier,
        "tracking_number": fulfillment.tracking_number,
        "tracking_url": fulfillment.tracking_url,
        "shipped_at": fulfillment.shipped_at.isoformat() if fulfillment.shipped_at else None,
        "delivered_at": fulfillment.delivered_at.isoformat() if fulfillment.delivered_at else None,
        "created_at": fulfillment.created_at.isoformat(),
        "updated_at": fulfillment.updated_at.isoformat(),
    }


def fulfillment_event_payload(event: CommerceFulfillmentEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "fulfillment_id": str(event.fulfillment_id),
        "order_id": str(event.order_id),
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "event_type": event.event_type,
        "status_from": event.status_from,
        "status_to": event.status_to,
        "message": event.message,
        "metadata": event.metadata_json,
        "created_at": event.created_at.isoformat(),
    }


def transition_fulfillment(
    *,
    order: InventoryOrderShell,
    actor: User,
    action: str,
    note: str = "",
    reason_code: str = "",
    carrier: str = "",
    tracking_number: str = "",
    tracking_url: str = "",
) -> CommerceFulfillment:
    fulfillment = _fulfillment_for_order(order)
    if fulfillment is None:
        raise CommerceError("fulfillment_not_found", "Fulfillment was not found for this order.")
    action = action.strip().lower()
    transitions = {
        "block": "blocked",
        "mark-ready": "ready",
        "ship": "shipped",
        "deliver": "delivered",
    }
    if action not in transitions:
        raise CommerceError("invalid_fulfillment_action", "Fulfillment action is not supported.")
    target = transitions[action]
    allowed = {
        "pending": {"ready", "blocked"},
        "ready": {"blocked", "shipped"},
        "blocked": {"ready"},
        "shipped": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }
    if target not in allowed.get(fulfillment.status, set()):
        raise CommerceError(
            "invalid_fulfillment_transition",
            f"Fulfillment cannot move from {fulfillment.status} to {target}.",
        )
    with transaction.atomic():
        fulfillment = CommerceFulfillment.objects.select_for_update().get(id=fulfillment.id)
        before = fulfillment.status
        fulfillment.status = target
        if note:
            fulfillment.operator_note = _safe_operator_text(note, limit=1000)
        if reason_code:
            fulfillment.reason_code = _safe_operator_text(reason_code, limit=64)
        if target == "shipped":
            fulfillment.carrier = _safe_operator_text(carrier, limit=120)
            fulfillment.tracking_number = _safe_operator_text(tracking_number, limit=120)
            fulfillment.tracking_url = _safe_operator_text(tracking_url, limit=1024)
            fulfillment.shipped_at = timezone.now()
        if target == "delivered":
            fulfillment.delivered_at = timezone.now()
        fulfillment.save()
        CommerceFulfillmentEvent.objects.create(
            organization=fulfillment.organization,
            company=fulfillment.company,
            fulfillment=fulfillment,
            order=fulfillment.order,
            actor_user=actor,
            event_type=target,
            status_from=before,
            status_to=target,
            message=_safe_operator_text(note, limit=512) or f"Fulfillment marked {target}.",
            metadata_json={
                "reason_code": fulfillment.reason_code,
                "carrier": fulfillment.carrier,
                "tracking_present": bool(fulfillment.tracking_number or fulfillment.tracking_url),
            },
        )
        return fulfillment


def add_order_operator_note(
    *, order: InventoryOrderShell, actor: User, note: str
) -> CommerceFulfillment:
    fulfillment = _fulfillment_for_order(order)
    if fulfillment is None:
        raise CommerceError("fulfillment_not_found", "Fulfillment was not found for this order.")
    sanitized = _safe_operator_text(note, limit=1000)
    fulfillment.operator_note = sanitized
    fulfillment.save(update_fields=["operator_note", "updated_at"])
    CommerceFulfillmentEvent.objects.create(
        organization=fulfillment.organization,
        company=fulfillment.company,
        fulfillment=fulfillment,
        order=fulfillment.order,
        actor_user=actor,
        event_type="note",
        status_from=fulfillment.status,
        status_to=fulfillment.status,
        message=sanitized[:512],
        metadata_json={},
    )
    return fulfillment


def safe_json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _resolve_operator_order(
    *,
    company: Graph,
    actor: User,
    idempotency_key: str,
    reservation_id: str = "",
    order_shell_id: str = "",
) -> InventoryOrderShell:
    if bool(reservation_id) == bool(order_shell_id):
        raise CommerceError(
            "checkout_source_required",
            "Provide exactly one of reservation_id or order_shell_id.",
        )
    if order_shell_id:
        order = (
            InventoryOrderShell.objects.select_related(
                "reservation", "reservation__product", "company"
            )
            .filter(company=company, id=order_shell_id)
            .first()
        )
        if order is None:
            raise CommerceError("order_not_found", "Order shell was not found.")
        return order

    reservation = (
        InventoryReservation.objects.select_related("company", "product")
        .filter(company=company, id=reservation_id)
        .first()
    )
    if reservation is None:
        raise CommerceError("reservation_not_found", "Reservation was not found.")
    try:
        return create_order_shell(
            reservation=reservation,
            actor=actor,
            idempotency_key=f"checkout-order:{idempotency_key}",
        )
    except InventoryError as exc:
        if exc.code == "reservation_not_active" and reservation.status == "converted":
            order = InventoryOrderShell.objects.filter(reservation=reservation).first()
            if order is not None:
                return order
        raise CommerceError(exc.code, exc.message) from exc


def _ensure_payment_for_order(
    *,
    order: InventoryOrderShell,
    actor: User | None,
    idempotency_key: str,
    source: str,
) -> CommercePayment:
    order = (
        InventoryOrderShell.objects.select_related(
            "organization",
            "company",
            "reservation",
            "reservation__product",
        )
        .filter(id=order.id)
        .first()
        or order
    )
    if order.status in {"paid", "payment_expired", "cancelled", "payment_review_required"}:
        raise CommerceError(
            "order_not_payable",
            f"Checkout cannot be created for order status {order.status}.",
        )
    reservation = order.reservation
    if reservation.status != "converted":
        raise CommerceError(
            "reservation_not_converted",
            f"Checkout requires a converted reservation, got {reservation.status}.",
        )
    _ensure_public_order_identity(order)
    amount_mxn = (
        _product_price_amount(reservation.product) * Decimal(reservation.quantity)
    ).quantize(Decimal("0.01"))
    payment, _ = CommercePayment.objects.get_or_create(
        order=order,
        defaults={
            "organization": order.organization,
            "company": order.company,
            "reservation": reservation,
            "product": reservation.product,
            "requested_by": actor,
            "status": "pending",
            "amount_mxn": amount_mxn,
            "currency": "mxn",
            "quantity": reservation.quantity,
            "idempotency_key": idempotency_key,
            "metadata_json": {"source": source},
        },
    )
    if payment.idempotency_key and payment.idempotency_key != idempotency_key:
        raise CommerceError("payment_exists", "Order already has a payment command.")
    if not payment.idempotency_key:
        payment.idempotency_key = idempotency_key
        payment.save(update_fields=["idempotency_key", "updated_at"])
    return payment


def _create_checkout_session_for_payment(
    *,
    payment: CommercePayment,
    source: str,
) -> dict[str, Any]:
    payment = (
        CommercePayment.objects.select_related("company", "organization", "order", "product")
        .filter(id=payment.id)
        .first()
        or payment
    )
    if payment.checkout_url:
        return checkout_session_payload(payment)
    if stripe is None:  # pragma: no cover - dependency guard
        raise CommerceError("stripe_sdk_missing", "Stripe SDK is not installed.")

    profile = storefront_profile_for_company(payment.company)
    credential = _stripe_credential_for_company(payment.company, profile=profile)
    stripe.api_key = decrypt_api_key(bytes(credential.encrypted_key))
    amount_cents = _mxn_cents(payment.amount_mxn)
    currency = (profile.currency if profile is not None else payment.currency).lower()
    product_label = payment.product.name or payment.product.model or payment.product.sku
    order = _ensure_public_order_identity(payment.order)
    storefront_slug = profile.slug if profile is not None else slug_for_company(payment.company)
    checkout_session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {
                        "name": product_label,
                        "metadata": {
                            "company_id": str(payment.company_id),
                            "product_id": str(payment.product_id),
                            "sku": payment.product.sku,
                        },
                    },
                    "unit_amount": amount_cents // max(1, payment.quantity),
                },
                "quantity": payment.quantity,
            }
        ],
        success_url=(
            f"{_frontend_url()}/storefront/{storefront_slug}"
            f"?status=success&order={order.public_status_token}"
            "&session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{_frontend_url()}/storefront/{storefront_slug}?status=canceled",
        customer_creation="if_required",
        billing_address_collection="auto",
        shipping_address_collection={"allowed_countries": ["MX"]},
        client_reference_id=str(payment.order_id),
        metadata={
            "company_id": str(payment.company_id),
            "order_id": str(payment.order_id),
            "reservation_id": str(payment.reservation_id),
            "payment_id": str(payment.id),
            "source": source,
            "public_reference": order.public_reference,
        },
        idempotency_key=payment.idempotency_key or str(payment.id),
    )
    session_id = str(_object_get(checkout_session, "id") or "")
    checkout_url = str(_object_get(checkout_session, "url") or "")
    if not session_id or not checkout_url:
        raise CommerceError("stripe_session_invalid", "Stripe did not return a checkout URL.")

    payment.stripe_session_id = session_id
    payment.checkout_url = checkout_url
    payment.status = "pending"
    payment.save(
        update_fields=[
            "stripe_session_id",
            "checkout_url",
            "status",
            "updated_at",
        ]
    )
    order = payment.order
    _ensure_public_order_identity(order)
    order.stripe_session_id = session_id
    order.stripe_checkout_url = checkout_url
    order.status = "pending_payment"
    order.save(
        update_fields=[
            "stripe_session_id",
            "stripe_checkout_url",
            "status",
            "updated_at",
        ]
    )
    return checkout_session_payload(payment)


def _mark_checkout_completed(
    *,
    payment: CommercePayment,
    session: dict[str, Any],
    event_id: str,
) -> str:
    with transaction.atomic():
        payment = (
            CommercePayment.objects.select_for_update()
            .select_related("organization", "company", "order", "reservation", "product")
            .get(id=payment.id)
        )
        order = (
            InventoryOrderShell.objects.select_for_update()
            .select_related("reservation", "reservation__product")
            .get(id=payment.order_id)
        )
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("product", "company")
            .get(id=payment.reservation_id)
        )
        if payment.status == "succeeded" and order.status == "paid":
            _append_processed_event(payment, event_id)
            return "ignored"

        reserved_units = list(
            InventoryStockUnit.objects.select_for_update()
            .filter(current_reservation=reservation, status="reserved")
            .order_by("unit_number")
        )
        if len(reserved_units) != payment.quantity:
            _mark_payment_review_required(
                payment=payment,
                order=order,
                reservation=reservation,
                event_id=event_id,
                reason=(
                    "Paid checkout completed after reservation stock was no longer reserved. "
                    "Operator review is required."
                ),
            )
            return "processed"

        paid_at = _event_time(session) or timezone.now()
        InventoryStockUnit.objects.filter(id__in=[unit.id for unit in reserved_units]).update(
            status="sold",
            updated_at=timezone.now(),
        )
        customer = _customer_details(session)
        shipping = _shipping_details(session)
        payment.status = "succeeded"
        payment.stripe_payment_intent_id = str(session.get("payment_intent") or "")
        payment.customer_email = customer.get("email", "")
        payment.customer_name = customer.get("name", "")
        payment.shipping_json = shipping
        payment.paid_at = paid_at
        payment.latest_event_id = event_id
        _append_processed_event(payment, event_id, save=False)
        payment.save(
            update_fields=[
                "status",
                "stripe_payment_intent_id",
                "customer_email",
                "customer_name",
                "shipping_json",
                "paid_at",
                "latest_event_id",
                "processed_event_ids",
                "updated_at",
            ]
        )
        order.status = "paid"
        _ensure_public_order_identity(order)
        order.stripe_payment_intent_id = payment.stripe_payment_intent_id
        order.customer_email = payment.customer_email
        order.customer_name = payment.customer_name
        order.shipping_json = shipping
        order.paid_at = paid_at
        order.save(
            update_fields=[
                "status",
                "stripe_payment_intent_id",
                "customer_email",
                "customer_name",
                "shipping_json",
                "paid_at",
                "updated_at",
            ]
        )
        CommerceCashLedgerEntry.objects.get_or_create(
            payment=payment,
            defaults={
                "organization": payment.organization,
                "company": payment.company,
                "order": order,
                "entry_type": "sale",
                "amount_mxn": payment.amount_mxn,
                "currency": payment.currency,
                "idempotency_key": f"stripe:{event_id}:sale",
                "occurred_at": paid_at,
                "metadata_json": {
                    "stripe_session_id": payment.stripe_session_id,
                    "stripe_payment_intent_id": payment.stripe_payment_intent_id,
                },
            },
        )
        _ensure_fulfillment(
            payment=payment,
            order=order,
            reservation=reservation,
            status="pending",
            event_id=event_id,
            message="Payment completed; fulfillment is pending operator handling.",
        )
        InventoryEvent.objects.create(
            organization=payment.organization,
            company=payment.company,
            product=payment.product,
            reservation=reservation,
            order=order,
            event_type="sell",
            quantity_delta=-payment.quantity,
            message=f"Stripe checkout paid for {payment.quantity} unit(s) of {payment.product.sku}.",
            metadata_json={
                "stripe_event_id": event_id,
                "stripe_session_id": payment.stripe_session_id,
                "payment_id": str(payment.id),
            },
        )
        return "processed"


def _mark_checkout_expired(
    *,
    payment: CommercePayment,
    session: dict[str, Any],
    event_id: str,
) -> str:
    with transaction.atomic():
        payment = (
            CommercePayment.objects.select_for_update()
            .select_related("organization", "company", "order", "reservation", "product")
            .get(id=payment.id)
        )
        order = InventoryOrderShell.objects.select_for_update().get(id=payment.order_id)
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("product")
            .get(id=payment.reservation_id)
        )
        if payment.status == "succeeded" or order.status == "paid":
            _append_processed_event(payment, event_id)
            return "ignored"
        if payment.status == "expired" and order.status == "payment_expired":
            _append_processed_event(payment, event_id)
            return "ignored"

        released = _release_reserved_units(reservation)
        expired_at = _event_time(session) or timezone.now()
        reservation.status = "expired"
        reservation.released_at = expired_at
        reservation.save(update_fields=["status", "released_at", "updated_at"])
        payment.status = "expired"
        payment.expired_at = expired_at
        payment.latest_event_id = event_id
        _append_processed_event(payment, event_id, save=False)
        payment.save(
            update_fields=[
                "status",
                "expired_at",
                "latest_event_id",
                "processed_event_ids",
                "updated_at",
            ]
        )
        order.status = "payment_expired"
        order.payment_expired_at = expired_at
        order.save(update_fields=["status", "payment_expired_at", "updated_at"])
        InventoryEvent.objects.create(
            organization=payment.organization,
            company=payment.company,
            product=payment.product,
            reservation=reservation,
            order=order,
            event_type="payment_expire",
            quantity_delta=released,
            message=f"Stripe checkout expired and released {released} unit(s).",
            metadata_json={
                "stripe_event_id": event_id,
                "stripe_session_id": payment.stripe_session_id,
                "payment_id": str(payment.id),
            },
        )
        return "processed"


def _mark_checkout_creation_failed(*, payment: CommercePayment, reason: str) -> None:
    with transaction.atomic():
        payment = (
            CommercePayment.objects.select_for_update()
            .select_related("order", "reservation", "product")
            .get(id=payment.id)
        )
        order = InventoryOrderShell.objects.select_for_update().get(id=payment.order_id)
        reservation = InventoryReservation.objects.select_for_update().get(
            id=payment.reservation_id
        )
        released = _release_reserved_units(reservation)
        reservation.status = "released"
        reservation.released_at = timezone.now()
        reservation.save(update_fields=["status", "released_at", "updated_at"])
        payment.status = "failed"
        payment.error_message = reason
        payment.save(update_fields=["status", "error_message", "updated_at"])
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
        InventoryEvent.objects.create(
            organization=payment.organization,
            company=payment.company,
            product=payment.product,
            reservation=reservation,
            order=order,
            event_type="release",
            quantity_delta=released,
            message="Checkout creation failed; reservation released.",
            metadata_json={"reason": reason},
        )


def _mark_payment_review_required(
    *,
    payment: CommercePayment,
    order: InventoryOrderShell,
    reservation: InventoryReservation,
    event_id: str,
    reason: str,
) -> None:
    payment.status = "review_required"
    payment.error_message = reason
    payment.latest_event_id = event_id
    _append_processed_event(payment, event_id, save=False)
    payment.save(
        update_fields=[
            "status",
            "error_message",
            "latest_event_id",
            "processed_event_ids",
            "updated_at",
        ]
    )
    order.status = "payment_review_required"
    order.save(update_fields=["status", "updated_at"])
    _ensure_fulfillment(
        payment=payment,
        order=order,
        reservation=reservation,
        status="blocked",
        event_id=event_id,
        reason_code="payment_review_required",
        message="Paid checkout requires operator review before fulfillment.",
    )
    InventoryEvent.objects.create(
        organization=payment.organization,
        company=payment.company,
        product=payment.product,
        reservation=reservation,
        order=order,
        event_type="payment_review",
        quantity_delta=0,
        message="Paid Stripe checkout requires operator review before stock changes.",
        metadata_json={
            "stripe_event_id": event_id,
            "stripe_session_id": payment.stripe_session_id,
            "payment_id": str(payment.id),
            "reason": reason,
        },
    )


def _release_reserved_units(reservation: InventoryReservation) -> int:
    return int(
        InventoryStockUnit.objects.select_for_update()
        .filter(current_reservation=reservation, status="reserved")
        .update(status="available", current_reservation=None, updated_at=timezone.now())
    )


def _payment_for_idempotency(
    *,
    company: Graph,
    idempotency_key: str,
) -> CommercePayment | None:
    if not idempotency_key:
        return None
    return (
        CommercePayment.objects.select_related("order", "reservation", "product")
        .filter(company=company, idempotency_key=idempotency_key)
        .first()
    )


def _stripe_credential_for_company(
    company: Graph, *, profile: CommerceStorefrontProfile | None = None
) -> APIKey:
    credential = profile.stripe_credential if profile is not None else None
    if credential is None:
        credential = (
            APIKey.objects.filter(organization=company.organization, provider="stripe")
            .order_by("-created_at")
            .first()
        )
    if credential is None:
        raise CommerceError(
            "stripe_credential_missing",
            "Stripe commerce credential is not configured for this organization.",
        )
    if (credential.token_metadata or {}).get("revoked") is True:
        raise CommerceError("stripe_credential_revoked", "Stripe commerce credential is revoked.")
    return credential


def _commerce_orders_queryset(company: Graph) -> Any:
    return (
        InventoryOrderShell.objects.filter(company=company)
        .select_related(
            "company",
            "reservation",
            "reservation__product",
            "commerce_payment",
            "commerce_fulfillment",
        )
        .order_by("-created_at")
    )


def _fulfillment_for_order(order: InventoryOrderShell) -> CommerceFulfillment | None:
    return (
        CommerceFulfillment.objects.select_related("order", "payment", "reservation", "company")
        .filter(order=order)
        .first()
    )


def _ensure_fulfillment(
    *,
    payment: CommercePayment,
    order: InventoryOrderShell,
    reservation: InventoryReservation,
    status: str,
    event_id: str,
    message: str,
    reason_code: str = "",
) -> CommerceFulfillment:
    fulfillment, created = CommerceFulfillment.objects.get_or_create(
        order=order,
        defaults={
            "organization": payment.organization,
            "company": payment.company,
            "payment": payment,
            "reservation": reservation,
            "status": status,
            "reason_code": reason_code,
        },
    )
    if not created and fulfillment.status != status and status == "blocked":
        before = fulfillment.status
        fulfillment.status = status
        fulfillment.reason_code = reason_code
        fulfillment.save(update_fields=["status", "reason_code", "updated_at"])
    else:
        before = "" if created else fulfillment.status
    if created or status == "blocked":
        CommerceFulfillmentEvent.objects.create(
            organization=payment.organization,
            company=payment.company,
            fulfillment=fulfillment,
            order=order,
            event_type="created" if created else status,
            status_from=before,
            status_to=fulfillment.status,
            message=message[:512],
            metadata_json={"stripe_event_id": event_id, "reason_code": reason_code},
        )
    return fulfillment


def _ensure_public_order_identity(order: InventoryOrderShell) -> InventoryOrderShell:
    updates: list[str] = []
    if not order.public_reference:
        order.public_reference = order.order_number
        updates.append("public_reference")
    if not order.public_status_token:
        order.public_status_token = secrets.token_urlsafe(32)
        updates.append("public_status_token")
    if updates:
        updates.append("updated_at")
        order.save(update_fields=updates)
    return order


def _product_price_amount(product: InventoryProduct) -> Decimal:
    amount = product.price_amount or product.price_mxn
    return Decimal(amount).quantize(Decimal("0.01"))


def _safe_operator_text(value: str, *, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _append_processed_event(payment: CommercePayment, event_id: str, *, save: bool = True) -> None:
    processed = list(payment.processed_event_ids or [])
    if event_id not in processed:
        processed.append(event_id)
        payment.processed_event_ids = processed
        if save:
            payment.save(update_fields=["processed_event_ids", "updated_at"])


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _mxn_cents(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1")))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "company"


def _object_get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _nested_get(obj: Any, *keys: str) -> Any:
    current = obj
    for key in keys:
        current = _object_get(current, key)
        if current is None:
            return None
    return current


def _object_to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return dict(obj.to_dict_recursive())
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    return dict(getattr(obj, "__dict__", {}) or {})


def _json_safe(value: Any) -> dict[str, Any]:
    if not isinstance(value, (dict, list, tuple, str, int, float, bool, type(None))):
        value = _object_to_dict(value)
    safe = json.loads(json.dumps(value, default=str))
    if isinstance(safe, dict):
        return safe
    return {"value": safe}


def _event_time(session: dict[str, Any]) -> datetime | None:
    value = session.get("created")
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        return None


def _customer_details(session: dict[str, Any]) -> dict[str, str]:
    details = session.get("customer_details") or {}
    if not isinstance(details, dict):
        details = _object_to_dict(details)
    return {
        "email": str(details.get("email") or "")[:255],
        "name": str(details.get("name") or "")[:255],
    }


def _shipping_details(session: dict[str, Any]) -> dict[str, Any]:
    details = session.get("customer_details") or {}
    if not isinstance(details, dict):
        details = _object_to_dict(details)
    shipping = details.get("address") or session.get("shipping_details") or {}
    return _json_safe(shipping) if isinstance(shipping, dict) else {}
