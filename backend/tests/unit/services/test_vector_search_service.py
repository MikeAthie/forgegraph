from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from application.services.embedding_service import EmbeddingService
from application.services.vector_search_service import VectorSearchService


class FakeEmbedder(EmbeddingService):
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def dimension(self) -> int:
        return 3


@dataclass
class FakeChunk:
    content: str
    similarity: float
    source_timestamp: datetime
    metadata: dict[str, Any]


class FakeRepository(MemoryChunkRepository):
    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks

    def search(self, **kwargs: Any) -> list[FakeChunk]:  # type: ignore[override]
        return self._chunks


class TestThresholdFiltering:
    @pytest.mark.asyncio
    async def test_filters_below_threshold(self):
        """Results below threshold should be excluded even with high recency."""
        now = datetime.now(UTC)
        chunks = [
            FakeChunk("high_sim", 0.9, now - timedelta(days=30), {}),  # Above threshold, old
            FakeChunk("low_sim", 0.5, now, {}),  # Below threshold, very recent
        ]

        service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            recency_weight=0.9,  # High recency weight
        )

        # Should only get the high-similarity result
        assert len(results) == 1
        assert results[0].similarity == 0.9

    @pytest.mark.asyncio
    async def test_threshold_applies_to_raw_similarity(self):
        """Threshold should apply to similarity, not combined score."""
        now = datetime.now(UTC)
        chunk = FakeChunk(
            "below_threshold",
            0.65,  # Just below 0.7 threshold
            now,  # Max recency
            {},
        )

        service = VectorSearchService(FakeEmbedder(), FakeRepository([chunk]))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            recency_weight=0.5,
        )

        # Combined would be 0.5*0.65 + 0.5*1.0 = 0.825
        # But should still be filtered because similarity < threshold
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_all_above_threshold_returned(self):
        """All results above threshold should be considered for ranking."""
        now = datetime.now(UTC)
        chunks = [
            FakeChunk("a", 0.8, now, {}),
            FakeChunk("b", 0.75, now, {}),
            FakeChunk("c", 0.71, now, {}),
        ]

        service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            top_k=10,
        )

        assert len(results) == 3


class TestRecencyScoring:
    @pytest.mark.asyncio
    async def test_recent_chunks_boosted(self):
        """Recent chunks should rank higher with recency weight."""
        now = datetime.now(UTC)
        chunks = [
            FakeChunk("old", 0.8, now - timedelta(days=7), {}),
            FakeChunk("recent", 0.8, now, {}),  # Same similarity, more recent
        ]

        service = VectorSearchService(
            FakeEmbedder(), FakeRepository(chunks), recency_decay_hours=168.0
        )
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            recency_weight=0.3,
        )

        # More recent should rank first
        assert results[0].content == "recent"

    def test_recency_decay_at_zero(self):
        """At t=0, recency should be 1.0."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))
        now = datetime.now(UTC)

        recency = service._calculate_recency(now, now)
        assert recency == pytest.approx(1.0)

    def test_recency_decay_at_half_life(self):
        """At t=half_life (168 hours = 1 week), recency should be 0.5."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]), recency_decay_hours=168.0)
        now = datetime.now(UTC)
        one_week_ago = now - timedelta(hours=168)

        recency = service._calculate_recency(one_week_ago, now)
        assert recency == pytest.approx(0.5)

    def test_recency_decay_at_double_half_life(self):
        """At t=2*half_life, recency should be 0.25."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]), recency_decay_hours=168.0)
        now = datetime.now(UTC)
        two_weeks_ago = now - timedelta(hours=336)

        recency = service._calculate_recency(two_weeks_ago, now)
        assert recency == pytest.approx(0.25)

    def test_recency_with_none_timestamp(self):
        """Missing timestamp should return default 0.5."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))
        now = datetime.now(UTC)

        recency = service._calculate_recency(None, now)
        assert recency == 0.5


class TestCombinedScoring:
    def test_score_combination_fifty_fifty(self):
        """Test weighted combination of scores at 50/50."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))

        combined = service._combine_scores(
            similarity=0.8,
            recency=0.6,
            recency_weight=0.5,
        )
        assert combined == pytest.approx(0.7)

    def test_score_combination_no_recency(self):
        """No recency weight means pure similarity."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))

        combined = service._combine_scores(
            similarity=0.8,
            recency=0.6,
            recency_weight=0.0,
        )
        assert combined == pytest.approx(0.8)

    def test_score_combination_full_recency(self):
        """Full recency weight means pure recency."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))

        combined = service._combine_scores(
            similarity=0.8,
            recency=0.6,
            recency_weight=1.0,
        )
        assert combined == pytest.approx(0.6)


class TestResultOrdering:
    @pytest.mark.asyncio
    async def test_results_sorted_by_combined_score(self):
        """Results should be sorted by combined score, not raw similarity."""
        now = datetime.now(UTC)
        chunks = [
            FakeChunk("old_high_sim", 0.95, now - timedelta(days=14), {}),
            FakeChunk("recent_lower_sim", 0.8, now, {}),
        ]

        service = VectorSearchService(
            FakeEmbedder(), FakeRepository(chunks), recency_decay_hours=168.0
        )
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            recency_weight=0.4,  # Significant recency weight
        )

        # With 40% recency weight:
        # old_high_sim: 0.6 * 0.95 + 0.4 * 0.25 = 0.57 + 0.1 = 0.67
        # recent_lower_sim: 0.6 * 0.8 + 0.4 * 1.0 = 0.48 + 0.4 = 0.88
        # Recent should be first despite lower raw similarity
        assert results[0].content == "recent_lower_sim"

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self):
        """top_k should limit the number of returned results."""
        now = datetime.now(UTC)
        chunks = [FakeChunk(f"chunk_{i}", 0.9, now, {}) for i in range(10)]

        service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            top_k=3,
        )

        assert len(results) == 3


class TestResultFields:
    @pytest.mark.asyncio
    async def test_result_includes_all_scores(self):
        """Each result should include similarity, recency, and combined scores."""
        now = datetime.now(UTC)
        chunks = [FakeChunk("test", 0.85, now, {"key": "value"})]

        service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
            recency_weight=0.2,
        )

        assert len(results) == 1
        result = results[0]

        # Check all fields are present
        assert result.similarity == 0.85
        assert result.recency_score == pytest.approx(1.0)  # Just now
        assert result.combined_score == pytest.approx(0.8 * 0.85 + 0.2 * 1.0)
        assert result.content == "test"
        assert result.metadata == {"key": "value"}


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        """Empty query should return empty results."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))
        results = await service.search(
            tenant_id="tenant",
            query="   ",  # Whitespace only
            threshold=0.7,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_no_results_from_repository(self):
        """No candidates from repository should return empty."""
        service = VectorSearchService(FakeEmbedder(), FakeRepository([]))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_all_filtered_returns_empty(self):
        """If all candidates are below threshold, return empty."""
        now = datetime.now(UTC)
        chunks = [
            FakeChunk("a", 0.3, now, {}),
            FakeChunk("b", 0.4, now, {}),
        ]

        service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
        results = await service.search(
            tenant_id="tenant",
            query="test",
            threshold=0.7,
        )
        assert results == []
