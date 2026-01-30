from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from django.db import connection

from django.core.cache import cache

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from infrastructure.orm.models import MemoryChunk, User

logger = logging.getLogger(__name__)


class MemoryGCService:
    def __init__(self, repository: MemoryChunkRepository | None = None) -> None:
        self._repository = repository or MemoryChunkRepository()

    def cleanup(
        self,
        *,
        retention_days: int,
        tenant_ids_to_delete: list[str] | None = None,
        prune_missing_users: bool = False,
        reindex: bool = False,
    ) -> dict[str, int | bool]:
        stats: dict[str, int | bool] = {
            "deleted_by_retention": 0,
            "deleted_by_tenant": 0,
            "deleted_missing_users": 0,
            "reindexed": False,
        }

        if tenant_ids_to_delete:
            deleted, _ = MemoryChunk.objects.filter(tenant_id__in=tenant_ids_to_delete).delete()
            stats["deleted_by_tenant"] = deleted
            logger.info("memory_gc_deleted_tenants", extra={"count": deleted})
            _increment_metric("memory_gc_deleted_tenant_total", deleted)

        if prune_missing_users:
            user_ids = list(User.objects.values_list("id", flat=True))
            deleted, _ = MemoryChunk.objects.exclude(tenant_id__in=user_ids).delete()
            stats["deleted_missing_users"] = deleted
            logger.info("memory_gc_deleted_missing_users", extra={"count": deleted})
            _increment_metric("memory_gc_deleted_missing_users_total", deleted)

        if retention_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            deleted = self._repository.delete_older_than(cutoff)
            stats["deleted_by_retention"] = deleted
            logger.info("memory_gc_deleted_retention", extra={"count": deleted})
            _increment_metric("memory_gc_deleted_retention_total", deleted)

        if reindex:
            stats["reindexed"] = self._reindex_vector_index()
            cache.set("memory_gc_last_reindex", stats["reindexed"], timeout=None)

        cache.set("memory_gc_last_run_at", datetime.now(timezone.utc).isoformat(), timeout=None)

        return stats

    def _reindex_vector_index(self) -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute("REINDEX INDEX memory_chunks_embedding_ivfflat")
            logger.info("memory_gc_reindex_complete")
            return True
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("memory_gc_reindex_failed", extra={"error": str(exc)})
            return False


def _increment_metric(key: str, amount: int) -> None:
    if amount <= 0:
        return
    try:
        cache.incr(key, amount)
    except Exception:
        try:
            current = cache.get(key, 0) or 0
            cache.set(key, current + amount, timeout=None)
        except Exception:  # pragma: no cover - best effort
            logger.debug("memory_gc_metric_update_failed", extra={"key": key})
