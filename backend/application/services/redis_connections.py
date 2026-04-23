from __future__ import annotations

import os
from typing import Any, cast

from redis import Redis
from redis.sentinel import Sentinel


def build_redis_client(
    *,
    db: int,
    decode_responses: bool = True,
) -> Redis:
    sentinel_master_name = str(os.environ.get("REDIS_SENTINEL_MASTER_NAME") or "").strip()
    sentinel_addrs = _parse_sentinel_addrs(
        os.environ.get("REDIS_SENTINEL_ADDRS") or os.environ.get("REDIS_SENTINELS") or ""
    )
    if sentinel_master_name and sentinel_addrs:
        sentinel: Sentinel = Sentinel(  # type: ignore[no-untyped-call]
            sentinel_addrs,
            sentinel_kwargs=_sentinel_connection_kwargs(),
            socket_timeout=_optional_timeout_seconds("REDIS_SOCKET_TIMEOUT_MS"),
            socket_connect_timeout=_optional_timeout_seconds("REDIS_SOCKET_CONNECT_TIMEOUT_MS"),
            decode_responses=decode_responses,
        )
        return cast(
            Redis,
            sentinel.master_for(  # type: ignore[no-untyped-call]
                sentinel_master_name,
                db=db,
                **_redis_connection_kwargs(decode_responses=decode_responses),
            ),
        )

    return Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=db,
        **_redis_connection_kwargs(decode_responses=decode_responses),
    )


def _redis_connection_kwargs(*, decode_responses: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "decode_responses": decode_responses,
        "username": _optional_string("REDIS_USERNAME"),
        "password": _optional_string("REDIS_PASSWORD"),
        "socket_timeout": _optional_timeout_seconds("REDIS_SOCKET_TIMEOUT_MS"),
        "socket_connect_timeout": _optional_timeout_seconds("REDIS_SOCKET_CONNECT_TIMEOUT_MS"),
        "health_check_interval": 30,
    }
    return {key: value for key, value in kwargs.items() if value is not None}


def _sentinel_connection_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "username": _optional_string("REDIS_SENTINEL_USERNAME"),
        "password": _optional_string("REDIS_SENTINEL_PASSWORD"),
    }
    return {key: value for key, value in kwargs.items() if value is not None}


def _optional_string(name: str) -> str | None:
    value = str(os.environ.get(name) or "").strip()
    return value or None


def _optional_timeout_seconds(name: str) -> float | None:
    raw_value = str(os.environ.get(name) or "").strip()
    if not raw_value:
        return None
    try:
        timeout_ms = int(raw_value)
    except ValueError:
        return None
    if timeout_ms <= 0:
        return None
    return timeout_ms / 1000.0


def _parse_sentinel_addrs(raw_value: str) -> list[tuple[str, int]]:
    addrs: list[tuple[str, int]] = []
    for raw_entry in str(raw_value or "").replace(";", ",").split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        host, separator, port_text = entry.partition(":")
        if not separator:
            continue
        host = host.strip()
        port_text = port_text.strip()
        if not host or not port_text:
            continue
        try:
            port = int(port_text)
        except ValueError:
            continue
        addrs.append((host, port))
    return addrs
