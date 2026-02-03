from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class CacheStats:
    """Statistics for the embedding cache."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class BoundedEmbeddingCache:
    """
    Thread-safe LRU cache for embeddings with bounded size.

    Evicts least recently used entries when capacity is reached.
    Cache key is (model, text_hash) to handle different embedding models.
    """

    def __init__(self, max_size: int = 10000):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of embeddings to cache.
                      Default 10000 = ~60MB for 1536-dim embeddings.
        """
        self._cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._stats = CacheStats(max_size=max_size)

    async def get(self, model: str, text: str) -> list[float] | None:
        """Get cached embedding, updating access order."""
        key = self._make_key(model, text)

        async with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._stats.hits += 1
                return self._cache[key]

            self._stats.misses += 1
            return None

    async def get_many(self, model: str, texts: list[str]) -> dict[str, list[float]]:
        """Get multiple cached embeddings."""
        results: dict[str, list[float]] = {}

        async with self._lock:
            for text in texts:
                key = self._make_key(model, text)
                if key in self._cache:
                    self._cache.move_to_end(key)
                    results[text] = self._cache[key]
                    self._stats.hits += 1
                else:
                    self._stats.misses += 1

        return results

    async def set(self, model: str, text: str, embedding: list[float]) -> None:
        """Cache embedding, evicting LRU if at capacity."""
        key = self._make_key(model, text)

        async with self._lock:
            # If already exists, update and move to end
            if key in self._cache:
                self._cache[key] = embedding
                self._cache.move_to_end(key)
                return

            # Add new entry
            self._cache[key] = embedding

            # Evict LRU entries if over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
                self._stats.evictions += 1

            self._stats.size = len(self._cache)

    async def set_many(self, model: str, items: dict[str, list[float]]) -> None:
        """Cache multiple embeddings."""
        async with self._lock:
            for text, embedding in items.items():
                key = self._make_key(model, text)

                if key in self._cache:
                    self._cache[key] = embedding
                    self._cache.move_to_end(key)
                else:
                    self._cache[key] = embedding

            # Evict after batch insert
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
                self._stats.evictions += 1

            self._stats.size = len(self._cache)

    async def clear(self) -> None:
        """Clear all cached embeddings."""
        async with self._lock:
            self._cache.clear()
            self._stats.size = 0

    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        async with self._lock:
            self._stats.size = len(self._cache)
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                size=self._stats.size,
                max_size=self._stats.max_size,
            )

    def _make_key(self, model: str, text: str) -> tuple[str, str]:
        """Create cache key from model and text."""
        # Use hash for long texts to save memory on keys
        if len(text) > 100:
            text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            return (model, text_hash)
        return (model, text)
