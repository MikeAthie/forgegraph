"""
Redis-backed auth state helpers for token revocation and one-time WebSocket tickets.
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import timedelta
from functools import lru_cache
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from rest_framework_simplejwt.tokens import AccessToken, Token

from application.services.tenancy import get_default_membership
from infrastructure.orm.models import User

_REVOKED_ACCESS_PREFIX = "auth:revoked:access:"
_WS_TICKET_PREFIX = "auth:ws-ticket:"


def _cache_location() -> str:
    default_cache = cast(dict[str, Any], settings.CACHES.get("default", {}))
    location = default_cache.get("LOCATION", "")
    return str(location) if location is not None else ""


@lru_cache(maxsize=1)
def _redis_client() -> Redis | None:
    location = _cache_location()
    if not location.startswith("redis://") and not location.startswith("rediss://"):
        return None
    return Redis.from_url(location)


@lru_cache(maxsize=1)
def _async_redis_client() -> AsyncRedis | None:
    location = _cache_location()
    if not location.startswith("redis://") and not location.startswith("rediss://"):
        return None
    return cast(AsyncRedis, AsyncRedis.from_url(location))


def _token_ttl_seconds(token: Token) -> int:
    exp = token.get("exp")
    if exp is None:
        lifetime = cast(timedelta, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])
        return max(1, int(lifetime.total_seconds()))
    ttl = int(exp) - int(time.time())
    return max(1, ttl)


def _access_jti(token: Token) -> str:
    return str(token.get("jti") or "")


def _ws_permissions_for_user(user: User) -> list[str]:
    membership = get_default_membership(user)
    role = membership.role if membership is not None else "viewer"
    permissions = {"organizations:state:view", "runs:view"}
    if role in {"member", "admin", "owner"}:
        permissions.add("runs:operate")
    if role in {"admin", "owner"}:
        permissions.add("runs:admin")
    return sorted(permissions)


def issue_ws_ticket(
    *,
    access_token: Token,
    user: User | None = None,
    user_id: str | None = None,
    org_id: str | None = None,
    permissions: list[str] | None = None,
) -> tuple[str, int]:
    ttl_seconds = int(getattr(settings, "AUTH_WS_TICKET_TTL_SECONDS", 45))
    ticket = secrets.token_urlsafe(32)
    resolved_user_id = user_id or (str(user.id) if user is not None else "")
    resolved_org_id = org_id or (
        str(getattr(user, "default_organization_id", "") or "") if user is not None else ""
    )
    resolved_permissions = permissions or (
        _ws_permissions_for_user(user) if user is not None else ["runs:view"]
    )
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    payload = {
        "ticket": ticket,
        "user_id": resolved_user_id,
        "org_id": resolved_org_id,
        "permissions": resolved_permissions,
        "expires_at": expires_at.isoformat(),
        "used": False,
        "access_jti": _access_jti(access_token),
        "issued_at": int(time.time()),
    }

    serialized = json.dumps(payload)
    key = f"{_WS_TICKET_PREFIX}{ticket}"

    redis_client = _redis_client()
    if redis_client is not None:
        redis_client.setex(key, ttl_seconds, serialized)
    else:
        cache.set(key, serialized, timeout=ttl_seconds)

    return ticket, ttl_seconds


async def async_issue_ws_ticket(
    *,
    access_token: Token,
    user_id: str,
    org_id: str,
    permissions: list[str],
) -> tuple[str, int]:
    ttl_seconds = int(getattr(settings, "AUTH_WS_TICKET_TTL_SECONDS", 45))
    ticket = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    payload = {
        "ticket": ticket,
        "user_id": str(user_id),
        "org_id": str(org_id),
        "permissions": permissions,
        "expires_at": expires_at.isoformat(),
        "used": False,
        "access_jti": _access_jti(access_token),
        "issued_at": int(time.time()),
    }

    serialized = json.dumps(payload)
    key = f"{_WS_TICKET_PREFIX}{ticket}"

    redis_client = _async_redis_client()
    if redis_client is not None:
        await redis_client.setex(key, ttl_seconds, serialized)
    else:
        await sync_to_async(cache.set, thread_sensitive=False)(
            key,
            serialized,
            timeout=ttl_seconds,
        )

    return ticket, ttl_seconds


def consume_ws_ticket(ticket: str) -> dict[str, Any] | None:
    key = f"{_WS_TICKET_PREFIX}{ticket}"
    redis_client = _redis_client()
    raw_payload: Any
    if redis_client is not None:
        raw_payload = redis_client.getdel(key)
    else:
        raw_payload = cache.get(key)
        if raw_payload is not None:
            cache.delete(key)

    if raw_payload is None:
        return None

    payload = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload
    if not isinstance(payload, str):
        return None

    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


def revoke_access_token(token: Token) -> None:
    jti = _access_jti(token)
    if not jti:
        return

    ttl_seconds = _token_ttl_seconds(token)
    key = f"{_REVOKED_ACCESS_PREFIX}{jti}"
    redis_client = _redis_client()
    if redis_client is not None:
        redis_client.setex(key, ttl_seconds, "1")
    else:
        cache.set(key, "1", timeout=ttl_seconds)


def is_access_token_revoked(token: Token) -> bool:
    jti = _access_jti(token)
    if not jti:
        return False
    return is_access_jti_revoked(jti)


def is_access_jti_revoked(jti: str) -> bool:
    if not jti:
        return False

    key = f"{_REVOKED_ACCESS_PREFIX}{jti}"
    redis_client = _redis_client()
    if redis_client is not None:
        return bool(redis_client.exists(key))
    return cache.get(key) is not None


def validate_access_token(raw_token: str) -> AccessToken | None:
    try:
        token = AccessToken(cast(Any, raw_token))
    except Exception:
        return None

    if is_access_token_revoked(token):
        return None
    return token


async def async_validate_access_token(raw_token: str) -> AccessToken | None:
    try:
        token = AccessToken(cast(Any, raw_token))
    except Exception:
        return None

    jti = _access_jti(token)
    if jti and await async_is_access_jti_revoked(jti):
        return None
    return token


async def async_is_access_jti_revoked(jti: str) -> bool:
    if not jti:
        return False

    key = f"{_REVOKED_ACCESS_PREFIX}{jti}"
    redis_client = _async_redis_client()
    if redis_client is not None:
        return bool(await redis_client.exists(key))
    return await sync_to_async(lambda: cache.get(key) is not None, thread_sensitive=False)()


async def async_cache_increment_with_ttl(key: str, ttl_seconds: int) -> int:
    redis_client = _async_redis_client()
    if redis_client is not None:
        count = int(await redis_client.incr(key))
        if count == 1:
            await redis_client.expire(key, max(int(ttl_seconds), 1))
        return count

    def _increment() -> int:
        added = cache.add(key, 1, timeout=max(int(ttl_seconds), 1))
        return 1 if added else int(cache.incr(key))

    return await sync_to_async(_increment, thread_sensitive=False)()
