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
from application.services.memory_observation_service import (
    MemoryObservationService,
    ObservationContext,
)
from application.services.vector_search_service import VectorSearchService
from infrastructure.grpc import engine_pb2, engine_pb2_grpc
from infrastructure.orm.models import MemoryObservation

logger = logging.getLogger(__name__)
T = TypeVar("T")
engine_pb2_any: Any = engine_pb2
_metric_fallback_store: dict[str, int] = {}


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
        self._observation_service = MemoryObservationService()
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

    def SaveObservation(self, request: Any, context: Any) -> Any:
        """Create or update a curated memory observation."""
        _increment_metric("memory_grpc_requests_total", 1)

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SaveObservationResponse(error="tenant_id is required")

        try:
            if request.observation_id:
                observation = self._observation_service.update_observation(
                    tenant_id=request.tenant_id,
                    observation_id=request.observation_id,
                    type=request.type or None,
                    title=request.title or None,
                    content=request.content or None,
                    topic_key=request.topic_key or None,
                    tool_name=request.tool_name or None,
                )
            else:
                dedupe = request.dedupe if request.HasField("dedupe") else True
                update_topic = request.update_topic if request.HasField("update_topic") else False
                observation = self._observation_service.create_observation(
                    tenant_id=request.tenant_id,
                    graph_id=request.graph_id or None,
                    run_id=request.run_id or None,
                    session_id=request.session_id or None,
                    agent_id=request.agent_id or None,
                    type=request.type,
                    title=request.title,
                    content=request.content,
                    scope=request.scope,
                    topic_key=request.topic_key or None,
                    tool_name=request.tool_name or None,
                    dedupe=dedupe,
                    update_topic=update_topic,
                )
            return engine_pb2_any.SaveObservationResponse(
                observation=_observation_to_proto(observation)
            )
        except LookupError:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SaveObservationResponse(error="observation not found")
        except ValueError as exc:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SaveObservationResponse(error=str(exc))
        except Exception as exc:
            logger.exception("Observation save failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SaveObservationResponse(error=f"internal error: {str(exc)}")

    def SearchObservations(self, request: Any, context: Any) -> Any:
        """Search curated memory observations."""
        _increment_metric("memory_grpc_requests_total", 1)

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SearchObservationsResponse(error="tenant_id is required")

        try:
            observations = self._observation_service.search_observations(
                tenant_id=request.tenant_id,
                query=request.query,
                graph_id=request.graph_id or None,
                run_id=request.run_id or None,
                session_id=request.session_id or None,
                agent_id=request.agent_id or None,
                scope=request.scope or None,
                type=request.type or None,
                topic_key=request.topic_key or None,
                limit=_normalize_limit(request.limit, default=20, maximum=100),
                include_deleted=bool(request.include_deleted),
            )
            return engine_pb2_any.SearchObservationsResponse(
                observations=[_observation_to_proto(observation) for observation in observations]
            )
        except ValueError as exc:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SearchObservationsResponse(error=str(exc))
        except Exception as exc:
            logger.exception("Observation search failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.SearchObservationsResponse(error=f"internal error: {str(exc)}")

    def GetObservation(self, request: Any, context: Any) -> Any:
        """Return a single curated memory observation."""
        _increment_metric("memory_grpc_requests_total", 1)

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetObservationResponse(error="tenant_id is required")
        if not request.observation_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetObservationResponse(error="observation_id is required")

        try:
            observation = self._observation_service.get_observation(
                tenant_id=request.tenant_id,
                observation_id=request.observation_id,
                include_deleted=bool(request.include_deleted),
            )
            return engine_pb2_any.GetObservationResponse(
                observation=_observation_to_proto(observation)
            )
        except LookupError:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetObservationResponse(error="observation not found")
        except ValueError as exc:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetObservationResponse(error=str(exc))
        except Exception as exc:
            logger.exception("Observation retrieval failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetObservationResponse(error=f"internal error: {str(exc)}")

    def GetContext(self, request: Any, context: Any) -> Any:
        """Return context-ready curated memory observations."""
        _increment_metric("memory_grpc_requests_total", 1)

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetContextResponse(error="tenant_id is required")

        try:
            observation_context = self._observation_service.get_context(
                tenant_id=request.tenant_id,
                graph_id=request.graph_id or None,
                run_id=request.run_id or None,
                session_id=request.session_id or None,
                agent_id=request.agent_id or None,
                query=request.query,
                limit=_normalize_limit(request.limit, default=10, maximum=50),
            )
            return _context_to_proto(observation_context)
        except ValueError as exc:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetContextResponse(error=str(exc))
        except Exception as exc:
            logger.exception("Observation context retrieval failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetContextResponse(error=f"internal error: {str(exc)}")

    def GetTimeline(self, request: Any, context: Any) -> Any:
        """Return a recency-ordered observation timeline."""
        _increment_metric("memory_grpc_requests_total", 1)

        if not request.tenant_id:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetTimelineResponse(error="tenant_id is required")

        try:
            observations = self._observation_service.get_timeline(
                tenant_id=request.tenant_id,
                graph_id=request.graph_id or None,
                run_id=request.run_id or None,
                session_id=request.session_id or None,
                agent_id=request.agent_id or None,
                scope=request.scope or None,
                limit=_normalize_limit(request.limit, default=50, maximum=100),
                include_deleted=bool(request.include_deleted),
            )
            return engine_pb2_any.GetTimelineResponse(
                observations=[_observation_to_proto(observation) for observation in observations]
            )
        except ValueError as exc:
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetTimelineResponse(error=str(exc))
        except Exception as exc:
            logger.exception("Observation timeline retrieval failed")
            _increment_metric("memory_grpc_errors_total", 1)
            return engine_pb2_any.GetTimelineResponse(error=f"internal error: {str(exc)}")

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
        try:
            current = cache.get(key, 0) or 0
            cache.set(key, current + amount, timeout=None)
        except Exception:
            _metric_fallback_store[key] = _metric_fallback_store.get(key, 0) + amount


def _normalize_limit(value: int, *, default: int, maximum: int) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def _observation_to_proto(observation: MemoryObservation) -> Any:
    return engine_pb2_any.Observation(
        id=str(observation.id),
        tenant_id=str(observation.tenant_id),
        graph_id=str(observation.graph_id or ""),
        run_id=str(observation.run_id or ""),
        session_id=str(observation.session_id or ""),
        agent_id=str(observation.agent_id or ""),
        memory_chunk_id=str(observation.memory_chunk_id or ""),
        type=observation.type,
        title=observation.title,
        content=observation.content,
        scope=observation.scope,
        topic_key=observation.topic_key,
        tool_name=observation.tool_name,
        revision_count=observation.revision_count,
        duplicate_count=observation.duplicate_count,
        last_seen_at=observation.last_seen_at.isoformat() if observation.last_seen_at else "",
        created_at=observation.created_at.isoformat() if observation.created_at else "",
        updated_at=observation.updated_at.isoformat() if observation.updated_at else "",
        deleted_at=observation.deleted_at.isoformat() if observation.deleted_at else "",
        is_deleted=observation.deleted_at is not None,
    )


def _context_to_proto(observation_context: ObservationContext) -> Any:
    return engine_pb2_any.GetContextResponse(
        observations=[
            _observation_to_proto(observation) for observation in observation_context.observations
        ],
        degraded=observation_context.degraded,
        strategies=observation_context.strategies,
    )
