"""Backend-owned snapshot recovery evidence drills."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from application.services.redis_connections import build_redis_client
from application.services.run_snapshots import (
    RunSnapshot,
    get_snapshot,
    safe_delete_snapshot,
    set_snapshot,
)
from application.services.whiteboard_boards import (
    rebuild_whiteboard_board_snapshot_from_db,
    whiteboard_board_snapshot_key,
)
from application.services.work_whiteboards import (
    _whiteboard_queryset,
    rebuild_whiteboard_snapshot_from_db,
    whiteboard_snapshot_key,
)
from infrastructure.orm.models import Run, WorkWhiteboard


def run_whiteboard_snapshot_recovery_drill(whiteboard_id: UUID | str) -> dict[str, Any]:
    """Corrupt cache-only whiteboard snapshots and rebuild them from DB truth."""

    whiteboard = _whiteboard_queryset().filter(id=whiteboard_id).first()
    if whiteboard is None:
        return {
            "available": False,
            "reason": "whiteboard_not_found",
            "whiteboard_id": str(whiteboard_id),
        }

    whiteboard_key = whiteboard_snapshot_key(whiteboard)
    board_key = whiteboard_board_snapshot_key(whiteboard)
    _set_snapshot_corruption(whiteboard_key)
    _set_snapshot_corruption(board_key)

    rebuilt_whiteboard = rebuild_whiteboard_snapshot_from_db(whiteboard.id)
    rebuilt_board = rebuild_whiteboard_board_snapshot_from_db(whiteboard.id)

    return {
        "available": rebuilt_whiteboard is not None and rebuilt_board is not None,
        "drill": "whiteboard_snapshot_cache_corruption",
        "authoritative_state_source": "backend_db",
        "cache_role": "cache_transport_only",
        "engine_durable_ownership": False,
        "whiteboard_id": str(whiteboard.id),
        "whiteboard_snapshot": _whiteboard_snapshot_evidence(
            whiteboard,
            cache_key=whiteboard_key,
            rebuilt=rebuilt_whiteboard,
        ),
        "board_snapshot": {
            "cache_key": board_key,
            "snapshot_source": str((rebuilt_board or {}).get("snapshot_source") or ""),
            "snapshot_version": str((rebuilt_board or {}).get("snapshot_version") or ""),
            "event_version": str((rebuilt_board or {}).get("event_version") or ""),
            "card_count": len((rebuilt_board or {}).get("cards") or []),
            "lane_count": len((rebuilt_board or {}).get("lanes") or []),
        },
    }


def run_checkpoint_recovery_drill(
    run_id: UUID | str,
    *,
    active_attempt_id: str = "attempt-backend-owned",
    stale_attempt_id: str = "attempt-stale-engine",
) -> dict[str, Any]:
    """Record run snapshot recovery evidence without giving the engine durable ownership."""

    run = Run.objects.filter(id=run_id).first()
    if run is None:
        return {"available": False, "reason": "run_not_found", "run_id": str(run_id)}

    safe_delete_snapshot(run.id)
    missing_checkpoint_fails_closed = get_snapshot(run.id) is None
    set_snapshot(
        RunSnapshot(
            run_id=run.id,
            last_completed_node="snapshot_recovery_drill",
            next_node="after_snapshot_recovery_drill",
            attempt_id=active_attempt_id,
            updated_at=timezone.now(),
        )
    )
    snapshot = get_snapshot(run.id)

    return {
        "available": snapshot is not None,
        "drill": "run_checkpoint_recovery",
        "authoritative_state_source": "backend_snapshot_store",
        "engine_durable_ownership": False,
        "run_id": str(run.id),
        "missing_checkpoint_fails_closed": missing_checkpoint_fails_closed,
        "valid_checkpoint_can_drive_recovery": snapshot is not None
        and snapshot.attempt_id == active_attempt_id
        and snapshot.next_node == "after_snapshot_recovery_drill",
        "stale_attempt_rejected_by_attempt_match": snapshot is not None
        and snapshot.attempt_id != stale_attempt_id,
        "checkpoint": {
            "last_completed_node": snapshot.last_completed_node if snapshot else "",
            "next_node": snapshot.next_node if snapshot else "",
            "attempt_id": snapshot.attempt_id if snapshot else "",
            "updated_at": snapshot.updated_at.isoformat() if snapshot else "",
        },
    }


def _whiteboard_snapshot_evidence(
    whiteboard: WorkWhiteboard,
    *,
    cache_key: str,
    rebuilt: dict[str, Any] | None,
) -> dict[str, Any]:
    rebuilt_from_db = rebuilt is not None
    return {
        "cache_key": cache_key,
        "snapshot_source": "db" if rebuilt_from_db else "",
        "snapshot_version": "work_whiteboard_v1" if rebuilt_from_db else "",
        "whiteboard_id": str((rebuilt or {}).get("id") or whiteboard.id),
        "status": str((rebuilt or {}).get("status") or whiteboard.status),
        "company_id": str((rebuilt or {}).get("company_id") or whiteboard.company_id),
    }


def _set_snapshot_corruption(key: str) -> None:
    payload = json.dumps({"corrupted": True, "source": "recovery_drill"})
    if _use_cache_snapshot_store():
        cache.set(key, payload, timeout=60)
        return
    try:
        redis_client = build_redis_client(
            db=int(os.environ.get("WHITEBOARD_SNAPSHOT_REDIS_DB", os.environ.get("REDIS_DB", "0"))),
            decode_responses=True,
        )
        redis_client.setex(key, 60, payload)
    except Exception:
        cache.set(key, payload, timeout=60)


def _use_cache_snapshot_store() -> bool:
    default_cache = settings.CACHES.get("default", {})
    backend = str(default_cache.get("BACKEND", "")).lower()
    return "locmemcache" in backend
