from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final

from django.conf import settings
from django.core.cache import cache

DEFAULT_MAX_SKEW_SECONDS: Final[int] = 600


def _get_secret() -> str:
    return getattr(settings, "ENGINE_CALLBACK_SECRET", "")


def _get_max_skew_seconds() -> int:
    value = getattr(settings, "ENGINE_CALLBACK_MAX_SKEW_SECONDS", DEFAULT_MAX_SKEW_SECONDS)
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_SKEW_SECONDS


def build_signature(secret: str, timestamp_ms: str, body: bytes) -> str:
    message = f"{timestamp_ms}.".encode() + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(*, timestamp_ms: str, signature: str, body: bytes) -> bool:
    secret = _get_secret()
    if not secret:
        return False

    expected = build_signature(secret, timestamp_ms, body)
    return hmac.compare_digest(expected, signature)


def verify_request(*, timestamp_ms: str, signature: str, body: bytes) -> tuple[bool, str]:
    """
    Verify S2S signature and timestamp.

    Returns (ok, reason).
    """
    if not timestamp_ms or not signature:
        return False, "missing_signature"

    try:
        timestamp_int = int(timestamp_ms)
    except (TypeError, ValueError):
        return False, "invalid_timestamp"

    now_ms = int(time.time() * 1000)
    max_skew_ms = _get_max_skew_seconds() * 1000
    if abs(now_ms - timestamp_int) > max_skew_ms:
        return False, "stale_timestamp"

    if not verify_signature(timestamp_ms=timestamp_ms, signature=signature, body=body):
        return False, "invalid_signature"

    return True, "ok"


def verify_request_once(
    *,
    timestamp_ms: str,
    signature: str,
    body: bytes,
    method: str,
    path: str,
) -> tuple[bool, str]:
    """
    Verify S2S signature/timestamp and reject exact replayed HTTP requests.

    Domain idempotency still belongs to the backend handlers. This guard only
    rejects a captured request with the same timestamp, signature, body digest,
    method, and path inside the callback skew window.
    """
    ok, reason = verify_request(timestamp_ms=timestamp_ms, signature=signature, body=body)
    if not ok:
        return ok, reason

    digest = hashlib.sha256(body).hexdigest()
    replay_material = "\n".join(
        [
            method.upper(),
            path,
            timestamp_ms,
            signature,
            digest,
        ]
    )
    replay_digest = hashlib.sha256(replay_material.encode("utf-8")).hexdigest()
    cache_key = f"forgegraph:s2s-replay:{replay_digest}"
    ttl_seconds = max(_get_max_skew_seconds(), 1)
    try:
        replay_slot_acquired = cache.add(cache_key, "1", timeout=ttl_seconds)
    except Exception:
        return False, "replay_cache_unavailable"
    if not replay_slot_acquired:
        return False, "replayed_signature"
    return True, "ok"
