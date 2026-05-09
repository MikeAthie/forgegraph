from __future__ import annotations

from types import SimpleNamespace

from application.services.stock_state import (
    STOCK_STATE_DEFINITION,
    stock_state_for_counts,
    stock_state_summary_for_products,
)


def test_stock_state_for_counts_is_mutually_exclusive():
    assert stock_state_for_counts(product_status="active", active_units=4) == "active"
    assert stock_state_for_counts(product_status="active", active_units=2) == "low_stock"
    assert stock_state_for_counts(product_status="active", active_units=1) == "last_piece"
    assert stock_state_for_counts(product_status="active", active_units=0) == "sold_out"
    assert stock_state_for_counts(product_status="archived", active_units=0) is None


def test_stock_state_summary_excludes_archived_products():
    products = [
        SimpleNamespace(status="active", available_units=5, held_units=0, sold_units=0),
        SimpleNamespace(status="active", available_units=2, held_units=1, sold_units=0),
        SimpleNamespace(status="active", available_units=1, held_units=0, sold_units=1),
        SimpleNamespace(status="active", available_units=0, held_units=0, sold_units=3),
        SimpleNamespace(status="archived", available_units=0, held_units=0, sold_units=0),
    ]

    summary = stock_state_summary_for_products(products)

    assert summary == {
        "active_count": 1,
        "low_stock_count": 1,
        "last_piece_count": 1,
        "sold_out_count": 1,
        "definition_used": STOCK_STATE_DEFINITION,
    }
