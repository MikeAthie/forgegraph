from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db import connection

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from infrastructure.orm.models import MemoryChunk, MemoryEntry, Organization

logger = logging.getLogger(__name__)


@dataclass
class GCResult:
    """Result of a garbage collection operation."""

    chunks_deleted: int = 0
    entries_deleted: int = 0
    orphaned_tenant_ids: list[UUID] = field(default_factory=list)
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


class MemoryGCService:
    """
    Garbage collection service for memory system.

    Handles cleanup of:
    - Expired memory entries (TTL-based)
    - Orphaned chunks (non-organization tenants from legacy data)
    - Old chunks beyond retention period
    """

    def __init__(
        self,
        repository: MemoryChunkRepository | None = None,
        chunk_retention_days: int = 90,
        entry_retention_days: int = 30,
        batch_size: int = 1000,
    ) -> None:
        self._repository = repository or MemoryChunkRepository()
        self.chunk_retention_days = chunk_retention_days
        self.entry_retention_days = entry_retention_days
        self.batch_size = batch_size

    def get_valid_tenant_ids(self) -> set[UUID]:
        """
        Get all valid canonical tenant IDs.

        Memory chunks are organization-scoped in the current architecture.
        Older user- and graph-scoped chunk rows are treated as legacy data and
        should be cleaned up as orphans.
        """
        organization_ids = set(Organization.objects.values_list("id", flat=True))
        logger.info(
            "Found valid tenant IDs",
            extra={
                "organization_count": len(organization_ids),
                "total": len(organization_ids),
            },
        )
        return organization_ids

    def find_orphaned_tenant_ids(self) -> list[UUID]:
        """Find chunk tenant IDs that do not map to a real organization."""
        valid_ids = self.get_valid_tenant_ids()

        # Get unique tenant IDs from chunks
        chunk_tenant_ids = set(MemoryChunk.objects.values_list("tenant_id", flat=True).distinct())

        # Find orphans
        orphaned = chunk_tenant_ids - valid_ids
        return list(orphaned)

    def cleanup_orphaned_chunks(
        self,
        tenant_ids: list[UUID] | None = None,
        dry_run: bool = False,
    ) -> GCResult:
        """
        Delete memory chunks for orphaned tenants.

        Args:
            tenant_ids: Specific tenant IDs to delete. If None, auto-detects orphans.
            dry_run: If True, only report what would be deleted.

        Returns:
            GCResult with deletion counts and any errors.
        """
        result = GCResult(dry_run=dry_run)

        # Auto-detect orphans if not specified
        if tenant_ids is None:
            tenant_ids = self.find_orphaned_tenant_ids()

        if not tenant_ids:
            logger.info("No orphaned tenant IDs found")
            return result

        result.orphaned_tenant_ids = list(tenant_ids)

        # Safety check: don't delete if it's a large percentage
        total_chunks = MemoryChunk.objects.count()
        orphan_chunks = MemoryChunk.objects.filter(tenant_id__in=tenant_ids).count()

        if total_chunks > 0 and orphan_chunks / total_chunks > 0.5:
            error_msg = (
                f"Safety check failed: {orphan_chunks}/{total_chunks} chunks "
                f"({orphan_chunks / total_chunks * 100:.1f}%) would be deleted. "
                "This seems too high - please investigate manually."
            )
            logger.error(error_msg)
            result.errors.append(error_msg)
            return result

        logger.warning(
            "Preparing to delete orphaned chunks",
            extra={
                "orphan_count": orphan_chunks,
                "tenant_count": len(tenant_ids),
                "dry_run": dry_run,
            },
        )

        if dry_run:
            result.chunks_deleted = orphan_chunks
            return result

        # Delete in batches to avoid long locks
        deleted_total = 0
        for tenant_id in tenant_ids:
            deleted = self._delete_chunks_for_tenant(tenant_id)
            deleted_total += deleted

        result.chunks_deleted = deleted_total
        logger.info(f"Deleted {deleted_total} orphaned chunks")
        _increment_metric("memory_gc_deleted_orphaned_total", deleted_total)
        return result

    def _delete_chunks_for_tenant(self, tenant_id: UUID) -> int:
        """Delete all chunks for a specific tenant in batches."""
        deleted_total = 0

        while True:
            # Get batch of IDs to delete
            chunk_ids = list(
                MemoryChunk.objects.filter(tenant_id=tenant_id).values_list("id", flat=True)[
                    : self.batch_size
                ]
            )

            if not chunk_ids:
                break

            # Delete batch
            deleted, _ = MemoryChunk.objects.filter(id__in=chunk_ids).delete()
            deleted_total += deleted

            logger.debug(f"Deleted batch of {deleted} chunks for tenant {tenant_id}")

        return deleted_total

    def cleanup_expired_entries(self, dry_run: bool = False) -> GCResult:
        """Delete memory entries that have expired based on their TTL."""
        result = GCResult(dry_run=dry_run)

        now = datetime.now(UTC)
        expired_qs = MemoryEntry.objects.filter(expires_at__lt=now)
        count = expired_qs.count()

        if dry_run:
            result.entries_deleted = count
            return result

        # Delete in batches
        deleted_total = 0
        while True:
            batch_ids = list(expired_qs.values_list("id", flat=True)[: self.batch_size])
            if not batch_ids:
                break

            deleted, _ = MemoryEntry.objects.filter(id__in=batch_ids).delete()
            deleted_total += deleted

        result.entries_deleted = deleted_total
        logger.info(f"Deleted {deleted_total} expired memory entries")
        _increment_metric("memory_gc_deleted_expired_entries_total", deleted_total)
        return result

    def cleanup_old_chunks(
        self,
        max_age_days: int | None = None,
        dry_run: bool = False,
    ) -> GCResult:
        """Delete chunks older than the retention period."""
        result = GCResult(dry_run=dry_run)

        if max_age_days is None:
            max_age_days = self.chunk_retention_days

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        old_qs = MemoryChunk.objects.filter(created_at__lt=cutoff)
        count = old_qs.count()

        logger.info(
            f"Found {count} chunks older than {max_age_days} days",
            extra={"cutoff": cutoff.isoformat()},
        )

        if dry_run:
            result.chunks_deleted = count
            return result

        # Delete in batches
        deleted_total = 0
        while True:
            batch_ids = list(old_qs.values_list("id", flat=True)[: self.batch_size])
            if not batch_ids:
                break

            deleted, _ = MemoryChunk.objects.filter(id__in=batch_ids).delete()
            deleted_total += deleted

        result.chunks_deleted = deleted_total
        logger.info(f"Deleted {deleted_total} old chunks")
        _increment_metric("memory_gc_deleted_retention_total", deleted_total)
        return result

    def reindex_vectors(self) -> bool:
        """
        Rebuild vector index for better performance.

        Note: This can be slow on large tables. Consider running during low-traffic periods.
        """
        logger.info("Starting vector index reindex")

        try:
            with connection.cursor() as cursor:
                # Check if index exists
                cursor.execute(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'memory_chunks'
                    AND indexname = 'memory_chunks_embedding_ivfflat'
                    """
                )
                if cursor.fetchone():
                    cursor.execute("REINDEX INDEX memory_chunks_embedding_ivfflat")
                    logger.info("Vector index reindexed successfully")
                    return True
                else:
                    logger.warning("Vector index not found, skipping reindex")
                    return False
        except Exception as exc:
            logger.warning("memory_gc_reindex_failed", extra={"error": str(exc)})
            return False

    def run_full_gc(self, dry_run: bool = False) -> dict[str, Any]:
        """
        Run complete garbage collection cycle.

        Returns summary of all operations.
        """
        logger.info("Starting full GC cycle", extra={"dry_run": dry_run})

        results = {
            "expired_entries": self.cleanup_expired_entries(dry_run=dry_run),
            "orphaned_chunks": self.cleanup_orphaned_chunks(dry_run=dry_run),
            "old_chunks": self.cleanup_old_chunks(dry_run=dry_run),
        }

        total_deleted = sum(r.chunks_deleted + r.entries_deleted for r in results.values())

        logger.info(
            "GC cycle complete",
            extra={
                "total_deleted": total_deleted,
                "dry_run": dry_run,
            },
        )

        cache.set("memory_gc_last_run_at", datetime.now(UTC).isoformat(), timeout=None)

        return {
            "dry_run": dry_run,
            "expired_entries_deleted": results["expired_entries"].entries_deleted,
            "orphaned_chunks_deleted": results["orphaned_chunks"].chunks_deleted,
            "orphaned_tenant_ids": [
                str(tid) for tid in results["orphaned_chunks"].orphaned_tenant_ids
            ],
            "old_chunks_deleted": results["old_chunks"].chunks_deleted,
            "total_deleted": total_deleted,
            "errors": [e for r in results.values() for e in r.errors],
        }

    # Legacy method for backward compatibility
    def cleanup(
        self,
        *,
        retention_days: int,
        tenant_ids_to_delete: list[str] | None = None,
        prune_missing_users: bool = False,
        reindex: bool = False,
    ) -> dict[str, int | bool]:
        """
        Legacy cleanup method maintained for backward compatibility.

        For new code, prefer using run_full_gc() or individual cleanup methods.
        """
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
            # Compatibility path: prune any chunk rows that are not owned by
            # a real organization tenant under the current architecture.
            valid_ids = self.get_valid_tenant_ids()
            deleted, _ = MemoryChunk.objects.exclude(tenant_id__in=valid_ids).delete()
            stats["deleted_missing_users"] = deleted
            logger.info("memory_gc_deleted_orphaned", extra={"count": deleted})
            _increment_metric("memory_gc_deleted_orphaned_total", deleted)

        if retention_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=retention_days)
            deleted = self._repository.delete_older_than(cutoff)
            stats["deleted_by_retention"] = deleted
            logger.info("memory_gc_deleted_retention", extra={"count": deleted})
            _increment_metric("memory_gc_deleted_retention_total", deleted)

        if reindex:
            stats["reindexed"] = self.reindex_vectors()
            cache.set("memory_gc_last_reindex", stats["reindexed"], timeout=None)

        cache.set("memory_gc_last_run_at", datetime.now(UTC).isoformat(), timeout=None)

        return stats


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
