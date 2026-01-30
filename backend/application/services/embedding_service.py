from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EmbeddingRequest:
    texts: list[str]
    model: str


class EmbeddingService(ABC):
    @abstractmethod
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError


class EmbeddingCache:
    """Simple in-memory cache for embeddings."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], list[float]] = {}
        self._lock = asyncio.Lock()

    async def get_many(self, model: str, texts: Iterable[str]) -> dict[str, list[float]]:
        async with self._lock:
            return {text: self._cache[(model, text)] for text in texts if (model, text) in self._cache}

    async def set_many(self, model: str, embeddings: dict[str, list[float]]) -> None:
        async with self._lock:
            for text, vector in embeddings.items():
                self._cache[(model, text)] = vector


class CachedEmbeddingService(EmbeddingService):
    def __init__(self, delegate: EmbeddingService, cache: EmbeddingCache | None = None) -> None:
        self._delegate = delegate
        self._cache = cache or EmbeddingCache()

    def dimension(self) -> int:
        return self._delegate.dimension()

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        model_name = model or ""

        cached = await self._cache.get_many(model_name, texts)
        missing = [text for text in texts if text not in cached]
        if missing:
            vectors = await self._delegate.embed(missing, model=model)
            await self._cache.set_many(model_name, dict(zip(missing, vectors, strict=True)))
            cached = await self._cache.get_many(model_name, texts)

        return [cached[text] for text in texts]


class RateLimiter:
    """Cooperative rate limiter with a minimum delay between batches."""

    def __init__(self, min_interval_seconds: float = 0.0) -> None:
        self._min_interval = max(min_interval_seconds, 0.0)
        self._lock = asyncio.Lock()
        self._last_time: float | None = None

    async def throttle(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = asyncio.get_event_loop().time()
            if self._last_time is None:
                self._last_time = now
                return
            elapsed = now - self._last_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_time = asyncio.get_event_loop().time()
