from __future__ import annotations

from typing import Any

from django.db.models import QuerySet


def assert_queryset_count(queryset: QuerySet[Any], expected: int, *, label: str = "") -> None:
    actual = queryset.count()
    context = f" for {label}" if label else ""
    assert actual == expected, f"expected {expected} row(s){context}, found {actual}"


def assert_response_idempotency(response: Any, *, status: str, idempotency_key: str) -> None:
    body = response.data if hasattr(response, "data") else response.json()
    data = body.get("data") if isinstance(body, dict) else None
    meta = body.get("meta") if isinstance(body, dict) else None
    assert isinstance(data, dict)
    assert isinstance(meta, dict)
    assert data["idempotency"]["status"] == status
    assert data["idempotency"]["idempotency_key"] == idempotency_key
    assert meta["idempotency"]["status"] == status
    assert meta["idempotency"]["idempotency_key"] == idempotency_key
