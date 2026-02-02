from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from application.services.embedding_service import EmbeddingService, RateLimiter


class OpenAIEmbedder(EmbeddingService):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-ada-002",
        batch_size: int = 100,
        min_interval_seconds: float = 0.0,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._batch_size = max(1, batch_size)
        self._limiter = RateLimiter(min_interval_seconds)

    def dimension(self) -> int:
        return 1536

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        selected_model = model or self._model
        results: list[list[float]] = []

        for batch in _batch(texts, self._batch_size):
            await self._limiter.throttle()
            response = await asyncio.to_thread(self._request_embeddings, batch, selected_model)
            results.extend(response)

        return results

    def _request_embeddings(self, texts: list[str], model: str) -> list[list[float]]:
        payload = {"model": model, "input": texts}
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI embedding error: {exc.read().decode('utf-8')}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI embedding request failed: {exc}") from exc

        data_items = payload.get("data", [])
        embeddings: list[list[float]] = []
        for item in data_items:
            vector = item.get("embedding")
            if not isinstance(vector, list):
                raise RuntimeError("OpenAI embedding response missing embedding vectors")
            embeddings.append(vector)
        return embeddings


def _batch(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]
