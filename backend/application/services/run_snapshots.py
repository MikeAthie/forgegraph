from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis import Redis

SNAPSHOT_KEY_PREFIX = "forgegraph:snapshot"


@dataclass(frozen=True)
class RunSnapshot:
    run_id: UUID
    last_completed_node: str
    next_node: str
    attempt_id: str
    updated_at: datetime


def build_run_snapshot_redis_client() -> Redis:
    return Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=int(os.environ.get("RUN_SNAPSHOT_REDIS_DB", os.environ.get("REDIS_DB", "0"))),
        password=os.environ.get("REDIS_PASSWORD") or None,
        decode_responses=True,
    )


def snapshot_key(run_id: UUID | str) -> str:
    return f"{SNAPSHOT_KEY_PREFIX}:{run_id}"


def get_snapshot(
    run_id: UUID | str,
    *,
    redis_client: Redis | None = None,
) -> RunSnapshot | None:
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
    client = redis_client or build_run_snapshot_redis_client()
    payload = asdict(snapshot)
    payload["run_id"] = str(snapshot.run_id)
    payload["updated_at"] = (snapshot.updated_at or timezone.now()).isoformat()
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    ttl_seconds = int(os.environ.get("FORGEGRAPH_RUN_SNAPSHOT_TTL_SECONDS", "0") or "0")
    key = snapshot_key(snapshot.run_id)
    if ttl_seconds > 0:
        client.setex(key, ttl_seconds, serialized)
        return
    client.set(key, serialized)


def delete_snapshot(
    run_id: UUID | str,
    *,
    redis_client: Redis | None = None,
) -> None:
    client = redis_client or build_run_snapshot_redis_client()
    client.delete(snapshot_key(run_id))
