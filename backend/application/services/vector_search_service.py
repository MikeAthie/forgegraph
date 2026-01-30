from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from application.services.embedding_service import EmbeddingService


@dataclass
class MemorySearchResult:
    content: str
    similarity: float
    source_timestamp: datetime
    metadata: dict


class VectorSearchService:
    def __init__(
        self,
        embedder: EmbeddingService,
        repository: MemoryChunkRepository | None = None,
    ) -> None:
        self._embedder = embedder
        self._repository = repository or MemoryChunkRepository()

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        top_k: int = 5,
        threshold: float = 0.5,
        recency_weight: float = 0.2,
        model: str | None = None,
    ) -> list[MemorySearchResult]:
        if not query.strip():
            return []

        vectors = await self._embedder.embed([query], model=model)
        if not vectors:
            return []

        embedding = vectors[0]
        candidates = list(
            self._repository.search(
                tenant_id=tenant_id,
                agent_id=agent_id,
                run_id=run_id,
                session_id=session_id,
                embedding=embedding,
                top_k=max(top_k * 3, top_k),
            )
        )

        if not candidates:
            return []

        now = datetime.now(timezone.utc)
        scored = []
        for chunk in candidates:
            similarity = getattr(chunk, "similarity", 0.0) or 0.0
            age_seconds = max((now - chunk.source_timestamp).total_seconds(), 0.0)
            recency_score = 1.0 / (1.0 + age_seconds / 3600.0)
            combined = (1 - recency_weight) * similarity + recency_weight * recency_score
            scored.append((combined, similarity, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[MemorySearchResult] = []
        for combined, similarity, chunk in scored[:top_k]:
            if similarity < threshold:
                continue
            results.append(
                MemorySearchResult(
                    content=chunk.content,
                    similarity=combined,
                    source_timestamp=chunk.source_timestamp,
                    metadata=chunk.metadata or {},
                )
            )

        return results
