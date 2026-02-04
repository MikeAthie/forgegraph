from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final

from django.conf import settings

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
