from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar, cast

from django.core.cache import cache

from adapters.embedding.openai_embedder import OpenAIEmbedder
from application.services.embedding_service import CachedEmbeddingService
from application.services.vector_search_service import VectorSearchService
from infrastructure.grpc import engine_pb2, engine_pb2_grpc

logger = logging.getLogger(__name__)
T = TypeVar("T")
engine_pb2_any: Any = engine_pb2


class AsyncMemoryServicer(engine_pb2_grpc.MemoryServiceServicer):
    """
    gRPC servicer for memory retrieval.

    Handles async-to-sync bridging for gRPC which uses sync handlers.
    Uses a dedicated event loop running in a background thread for async operations.
    """

    def __init__(
        self,
        search_service: VectorSearchService | None = None,
        max_workers: int = 4,
        default_timeout: float = 10.0,
    ) -> None:
        if search_service is None:
            embedder = CachedEmbeddingService(OpenAIEmbedder())
            search_service = VectorSearchService(embedder)

        self._search_service = search_service
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._default_timeout = default_timeout

        # Create dedicated event loop for async operations
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_thread: threading.Thread | None = None
        self._start_loop()

    def _start_loop(self) -> None:
        """Start the async event loop in a background thread."""

        def run_loop() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()

    def _run_async(self, coro: Awaitable[T], timeout: float | None = None) -> T:
        """Run async coroutine from sync context."""
        if timeout is None:
            timeout = self._default_timeout

        future = asyncio.run_coroutine_threadsafe(cast(Coroutine[Any, Any, T], coro), self._loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise

    def RetrieveMemory(self, request: Any, context: Any) -> Any:
        """Retrieve relevant memories for a query."""
        _increment_metric("memory_grpc_requests_total", 1)

        # Validate request
        if not request.query:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.RetrieveMemoryResponse(error="query is required")

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.RetrieveMemoryResponse(error="tenant_id is required")

        try:
            # Execute search asynchronously
            results = self._run_async(
                self._search_service.search(
                    tenant_id=request.tenant_id,
                    query=request.query,
                    agent_id=request.agent_id or None,
                    run_id=request.run_id or None,
                    session_id=request.session_id or None,
                    top_k=request.top_k or 5,
                    threshold=request.threshold or 0.7,
                    recency_weight=request.recency_weight or 0.2,
                    model=request.embedding_model or None,
                ),
                timeout=self._default_timeout,
            )

            # Convert to proto
            chunks = []
            for result in results:
                chunk = engine_pb2_any.MemoryChunk(
                    content=result.content,
                    score=float(result.combined_score),
                    source_timestamp=result.source_timestamp.isoformat()
                    if result.source_timestamp
                    else "",
                    metadata_json=json.dumps(result.metadata or {}),
                )
                # Add similarity and recency if the proto supports it
                if hasattr(chunk, "similarity"):
                    chunk.similarity = float(result.similarity)
                if hasattr(chunk, "recency_score"):
                    chunk.recency_score = float(result.recency_score)
                chunks.append(chunk)

            return engine_pb2_any.RetrieveMemoryResponse(chunks=chunks)

        except TimeoutError:
            logger.error(
                "Memory search timed out",
                extra={"query": request.query[:50] if request.query else ""},
            )
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.RetrieveMemoryResponse(error="search timed out")
        except Exception as exc:
            logger.exception("Memory search failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.RetrieveMemoryResponse(error=f"internal error: {str(exc)}")

    def shutdown(self) -> None:
        """Clean shutdown of async resources."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=5.0)
        self._executor.shutdown(wait=True)


# Legacy alias for backward compatibility
MemoryService = AsyncMemoryServicer


def create_memory_servicer(
    search_service: VectorSearchService | None = None,
) -> AsyncMemoryServicer:
    """Factory function for creating memory servicer."""
    return AsyncMemoryServicer(search_service)


def _increment_metric(key: str, amount: int) -> None:
    try:
        cache.incr(key, amount)
    except Exception:
        current = cache.get(key, 0) or 0
        cache.set(key, current + amount, timeout=None)
