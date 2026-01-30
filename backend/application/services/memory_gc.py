from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from django.db import connection

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from infrastructure.orm.models import MemoryChunk

logger = logging.getLogger(__name__)


class MemoryGCService:
    def __init__(self, repository: MemoryChunkRepository | None = None) -> None:
        self._repository = repository or MemoryChunkRepository()

    def cleanup(
        self,
        *,
        retention_days: int,
        tenant_ids_to_delete: list[str] | None = None,
        reindex: bool = False,
    ) -> dict[str, int | bool]:
        stats: dict[str, int | bool] = {
            "deleted_by_retention": 0,
            "deleted_by_tenant": 0,
            "reindexed": False,
        }

        if tenant_ids_to_delete:
            deleted, _ = MemoryChunk.objects.filter(tenant_id__in=tenant_ids_to_delete).delete()
            stats["deleted_by_tenant"] = deleted
            logger.info("memory_gc_deleted_tenants", extra={"count": deleted})

        if retention_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            deleted = self._repository.delete_older_than(cutoff)
            stats["deleted_by_retention"] = deleted
            logger.info("memory_gc_deleted_retention", extra={"count": deleted})

        if reindex:
            stats["reindexed"] = self._reindex_vector_index()

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
