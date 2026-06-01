from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis import Redis

from application.services.redis_connections import build_redis_client

SNAPSHOT_KEY_PREFIX = "forgegraph:snapshot"
RUN_SNAPSHOT_DEFAULT_TTL_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunSnapshot:
    run_id: UUID
    last_completed_node: str
    next_node: str
    attempt_id: str
    updated_at: datetime


def build_run_snapshot_redis_client() -> Redis:
    return build_redis_client(
        db=int(os.environ.get("RUN_SNAPSHOT_REDIS_DB", os.environ.get("REDIS_DB", "0"))),
        decode_responses=True,
    )


def _use_cache_snapshot_store() -> bool:
    default_cache = settings.CACHES.get("default", {})
    backend = str(default_cache.get("BACKEND") or "").lower()
    return "locmemcache" in backend


def snapshot_key(run_id: UUID | str) -> str:
    return f"{SNAPSHOT_KEY_PREFIX}:{run_id}"


def run_snapshot_ttl_seconds() -> int:
    configured_value: object = os.environ.get("FORGEGRAPH_RUN_SNAPSHOT_TTL_SECONDS")
    if configured_value is None or configured_value == "":
        configured_value = getattr(
            settings,
            "FORGEGRAPH_RUN_SNAPSHOT_TTL_SECONDS",
            RUN_SNAPSHOT_DEFAULT_TTL_SECONDS,
        )
    try:
        ttl_seconds = int(str(configured_value))
    except (TypeError, ValueError):
        logger.warning(
            "invalid_run_snapshot_ttl",
            extra={"configured_value": str(configured_value)},
        )
        return RUN_SNAPSHOT_DEFAULT_TTL_SECONDS
    if ttl_seconds <= 0:
        logger.warning(
            "invalid_run_snapshot_ttl",
            extra={"configured_value": str(configured_value)},
        )
        return RUN_SNAPSHOT_DEFAULT_TTL_SECONDS
    return ttl_seconds


def get_snapshot(
    run_id: UUID | str,
    *,
    redis_client: Redis | None = None,
) -> RunSnapshot | None:
    if redis_client is None and _use_cache_snapshot_store():
        raw_payload = cache.get(snapshot_key(run_id))
    else:
        client = redis_client or build_run_snapshot_redis_client()
        raw_payload = client.get(snapshot_key(run_id))
    if not raw_payload:
        return None

    payload = json.loads(cast(str | bytes | bytearray, raw_payload))
    updated_at = parse_datetime(str(payload.get("updated_at") or "").strip())
    if updated_at is None:
        raise ValueError("snapshot.updated_at must be a valid ISO-8601 timestamp")

    return RunSnapshot(
        run_id=UUID(str(payload.get("run_id") or "").strip()),
        last_completed_node=str(payload.get("last_completed_node") or "").strip(),
        next_node=str(payload.get("next_node") or "").strip(),
        attempt_id=str(payload.get("attempt_id") or "").strip(),
        updated_at=updated_at,
    )


def set_snapshot(
    snapshot: RunSnapshot,
    *,
    redis_client: Redis | None = None,
) -> None:
    payload = asdict(snapshot)
    payload["run_id"] = str(snapshot.run_id)
    payload["updated_at"] = (snapshot.updated_at or timezone.now()).isoformat()
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    ttl_seconds = run_snapshot_ttl_seconds()
    key = snapshot_key(snapshot.run_id)

    if redis_client is None and _use_cache_snapshot_store():
        cache.set(key, serialized, timeout=ttl_seconds)
        return

    client = redis_client or build_run_snapshot_redis_client()
    client.setex(key, ttl_seconds, serialized)


def safe_set_snapshot(
    snapshot: RunSnapshot,
    *,
    redis_client: Redis | None = None,
) -> None:
    try:
        set_snapshot(snapshot, redis_client=redis_client)
    except Exception:
        logger.error(
            "snapshot_write_failed",
            exc_info=True,
            extra={
                "run_id": str(snapshot.run_id),
                "node_id": snapshot.last_completed_node,
                "next_node": snapshot.next_node,
                "attempt_id": snapshot.attempt_id,
            },
        )


def delete_snapshot(
    run_id: UUID | str,
    *,
    redis_client: Redis | None = None,
) -> None:
    if redis_client is None and _use_cache_snapshot_store():
        cache.delete(snapshot_key(run_id))
        return

    client = redis_client or build_run_snapshot_redis_client()
    client.delete(snapshot_key(run_id))


def safe_delete_snapshot(
    run_id: UUID | str,
    *,
    redis_client: Redis | None = None,
) -> None:
    try:
        delete_snapshot(run_id, redis_client=redis_client)
    except Exception:
        logger.error(
            "snapshot_delete_failed",
            exc_info=True,
            extra={"run_id": str(run_id)},
        )
