import asyncio

import pytest

from application.services.embedding_cache import BoundedEmbeddingCache


@pytest.fixture
def cache():
    return BoundedEmbeddingCache(max_size=5)


class TestBoundedCache:
    @pytest.mark.asyncio
    async def test_basic_get_set(self, cache):
        embedding = [0.1, 0.2, 0.3]
        await cache.set("model", "hello", embedding)

        result = await cache.get("model", "hello")
        assert result == embedding

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        result = await cache.get("model", "unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        # Fill cache
        for i in range(5):
            await cache.set("model", f"text{i}", [float(i)])

        # Access text0 to make it recent
        await cache.get("model", "text0")

        # Add new item, should evict text1 (oldest not accessed)
        await cache.set("model", "text5", [5.0])

        # text0 should still exist (was accessed)
        assert await cache.get("model", "text0") is not None

        # text1 should be evicted
        assert await cache.get("model", "text1") is None

        # text5 should exist
        assert await cache.get("model", "text5") is not None

    @pytest.mark.asyncio
    async def test_eviction_count(self, cache):
        for i in range(10):
            await cache.set("model", f"text{i}", [float(i)])

        stats = await cache.get_stats()
        assert stats.evictions == 5
        assert stats.size == 5

    @pytest.mark.asyncio
    async def test_different_models_separate_keys(self, cache):
        await cache.set("model1", "hello", [1.0])
        await cache.set("model2", "hello", [2.0])

        assert await cache.get("model1", "hello") == [1.0]
        assert await cache.get("model2", "hello") == [2.0]

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        async def writer(n):
            for i in range(100):
                await cache.set("model", f"text{n}_{i}", [float(i)])

        async def reader(n):
            for i in range(100):
                await cache.get("model", f"text{n}_{i}")

        tasks = [writer(i) for i in range(5)] + [reader(i) for i in range(5)]
        await asyncio.gather(*tasks)

        stats = await cache.get_stats()
        assert stats.size <= 5  # Should respect max_size

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        await cache.set("model", "text1", [1.0])
        await cache.get("model", "text1")  # Hit
        await cache.get("model", "text2")  # Miss

        stats = await cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.hit_rate == 0.5

    @pytest.mark.asyncio
    async def test_get_many(self, cache):
        await cache.set("model", "a", [1.0])
        await cache.set("model", "b", [2.0])

        results = await cache.get_many("model", ["a", "b", "c"])

        assert results["a"] == [1.0]
        assert results["b"] == [2.0]
        assert "c" not in results

    @pytest.mark.asyncio
    async def test_set_many(self, cache):
        items = {"a": [1.0], "b": [2.0], "c": [3.0]}
        await cache.set_many("model", items)

        assert await cache.get("model", "a") == [1.0]
        assert await cache.get("model", "b") == [2.0]
        assert await cache.get("model", "c") == [3.0]

    @pytest.mark.asyncio
    async def test_set_many_eviction(self, cache):
        # Add 8 items at once to a cache with max_size=5
        items = {f"text{i}": [float(i)] for i in range(8)}
        await cache.set_many("model", items)

        stats = await cache.get_stats()
        assert stats.size == 5
        assert stats.evictions == 3

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("model", "a", [1.0])
        await cache.set("model", "b", [2.0])

        await cache.clear()

        assert await cache.get("model", "a") is None
        assert await cache.get("model", "b") is None

        stats = await cache.get_stats()
        assert stats.size == 0

    @pytest.mark.asyncio
    async def test_update_existing_moves_to_end(self, cache):
        # Fill cache
        for i in range(5):
            await cache.set("model", f"text{i}", [float(i)])

        # Update text0 (should move it to end)
        await cache.set("model", "text0", [100.0])

        # Add new item, should evict text1 (now oldest)
        await cache.set("model", "new", [999.0])

        # text0 should still exist with new value
        assert await cache.get("model", "text0") == [100.0]

        # text1 should be evicted
        assert await cache.get("model", "text1") is None

    @pytest.mark.asyncio
    async def test_long_text_hashing(self):
        cache = BoundedEmbeddingCache(max_size=10)

        long_text = "x" * 200  # Over 100 chars
        await cache.set("model", long_text, [1.0, 2.0])

        result = await cache.get("model", long_text)
        assert result == [1.0, 2.0]

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self, cache):
        # 3 hits, 2 misses = 60% hit rate
        await cache.set("model", "a", [1.0])
        await cache.get("model", "a")  # hit
        await cache.get("model", "a")  # hit
        await cache.get("model", "a")  # hit
        await cache.get("model", "b")  # miss
        await cache.get("model", "c")  # miss

        stats = await cache.get_stats()
        assert stats.hits == 3
        assert stats.misses == 2
        assert stats.hit_rate == pytest.approx(0.6)
