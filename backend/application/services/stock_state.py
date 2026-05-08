"""Canonical stock-state semantics for company inventory surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

STOCK_STATE_DEFINITION = (
    "Only active products are counted; sold_out means available_units == 0, "
    "last_piece means available_units == 1, low_stock means available_units == 2, "
    "and active means available_units >= 3."
)

COUNT_KEYS = ("active_count", "low_stock_count", "last_piece_count", "sold_out_count")


def stock_state_for_counts(
    *, product_status: str, active_units: int, held_units: int = 0, sold_units: int = 0
) -> str | None:
    """Return the canonical stock state for an inventory product."""

    if product_status != "active":
        return None
    available = max(0, int(active_units or 0))
    if available == 0:
        return "sold_out"
    if available == 1:
        return "last_piece"
    if available == 2:
        return "low_stock"
    return "active"


def stock_state_for_product(product: Any) -> str | None:
    return stock_state_for_counts(
        product_status=str(getattr(product, "status", "")),
        active_units=int(getattr(product, "available_units", 0) or 0),
        held_units=int(getattr(product, "held_units", 0) or 0),
        sold_units=int(getattr(product, "sold_units", 0) or 0),
    )


def empty_stock_state_summary() -> dict[str, int | str]:
    return {
        "active_count": 0,
        "low_stock_count": 0,
        "last_piece_count": 0,
        "sold_out_count": 0,
        "definition_used": STOCK_STATE_DEFINITION,
    }


def stock_state_summary_for_products(products: Iterable[Any]) -> dict[str, int | str]:
    summary = empty_stock_state_summary()
    for product in products:
        state = stock_state_for_product(product)
        if state == "active":
            summary["active_count"] = int(summary["active_count"]) + 1
        elif state == "low_stock":
            summary["low_stock_count"] = int(summary["low_stock_count"]) + 1
        elif state == "last_piece":
            summary["last_piece_count"] = int(summary["last_piece_count"]) + 1
        elif state == "sold_out":
            summary["sold_out_count"] = int(summary["sold_out_count"]) + 1
    return summary
