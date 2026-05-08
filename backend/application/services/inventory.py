"""Backend-owned company inventory and reservation services."""

from __future__ import annotations

import csv
import re
import secrets
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from application.services.stock_state import (
    stock_state_for_product,
    stock_state_summary_for_products,
)
from infrastructure.orm.models import (
    Graph,
    InventoryEvent,
    InventoryOrderShell,
    InventoryProduct,
    InventoryReservation,
    InventoryStockUnit,
    Organization,
    User,
)

DEFAULT_RESERVATION_EXPIRY_MINUTES = 30
DEFAULT_INVENTORY_CSV = Path("docs/legacy-ultimate-test/Análisis costos.csv")
RESERVATION_STATUSES = {"active", "expired", "released", "converted"}
STOCK_STATUSES = {"available", "reserved", "sold", "removed"}


class InventoryError(ValueError):
    """Domain error for inventory commands."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class InventoryImportRowResult:
    sku: str
    model: str
    desired_quantity: int
    created_product: bool
    created_units: int
    removed_units: int
    active_units: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class InventoryImportResult:
    csv_path: str
    company_id: str
    products_seen: int = 0
    products_created: int = 0
    products_updated: int = 0
    stock_units_created: int = 0
    stock_units_removed: int = 0
    total_active_units: int = 0
    rows: list[InventoryImportRowResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "csv_path": self.csv_path,
            "company_id": self.company_id,
            "products_seen": self.products_seen,
            "products_created": self.products_created,
            "products_updated": self.products_updated,
            "stock_units_created": self.stock_units_created,
            "stock_units_removed": self.stock_units_removed,
            "total_active_units": self.total_active_units,
            "warnings": self.warnings,
            "rows": [
                {
                    "sku": row.sku,
                    "model": row.model,
                    "desired_quantity": row.desired_quantity,
                    "created_product": row.created_product,
                    "created_units": row.created_units,
                    "removed_units": row.removed_units,
                    "active_units": row.active_units,
                    "warnings": row.warnings,
                }
                for row in self.rows
            ],
        }


def import_inventory_csv(
    *,
    company: Graph,
    csv_path: str | Path = DEFAULT_INVENTORY_CSV,
    actor: User | None = None,
    source: str = "csv_import",
    anchor_models: set[str] | None = None,
    currency: str = "mxn",
) -> InventoryImportResult:
    """Import a product/SKU CSV into backend-owned inventory units."""

    organization = _organization_for_company(company)
    resolved_path = _resolve_repo_path(csv_path)
    rows = _parse_inventory_csv(resolved_path)
    duplicate_sku_counts = _duplicate_sku_counts(rows)
    result = InventoryImportResult(csv_path=str(resolved_path), company_id=str(company.id))

    with transaction.atomic():
        for row in rows:
            raw_sku = _required_text(row, "sku")
            sku = _product_sku(raw_sku, row=row, duplicate_sku_counts=duplicate_sku_counts)
            model = row.get("model") or row.get("name") or sku
            desired_quantity = _parse_quantity(row.get("quantity"))
            price_mxn = _parse_money(row.get("price_mxn"))
            cost_mxn = _parse_money(row.get("cost_mxn"))
            if not raw_sku or desired_quantity is None or price_mxn is None or cost_mxn is None:
                result.warnings.append(
                    f"Skipped row for {raw_sku or 'unknown SKU'} because required values were missing."
                )
                continue

            target_margin_pct = _parse_decimal(row.get("target_margin_pct"))
            if target_margin_pct is None and price_mxn > 0:
                target_margin_pct = ((price_mxn - cost_mxn) / price_mxn * Decimal("100")).quantize(
                    Decimal("0.01")
                )
            selected_currency = str(row.get("currency") or currency or "mxn").strip().lower()[:8]
            product_defaults = {
                "organization": organization,
                "model": str(model).strip()[:255],
                "name": str(row.get("name") or model).strip()[:255],
                "variant": str(row.get("variant") or "").strip()[:255],
                "color": str(row.get("color") or "").strip()[:128],
                "photo_url": str(row.get("photo_url") or "").strip()[:1024],
                "price_amount": price_mxn,
                "cost_amount": cost_mxn,
                "currency": selected_currency,
                "price_mxn": price_mxn,
                "cost_mxn": cost_mxn,
                "target_margin_pct": target_margin_pct,
                "anchor_model": _parse_anchor_model(row, model=model, anchor_models=anchor_models),
                "scarcity_tag": _scarcity_tag(row, desired_quantity=desired_quantity),
                "status": "active",
                "metadata_json": {
                    "source": source,
                    "source_sku": raw_sku,
                    "source_csv": str(resolved_path),
                    "notes": str(row.get("notes") or "").strip(),
                    "raw_columns": row.get("_raw") or {},
                },
            }
            product, created = InventoryProduct.objects.update_or_create(
                company=company,
                sku=sku,
                defaults=product_defaults,
            )
            reconcile = _reconcile_stock_units(
                product=product,
                desired_quantity=desired_quantity,
                source=source,
            )
            if reconcile["warning"]:
                result.warnings.append(str(reconcile["warning"]))
            InventoryEvent.objects.create(
                organization=organization,
                company=company,
                product=product,
                actor_user=actor,
                event_type="import",
                quantity_delta=int(reconcile["created"]) - int(reconcile["removed"]),
                message=f"Imported {sku} with desired quantity {desired_quantity}.",
                metadata_json={
                    "source": source,
                    "created_product": created,
                    "desired_quantity": desired_quantity,
                    "created_units": reconcile["created"],
                    "removed_units": reconcile["removed"],
                    "active_units": reconcile["active_units"],
                    "warning": reconcile["warning"],
                },
            )
            result.products_seen += 1
            result.products_created += 1 if created else 0
            result.products_updated += 0 if created else 1
            result.stock_units_created += int(reconcile["created"])
            result.stock_units_removed += int(reconcile["removed"])
            result.rows.append(
                InventoryImportRowResult(
                    sku=product.sku,
                    model=product.model,
                    desired_quantity=desired_quantity,
                    created_product=created,
                    created_units=int(reconcile["created"]),
                    removed_units=int(reconcile["removed"]),
                    active_units=int(reconcile["active_units"]),
                    warnings=[str(reconcile["warning"])] if reconcile["warning"] else [],
                )
            )

    result.total_active_units = (
        InventoryStockUnit.objects.filter(
            company=company,
        )
        .exclude(status="removed")
        .count()
    )
    return result


def create_reservation(
    *,
    company: Graph,
    product_id: str | None = None,
    sku: str = "",
    quantity: int = 1,
    buyer_alias: str = "",
    channel: str = "manual",
    note: str = "",
    ttl_minutes: int = DEFAULT_RESERVATION_EXPIRY_MINUTES,
    actor: User | None = None,
    idempotency_key: str = "",
) -> InventoryReservation:
    """Create a stock hold using row locks and oldest available units first."""

    if quantity < 1:
        raise InventoryError("invalid_quantity", "Reservation quantity must be at least 1.")
    if channel not in dict(InventoryReservation.CHANNEL_CHOICES):
        raise InventoryError("invalid_channel", "Reservation channel is not supported.")

    organization = _organization_for_company(company)
    with transaction.atomic():
        existing = _existing_reservation(company=company, idempotency_key=idempotency_key)
        if existing is not None:
            return existing

        product = _resolve_product_locked(company=company, product_id=product_id, sku=sku)
        units = list(
            InventoryStockUnit.objects.select_for_update()
            .filter(company=company, product=product, status="available")
            .order_by("created_at", "unit_number")[:quantity]
        )
        if len(units) != quantity:
            raise InventoryError(
                "insufficient_stock",
                f"Only {len(units)} available unit(s) remain for {product.sku}.",
            )

        reservation = InventoryReservation.objects.create(
            organization=organization,
            company=company,
            product=product,
            created_by=actor,
            status="active",
            quantity=quantity,
            buyer_alias=_sanitize_operator_text(buyer_alias, limit=120),
            channel=channel,
            note=_sanitize_operator_text(note, limit=1000),
            idempotency_key=idempotency_key,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
            metadata_json={"ttl_minutes": ttl_minutes},
        )
        InventoryStockUnit.objects.filter(id__in=[unit.id for unit in units]).update(
            status="reserved",
            current_reservation=reservation,
            updated_at=timezone.now(),
        )
        InventoryEvent.objects.create(
            organization=organization,
            company=company,
            product=product,
            reservation=reservation,
            actor_user=actor,
            event_type="reserve",
            quantity_delta=-quantity,
            message=f"Reserved {quantity} unit(s) of {product.sku}.",
            metadata_json={"idempotency_key": idempotency_key},
        )
        return reservation


def release_reservation(
    *,
    reservation: InventoryReservation,
    actor: User | None = None,
    reason: str = "",
) -> InventoryReservation:
    organization = _organization_for_company(reservation.company)
    with transaction.atomic():
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("company", "product")
            .get(id=reservation.id)
        )
        if reservation.status == "released":
            return reservation
        if reservation.status != "active":
            raise InventoryError(
                "reservation_not_active",
                f"Reservation cannot be released from status {reservation.status}.",
            )
        released = _release_units_for_reservation(reservation)
        reservation.status = "released"
        reservation.released_at = timezone.now()
        reservation.metadata_json = {
            **reservation.metadata_json,
            "release_reason": _sanitize_operator_text(reason, limit=500),
        }
        reservation.save(update_fields=["status", "released_at", "metadata_json", "updated_at"])
        InventoryEvent.objects.create(
            organization=organization,
            company=reservation.company,
            product=reservation.product,
            reservation=reservation,
            actor_user=actor,
            event_type="release",
            quantity_delta=released,
            message=f"Released {released} unit(s) for {reservation.product.sku}.",
            metadata_json={"reason": reservation.metadata_json.get("release_reason", "")},
        )
        return reservation


def extend_reservation(
    *,
    reservation: InventoryReservation,
    minutes: int = DEFAULT_RESERVATION_EXPIRY_MINUTES,
    actor: User | None = None,
) -> InventoryReservation:
    if minutes < 1 or minutes > 24 * 60:
        raise InventoryError("invalid_extension", "Extension must be between 1 and 1440 minutes.")
    organization = _organization_for_company(reservation.company)
    with transaction.atomic():
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("company", "product")
            .get(id=reservation.id)
        )
        if reservation.status != "active":
            raise InventoryError(
                "reservation_not_active",
                f"Reservation cannot be extended from status {reservation.status}.",
            )
        reservation.expires_at = max(timezone.now(), reservation.expires_at) + timedelta(
            minutes=minutes
        )
        reservation.metadata_json = {
            **reservation.metadata_json,
            "last_extension_minutes": minutes,
        }
        reservation.save(update_fields=["expires_at", "metadata_json", "updated_at"])
        InventoryEvent.objects.create(
            organization=organization,
            company=reservation.company,
            product=reservation.product,
            reservation=reservation,
            actor_user=actor,
            event_type="extend",
            quantity_delta=0,
            message=f"Extended reservation by {minutes} minutes.",
            metadata_json={"minutes": minutes},
        )
        return reservation


def create_order_shell(
    *,
    reservation: InventoryReservation,
    actor: User | None = None,
    idempotency_key: str = "",
) -> InventoryOrderShell:
    organization = _organization_for_company(reservation.company)
    with transaction.atomic():
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("company", "product")
            .get(id=reservation.id)
        )
        existing = InventoryOrderShell.objects.filter(reservation=reservation).first()
        if existing is not None:
            return existing
        if reservation.status != "active":
            raise InventoryError(
                "reservation_not_active",
                f"Order shell requires an active reservation, got {reservation.status}.",
            )
        order = InventoryOrderShell.objects.create(
            organization=organization,
            company=reservation.company,
            reservation=reservation,
            created_by=actor,
            order_number=_next_order_number(reservation.company),
            public_reference=_next_public_reference(reservation.company),
            public_status_token=secrets.token_urlsafe(32),
            status="pending_payment",
            idempotency_key=idempotency_key,
            metadata_json={"phase": "inventory_order_shell"},
        )
        reservation.status = "converted"
        reservation.converted_at = timezone.now()
        reservation.save(update_fields=["status", "converted_at", "updated_at"])
        InventoryEvent.objects.create(
            organization=organization,
            company=reservation.company,
            product=reservation.product,
            reservation=reservation,
            order=order,
            actor_user=actor,
            event_type="order_shell",
            quantity_delta=0,
            message=f"Created order shell {order.order_number}.",
            metadata_json={"idempotency_key": idempotency_key},
        )
        return order


def expire_due_reservations(
    *,
    company: Graph,
    actor: User | None = None,
    now: Any | None = None,
) -> list[InventoryReservation]:
    cutoff = now or timezone.now()
    due = list(
        InventoryReservation.objects.filter(
            company=company,
            status="active",
            expires_at__lte=cutoff,
        ).order_by("expires_at")
    )
    expired: list[InventoryReservation] = []
    for reservation in due:
        expired.append(expire_reservation(reservation=reservation, actor=actor))
    return expired


def expire_reservation(
    *,
    reservation: InventoryReservation,
    actor: User | None = None,
) -> InventoryReservation:
    organization = _organization_for_company(reservation.company)
    with transaction.atomic():
        reservation = (
            InventoryReservation.objects.select_for_update()
            .select_related("company", "product")
            .get(id=reservation.id)
        )
        if reservation.status == "expired":
            return reservation
        if reservation.status != "active":
            raise InventoryError(
                "reservation_not_active",
                f"Reservation cannot be expired from status {reservation.status}.",
            )
        released = _release_units_for_reservation(reservation)
        reservation.status = "expired"
        reservation.released_at = timezone.now()
        reservation.save(update_fields=["status", "released_at", "updated_at"])
        InventoryEvent.objects.create(
            organization=organization,
            company=reservation.company,
            product=reservation.product,
            reservation=reservation,
            actor_user=actor,
            event_type="expire",
            quantity_delta=released,
            message=f"Expired reservation and released {released} unit(s).",
            metadata_json={},
        )
        return reservation


def inventory_overview_payload(company: Graph) -> dict[str, Any]:
    """Return inventory counts computed from stock units."""

    products = list(
        InventoryProduct.objects.filter(company=company)
        .annotate(
            total_units=Count(
                "stock_units",
                filter=~Q(stock_units__status="removed"),
            ),
            available_units=Count(
                "stock_units",
                filter=Q(stock_units__status="available"),
            ),
            held_units=Count(
                "stock_units",
                filter=Q(stock_units__status="reserved"),
            ),
            sold_units=Count(
                "stock_units",
                filter=Q(stock_units__status="sold"),
            ),
            removed_units=Count(
                "stock_units",
                filter=Q(stock_units__status="removed"),
            ),
        )
        .order_by("model", "sku")
    )
    reservations = list(
        InventoryReservation.objects.filter(company=company)
        .select_related("product", "order")
        .order_by("-created_at")[:30]
    )
    events = list(
        InventoryEvent.objects.filter(company=company)
        .select_related("product", "reservation", "order", "actor_user")
        .order_by("-created_at")[:50]
    )
    stock_state_summary = stock_state_summary_for_products(products)
    summary = _summary_from_products(products, stock_state_summary=stock_state_summary)
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "summary": summary,
        "stock_state_summary": stock_state_summary,
        "products": [inventory_product_payload(product) for product in products],
        "reservations": [inventory_reservation_payload(item) for item in reservations],
        "events": [inventory_event_payload(item) for item in events],
    }


def inventory_product_payload(product: InventoryProduct) -> dict[str, Any]:
    return {
        "id": str(product.id),
        "company_id": str(product.company_id),
        "sku": product.sku,
        "model": product.model,
        "name": product.name,
        "variant": product.variant,
        "color": product.color,
        "photo_url": product.photo_url,
        "price_amount": str(product.price_amount),
        "cost_amount": str(product.cost_amount),
        "currency": product.currency,
        "price_mxn": str(product.price_mxn),
        "cost_mxn": str(product.cost_mxn),
        "target_margin_pct": str(product.target_margin_pct)
        if product.target_margin_pct is not None
        else None,
        "anchor_model": product.anchor_model,
        "scarcity_tag": product.scarcity_tag,
        "status": product.status,
        "total_units": int(getattr(product, "total_units", 0) or 0),
        "available_units": int(getattr(product, "available_units", 0) or 0),
        "held_units": int(getattr(product, "held_units", 0) or 0),
        "sold_units": int(getattr(product, "sold_units", 0) or 0),
        "removed_units": int(getattr(product, "removed_units", 0) or 0),
        "stock_state": stock_state_for_product(product),
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def inventory_reservation_payload(reservation: InventoryReservation) -> dict[str, Any]:
    order = getattr(reservation, "order", None)
    return {
        "id": str(reservation.id),
        "company_id": str(reservation.company_id),
        "product_id": str(reservation.product_id),
        "product_sku": reservation.product.sku,
        "product_model": reservation.product.model,
        "status": reservation.status,
        "quantity": reservation.quantity,
        "buyer_alias": reservation.buyer_alias,
        "channel": reservation.channel,
        "note": reservation.note,
        "expires_at": reservation.expires_at.isoformat(),
        "released_at": reservation.released_at.isoformat() if reservation.released_at else None,
        "converted_at": reservation.converted_at.isoformat() if reservation.converted_at else None,
        "order_shell": inventory_order_shell_payload(order) if order is not None else None,
        "created_at": reservation.created_at.isoformat(),
        "updated_at": reservation.updated_at.isoformat(),
    }


def inventory_order_shell_payload(order: InventoryOrderShell) -> dict[str, Any]:
    payment = getattr(order, "commerce_payment", None)
    return {
        "id": str(order.id),
        "company_id": str(order.company_id),
        "reservation_id": str(order.reservation_id),
        "order_number": order.order_number,
        "public_reference": order.public_reference,
        "public_status_token": order.public_status_token,
        "status": order.status,
        "stripe_session_id": order.stripe_session_id,
        "stripe_payment_intent_id": order.stripe_payment_intent_id,
        "stripe_checkout_url": order.stripe_checkout_url,
        "customer_email": order.customer_email,
        "customer_name": order.customer_name,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "payment_expired_at": order.payment_expired_at.isoformat()
        if order.payment_expired_at
        else None,
        "commerce_payment": _inventory_payment_payload(payment) if payment is not None else None,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _inventory_payment_payload(payment: Any) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "status": payment.status,
        "amount_mxn": str(payment.amount_mxn),
        "currency": payment.currency,
        "stripe_session_id": payment.stripe_session_id,
        "stripe_payment_intent_id": payment.stripe_payment_intent_id,
        "checkout_url": payment.checkout_url,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "expired_at": payment.expired_at.isoformat() if payment.expired_at else None,
        "error_message": payment.error_message,
    }


def inventory_event_payload(event: InventoryEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "company_id": str(event.company_id),
        "product_id": str(event.product_id) if event.product_id else None,
        "product_sku": event.product.sku if event.product_id and event.product else "",
        "reservation_id": str(event.reservation_id) if event.reservation_id else None,
        "order_id": str(event.order_id) if event.order_id else None,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "event_type": event.event_type,
        "quantity_delta": event.quantity_delta,
        "message": event.message,
        "metadata": event.metadata_json,
        "created_at": event.created_at.isoformat(),
    }


def _summary_from_products(
    products: Iterable[InventoryProduct],
    *,
    stock_state_summary: dict[str, int | str] | None = None,
) -> dict[str, int]:
    product_list = list(products)
    state_summary = stock_state_summary or stock_state_summary_for_products(product_list)
    summary = {
        "total_units": 0,
        "available_units": 0,
        "held_units": 0,
        "sold_units": 0,
        "removed_units": 0,
        "low_stock_products": int(state_summary["low_stock_count"]),
        "last_piece_products": int(state_summary["last_piece_count"]),
        "sold_out_products": int(state_summary["sold_out_count"]),
        "active_holds": InventoryReservation.objects.filter(
            product__in=product_list,
            status="active",
        ).count(),
    }
    for product in product_list:
        total = int(getattr(product, "total_units", 0) or 0)
        available = int(getattr(product, "available_units", 0) or 0)
        summary["total_units"] += total
        summary["available_units"] += available
        summary["held_units"] += int(getattr(product, "held_units", 0) or 0)
        summary["sold_units"] += int(getattr(product, "sold_units", 0) or 0)
        summary["removed_units"] += int(getattr(product, "removed_units", 0) or 0)
    return summary


def _parse_inventory_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise InventoryError("csv_not_found", f"Inventory CSV was not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.reader(handle))
    header_index = _header_index(raw_rows)
    if header_index is None:
        raise InventoryError("invalid_csv", "Could not find inventory CSV header row.")
    raw_headers = raw_rows[header_index]
    headers = [_normalize_header(item) for item in raw_headers]
    parsed: list[dict[str, Any]] = []
    for raw in raw_rows[header_index + 1 :]:
        if not any(str(value).strip() for value in raw):
            continue
        values = list(raw) + [""] * max(0, len(headers) - len(raw))
        normalized: dict[str, Any] = {
            _canonical_field(header): str(values[index]).strip()
            for index, header in enumerate(headers)
            if _canonical_field(header)
        }
        normalized["_raw"] = {
            str(raw_headers[index]).strip(): str(values[index]).strip()
            for index in range(min(len(raw_headers), len(values)))
            if str(raw_headers[index]).strip()
        }
        sku = normalized.get("sku", "").strip()
        if not sku or sku.lower() == "total":
            continue
        parsed.append(normalized)
    return parsed


def _duplicate_sku_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        sku = _required_text(row, "sku")
        if not sku:
            continue
        counts[sku] = counts.get(sku, 0) + 1
    return counts


def _product_sku(
    raw_sku: str,
    *,
    row: dict[str, Any],
    duplicate_sku_counts: dict[str, int],
) -> str:
    raw_sku = raw_sku.strip()
    if duplicate_sku_counts.get(raw_sku, 0) <= 1:
        return raw_sku[:128]
    suffix_source = str(
        row.get("model") or row.get("name") or row.get("variant") or row.get("color") or "variant"
    )
    suffix = re.sub(r"[^A-Z0-9]+", "-", suffix_source.upper()).strip("-") or "VARIANT"
    base = raw_sku[: max(1, 127 - len(suffix))]
    return f"{base}-{suffix}"[:128]


def _header_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        normalized = {_normalize_header(value) for value in row}
        if {"sku", "quantity"}.issubset({_canonical_field(value) for value in normalized}):
            return index
        if "modelo" in normalized and "inventario" in normalized:
            return index
    return None


def _canonical_field(header: str) -> str:
    mapping = {
        "#": "",
        "sku": "sku",
        "modelo": "sku",
        "model": "model",
        "nombrecomercial": "model",
        "nombre": "name",
        "name": "name",
        "variant": "variant",
        "variante": "variant",
        "color": "color",
        "foto": "photo_url",
        "photourl": "photo_url",
        "photo": "photo_url",
        "price": "price_mxn",
        "preciomxn": "price_mxn",
        "precio": "price_mxn",
        "preciopublico": "price_mxn",
        "precioajustado": "price_mxn",
        "cost": "cost_mxn",
        "costmxn": "cost_mxn",
        "costo": "cost_mxn",
        "costopesos": "cost_mxn",
        "quantity": "quantity",
        "inventario": "quantity",
        "stock": "quantity",
        "targetmarginpct": "target_margin_pct",
        "targetmargin": "target_margin_pct",
        "margen": "target_margin_pct",
        "anchormodel": "anchor_model",
        "modeloanchor": "anchor_model",
        "scarcitytag": "scarcity_tag",
        "escasez": "scarcity_tag",
        "notes": "notes",
        "notas": "notes",
    }
    return mapping.get(header, "")


def _normalize_header(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9#]+", "", value.strip().lower())


def _resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (Path(settings.BASE_DIR).parent / candidate).resolve()


def _required_text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _parse_money(value: Any) -> Decimal | None:
    return _parse_decimal(value)


def _parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_quantity(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(0, int(Decimal(re.sub(r"[^0-9.\-]", "", text))))
    except (InvalidOperation, ValueError):
        return None


def _parse_anchor_model(
    row: dict[str, Any], *, model: str, anchor_models: set[str] | None = None
) -> bool:
    explicit = str(row.get("anchor_model") or "").strip().lower()
    if explicit in {"1", "true", "yes", "y", "si", "sí"}:
        return True
    if explicit in {"0", "false", "no", "n"}:
        return False
    return str(model).upper().strip() in (anchor_models or set())


def _scarcity_tag(row: dict[str, Any], *, desired_quantity: int) -> str:
    explicit = str(row.get("scarcity_tag") or "").strip()
    if explicit:
        return explicit[:64]
    if desired_quantity == 0:
        return "sold_out"
    if desired_quantity == 1:
        return "last_piece"
    if desired_quantity <= 2:
        return "low_stock"
    return ""


def _reconcile_stock_units(
    *,
    product: InventoryProduct,
    desired_quantity: int,
    source: str,
) -> dict[str, Any]:
    active_count = (
        InventoryStockUnit.objects.filter(product=product).exclude(status="removed").count()
    )
    created = 0
    removed = 0
    warning = ""
    if active_count < desired_quantity:
        max_unit = (
            InventoryStockUnit.objects.filter(product=product).aggregate(Max("unit_number"))[
                "unit_number__max"
            ]
            or 0
        )
        for offset in range(desired_quantity - active_count):
            InventoryStockUnit.objects.create(
                organization=product.organization,
                company=product.company,
                product=product,
                unit_number=int(max_unit) + offset + 1,
                status="available",
                source=source,
                metadata_json={"source": source},
            )
            created += 1
    elif active_count > desired_quantity:
        excess = active_count - desired_quantity
        removable = list(
            InventoryStockUnit.objects.filter(product=product, status="available").order_by(
                "-unit_number"
            )[:excess]
        )
        if len(removable) < excess:
            warning = (
                f"{product.sku} desired quantity is {desired_quantity}, but "
                f"{excess - len(removable)} reserved/sold unit(s) could not be removed."
            )
        if removable:
            InventoryStockUnit.objects.filter(id__in=[unit.id for unit in removable]).update(
                status="removed",
                current_reservation=None,
                updated_at=timezone.now(),
            )
            removed = len(removable)
    active_units = (
        InventoryStockUnit.objects.filter(product=product).exclude(status="removed").count()
    )
    return {
        "created": created,
        "removed": removed,
        "active_units": active_units,
        "warning": warning,
    }


def _organization_for_company(company: Graph) -> Organization:
    organization = company.organization
    if organization is None:
        raise InventoryError("organization_required", "Inventory requires an organization company.")
    return organization


def _resolve_product_locked(
    *,
    company: Graph,
    product_id: str | None = None,
    sku: str = "",
) -> InventoryProduct:
    queryset = InventoryProduct.objects.select_for_update().filter(company=company, status="active")
    if product_id:
        product = queryset.filter(id=product_id).first()
    elif sku:
        product = queryset.filter(sku=sku).first()
    else:
        raise InventoryError("product_required", "A product_id or sku is required.")
    if product is None:
        raise InventoryError("product_not_found", "Inventory product was not found.")
    return product


def _existing_reservation(
    *,
    company: Graph,
    idempotency_key: str = "",
) -> InventoryReservation | None:
    if not idempotency_key:
        return None
    return (
        InventoryReservation.objects.select_related("product")
        .filter(company=company, idempotency_key=idempotency_key)
        .first()
    )


def _release_units_for_reservation(reservation: InventoryReservation) -> int:
    updated = (
        InventoryStockUnit.objects.select_for_update()
        .filter(
            company=reservation.company,
            current_reservation=reservation,
            status="reserved",
        )
        .update(status="available", current_reservation=None, updated_at=timezone.now())
    )
    return int(updated)


def _next_order_number(company: Graph) -> str:
    count = InventoryOrderShell.objects.filter(company=company).count() + 1
    return f"INV-{str(company.id)[:8].upper()}-{count:05d}"


def _next_public_reference(company: Graph) -> str:
    count = InventoryOrderShell.objects.filter(company=company).count() + 1
    return f"ORDER-{str(company.id)[:6].upper()}-{count:05d}"


def _sanitize_operator_text(value: str, *, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[redacted-email]", text)
    text = re.sub(r"\b\d[\d\s\-]{5,}\d\b", "[redacted-number]", text)
    return text[:limit]
