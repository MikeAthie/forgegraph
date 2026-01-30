import pytest

from application.services.embedding_service import CachedEmbeddingService, EmbeddingService


class FakeEmbedder(EmbeddingService):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(text))] for text in texts]

    def dimension(self) -> int:
        return 1


@pytest.mark.asyncio
async def test_cached_embedding_service_reuses_cache():
    embedder = FakeEmbedder()
    cached = CachedEmbeddingService(embedder)

    result1 = await cached.embed(["alpha", "beta"], model="m1")
    result2 = await cached.embed(["alpha", "beta"], model="m1")

    assert result1 == result2
    assert embedder.calls == [["alpha", "beta"]]
