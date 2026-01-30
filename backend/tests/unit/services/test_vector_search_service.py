from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

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
    metadata: dict


class FakeRepository:
    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks

    def search(self, **kwargs):
        return self._chunks


@pytest.mark.asyncio
async def test_vector_search_filters_by_threshold():
    now = datetime.now(timezone.utc)
    chunks = [
        FakeChunk("keep", 0.9, now, {}),
        FakeChunk("drop", 0.4, now, {}),
    ]
    service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
    results = await service.search(
        tenant_id="tenant",
        query="q",
        top_k=5,
        threshold=0.5,
    )
    assert [r.content for r in results] == ["keep"]


@pytest.mark.asyncio
async def test_vector_search_recency_weight():
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=7)
    chunks = [
        FakeChunk("recent", 0.6, now, {}),
        FakeChunk("old", 0.7, older, {}),
    ]
    service = VectorSearchService(FakeEmbedder(), FakeRepository(chunks))
    results = await service.search(
        tenant_id="tenant",
        query="q",
        top_k=2,
        threshold=0.0,
        recency_weight=0.6,
    )
    assert results[0].content == "recent"
