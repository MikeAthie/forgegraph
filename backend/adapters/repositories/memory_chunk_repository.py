from __future__ import annotations

from datetime import datetime
from typing import Iterable

from django.db.models import QuerySet
from pgvector.django import CosineDistance

from infrastructure.orm.models import MemoryChunk


class MemoryChunkRepository:
    def bulk_create(self, chunks: Iterable[MemoryChunk]) -> list[MemoryChunk]:
        return MemoryChunk.objects.bulk_create(list(chunks))

    def by_tenant(self, tenant_id: str) -> QuerySet[MemoryChunk]:
        return MemoryChunk.objects.filter(tenant_id=tenant_id)

    def search(
        self,
        *,
        tenant_id: str,
        embedding: list[float],
        agent_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> QuerySet[MemoryChunk]:
        qs = MemoryChunk.objects.filter(tenant_id=tenant_id)
        if agent_id:
            qs = qs.filter(agent_id=agent_id)
        if run_id:
            qs = qs.filter(run_id=run_id)
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs.annotate(similarity=1 - CosineDistance("embedding", embedding)).order_by(
            "-similarity"
        )[:top_k]

    def delete_older_than(self, cutoff: datetime) -> int:
        deleted, _ = MemoryChunk.objects.filter(source_timestamp__lt=cutoff).delete()
        return deleted
