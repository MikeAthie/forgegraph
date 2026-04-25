from __future__ import annotations

from uuid import UUID

from django.db import connection


def _to_signed_int32(value: int) -> int:
    if value >= 2**31:
        return value - 2**32
    return value


def _run_lock_keys(run_id: UUID) -> tuple[int, int]:
    raw = run_id.bytes
    first = int.from_bytes(raw[:4], byteorder="big", signed=False)
    second = int.from_bytes(raw[4:8], byteorder="big", signed=False)
    return _to_signed_int32(first), _to_signed_int32(second)


def acquire_run_transaction_lock(run_id: UUID) -> None:
    """
    Serialize backend writers for a run inside the current transaction.

    The backend remains the durable source of truth; this only constrains write
    concurrency so concurrent callback and intent processing paths cannot
    deadlock while mutating the same run-owned rows.
    """

    if connection.vendor != "postgresql":
        return

    key_one, key_two = _run_lock_keys(run_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [key_one, key_two])
