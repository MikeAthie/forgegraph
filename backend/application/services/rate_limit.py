from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.cache import cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after_seconds: int


def check_rate_limit(
    *,
    scope: str,
    tenant_id: str,
    limit: int,
    window_seconds: int = 60,
) -> RateLimitResult:
    now = datetime.now(UTC)
    if limit <= 0:
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit,
            reset_at=now + timedelta(seconds=window_seconds),
            retry_after_seconds=0,
        )

    window_start = now - timedelta(seconds=int(now.timestamp()) % window_seconds)
    reset_at = window_start + timedelta(seconds=window_seconds)
    key = f"rate:{scope}:{tenant_id}:{int(window_start.timestamp())}"

    added = cache.add(key, 1, timeout=window_seconds)
    if added:
        count = 1
    else:
        try:
            count = int(cache.incr(key))
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)
            count = 1

    remaining = max(0, limit - count)
    allowed = count <= limit
    retry_after = max(0, int((reset_at - now).total_seconds()))

    return RateLimitResult(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        reset_at=reset_at,
        retry_after_seconds=retry_after,
    )


def rate_limit_response_payload(result: RateLimitResult) -> dict[str, Any]:
    return {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset_at": result.reset_at.isoformat(),
        "retry_after_seconds": result.retry_after_seconds,
    }
