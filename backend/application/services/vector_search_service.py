from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from application.services.embedding_service import EmbeddingService


@dataclass
class MemorySearchResult:
    """Result from vector similarity search."""

    content: str
    similarity: float  # Raw cosine similarity (0-1)
    recency_score: float  # Time-based recency (0-1)
    combined_score: float  # Weighted combination for ranking
    source_timestamp: datetime
    metadata: dict[str, Any]


class VectorSearchService:
    """
    Service for semantic memory retrieval.

    Implements hybrid ranking combining:
    1. Cosine similarity from vector search
    2. Recency boost for recent memories

    Filtering Strategy:
    - Threshold is applied to RAW SIMILARITY before ranking
    - This ensures only semantically relevant results are considered
    - Recency boost can then re-order but not include irrelevant results
    """

    def __init__(
        self,
        embedder: EmbeddingService,
        repository: MemoryChunkRepository | None = None,
        recency_decay_hours: float = 168.0,  # 1 week half-life
    ) -> None:
        self._embedder = embedder
        self._repository = repository or MemoryChunkRepository()
        self._recency_decay_hours = recency_decay_hours

    async def search(
        self,
        *,
        tenant_id: str | UUID,
        query: str,
        agent_id: str | UUID | None = None,
        run_id: str | UUID | None = None,
        session_id: str | UUID | None = None,
        top_k: int = 5,
        threshold: float = 0.7,
        recency_weight: float = 0.2,
        model: str | None = None,
    ) -> list[MemorySearchResult]:
        """
        Search for relevant memory chunks.

        Args:
            tenant_id: Tenant ID for isolation
            query: Search query text
            agent_id: Optional agent ID filter
            run_id: Optional run ID filter
            session_id: Optional session ID filter
            top_k: Maximum results to return
            threshold: Minimum similarity score (0-1) BEFORE recency weighting.
                      Results below this threshold are excluded regardless of recency.
            recency_weight: Weight for recency in combined score (0-1).
                           0.0 = pure similarity, 1.0 = pure recency.
            model: Optional embedding model override

        Returns:
            List of MemorySearchResult sorted by combined score
        """
        if not query.strip():
            return []

        # 1. Embed query
        vectors = await self._embedder.embed([query], model=model)
        if not vectors:
            return []

        embedding = vectors[0]

        # 2. Vector search with overfetch for filtering
        # Fetch extra candidates since some will be filtered by threshold
        fetch_count = max(top_k * 3, top_k + 10)

        candidates = list(
            self._repository.search(
                tenant_id=str(tenant_id) if isinstance(tenant_id, UUID) else tenant_id,
                agent_id=str(agent_id) if isinstance(agent_id, UUID) else agent_id,
                run_id=str(run_id) if isinstance(run_id, UUID) else run_id,
                session_id=str(session_id) if isinstance(session_id, UUID) else session_id,
                embedding=embedding,
                top_k=fetch_count,
            )
        )

        if not candidates:
            return []

        # 3. Filter by similarity threshold FIRST
        # This ensures only semantically relevant results are considered
        filtered = []
        for chunk in candidates:
            similarity = getattr(chunk, "similarity", 0.0) or 0.0
            if similarity >= threshold:
                filtered.append((chunk, similarity))

        if not filtered:
            return []

        # 4. Calculate recency scores and combine
        now = datetime.now(UTC)
        results: list[MemorySearchResult] = []

        for chunk, similarity in filtered:
            recency = self._calculate_recency(chunk.source_timestamp, now)
            combined = self._combine_scores(
                similarity=similarity,
                recency=recency,
                recency_weight=recency_weight,
            )

            results.append(
                MemorySearchResult(
                    content=chunk.content,
                    similarity=similarity,
                    recency_score=recency,
                    combined_score=combined,
                    source_timestamp=chunk.source_timestamp,
                    metadata=chunk.metadata or {},
                )
            )

        # 5. Sort by combined score and return top_k
        results.sort(key=lambda r: r.combined_score, reverse=True)
        return results[:top_k]

    def _calculate_recency(self, timestamp: datetime | None, now: datetime) -> float:
        """
        Calculate recency score with exponential decay.

        Score of 1.0 for current time, decaying with half-life of recency_decay_hours.
        At half_life hours, score = 0.5
        At 2*half_life hours, score = 0.25
        """
        if timestamp is None:
            return 0.5  # Default for missing timestamp

        # Make timestamp timezone-aware if it isn't
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        age_hours = max((now - timestamp).total_seconds() / 3600.0, 0.0)

        # Exponential decay: score = 0.5^(age / half_life)
        decay_factor = age_hours / self._recency_decay_hours
        return math.pow(0.5, decay_factor)

    def _combine_scores(
        self,
        similarity: float,
        recency: float,
        recency_weight: float,
    ) -> float:
        """
        Combine similarity and recency scores.

        combined = (1 - recency_weight) * similarity + recency_weight * recency
        """
        sim_weight = 1.0 - recency_weight
        return (sim_weight * similarity) + (recency_weight * recency)
