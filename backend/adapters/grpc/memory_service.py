from __future__ import annotations

import asyncio
import json
import logging

from django.core.cache import cache

from adapters.embedding.openai_embedder import OpenAIEmbedder
from application.services.embedding_service import CachedEmbeddingService
from application.services.vector_search_service import VectorSearchService
from infrastructure.grpc import engine_pb2, engine_pb2_grpc

logger = logging.getLogger(__name__)


class MemoryService(engine_pb2_grpc.MemoryServiceServicer):
    def __init__(self, search_service: VectorSearchService | None = None) -> None:
        if search_service is None:
            embedder = CachedEmbeddingService(OpenAIEmbedder())
            search_service = VectorSearchService(embedder)
        self._search_service = search_service

    def RetrieveMemory(self, request, context):
        _increment_metric("memory_grpc_requests_total", 1)
        if not request.tenant_id or not request.query:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2.RetrieveMemoryResponse(
                error="tenant_id and query are required"
            )

        try:
            results = asyncio.run(
                self._search_service.search(
                    tenant_id=request.tenant_id,
                    query=request.query,
                    agent_id=request.agent_id or None,
                    run_id=request.run_id or None,
                    session_id=request.session_id or None,
                    top_k=request.top_k or 5,
                    threshold=request.threshold or 0.5,
                    recency_weight=request.recency_weight or 0.2,
                    model=request.embedding_model or None,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("memory_retrieve_failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2.RetrieveMemoryResponse(error=str(exc))

        chunks = []
        for result in results:
            chunks.append(
                engine_pb2.MemoryChunk(
                    content=result.content,
                    score=float(result.similarity),
                    source_timestamp=result.source_timestamp.isoformat(),
                    metadata_json=json.dumps(result.metadata or {}),
                )
            )

        return engine_pb2.RetrieveMemoryResponse(chunks=chunks)


def _increment_metric(key: str, amount: int) -> None:
    try:
        cache.incr(key, amount)
    except Exception:
        current = cache.get(key, 0) or 0
        cache.set(key, current + amount, timeout=None)
