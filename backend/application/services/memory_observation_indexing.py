from __future__ import annotations

import logging
import threading
from typing import Any, Protocol, cast
from uuid import UUID

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache

from adapters.embedding.openai_embedder import OpenAIEmbedder
from application.services.embedding_service import CachedEmbeddingService, EmbeddingService
from infrastructure.orm.models import MemoryChunk, MemoryObservation

logger = logging.getLogger(__name__)

DEFAULT_OBSERVATION_EMBEDDING_MODEL = "text-embedding-ada-002"
_metric_fallback_store: dict[str, int] = {}


class ObservationIndexDispatcher(Protocol):
    def enqueue_upsert(
        self,
        *,
        observation_id: UUID | str,
        embedding_model: str | None = None,
    ) -> None: ...

    def enqueue_delete(self, *, observation_id: UUID | str) -> None: ...


class CeleryObservationIndexDispatcher:
    """Queues observation indexing work without blocking observation writes."""

    def enqueue_upsert(
        self,
        *,
        observation_id: UUID | str,
        embedding_model: str | None = None,
    ) -> None:
        if not getattr(settings, "FF_CURATED_MEMORY_VECTOR_INDEXING", True):
            return

        payload = {
            "observation_id": str(observation_id),
            "embedding_model": embedding_model or _default_embedding_model(),
        }
        _increment_metric("memory_observation_index_jobs_total", 1)
        self._publish_async("index_memory_observation", payload)

    def enqueue_delete(self, *, observation_id: UUID | str) -> None:
        if not getattr(settings, "FF_CURATED_MEMORY_VECTOR_INDEXING", True):
            return

        payload = {"observation_id": str(observation_id)}
        _increment_metric("memory_observation_delete_jobs_total", 1)
        self._publish_async("delete_memory_observation_index", payload)

    def _publish_async(self, task_name: str, payload: dict[str, str]) -> None:
        def _publish() -> None:
            try:
                from adapters.worker import embedding_worker

                task = getattr(embedding_worker, task_name)
                cast(Any, task).delay(payload)
            except Exception:
                logger.exception(
                    "Failed to enqueue observation task", extra={"task": task_name, **payload}
                )
                metric_name = (
                    "memory_observation_delete_enqueue_errors_total"
                    if task_name == "delete_memory_observation_index"
                    else "memory_observation_index_enqueue_errors_total"
                )
                _increment_metric(metric_name, 1)

        thread = threading.Thread(target=_publish, daemon=True)
        thread.start()


class MemoryObservationIndexingService:
    """Creates and updates observation-backed MemoryChunk rows."""

    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        model_name = _default_embedding_model()
        self._embedder = embedder or CachedEmbeddingService(OpenAIEmbedder(model=model_name))

    def upsert_observation(
        self,
        *,
        observation_id: UUID | str,
        embedding_model: str | None = None,
    ) -> MemoryChunk | None:
        observation = (
            MemoryObservation.objects.select_related("memory_chunk")
            .filter(id=_as_uuid(observation_id))
            .first()
        )
        if observation is None:
            raise LookupError("Observation not found")

        if observation.deleted_at is not None:
            self.delete_observation_index(observation_id=observation.id)
            return None

        selected_model = embedding_model or _default_embedding_model()
        content = _observation_document(observation)
        vectors = async_to_sync(self._embedder.embed)([content], model=selected_model)
        if not vectors:
            raise RuntimeError("embedding service returned no vectors")

        metadata = _observation_metadata(observation)
        source_timestamp = (
            observation.last_seen_at or observation.updated_at or observation.created_at
        )
        chunk = (
            observation.memory_chunk
            or MemoryChunk.objects.filter(metadata__observation_id=str(observation.id)).first()
        )

        if chunk is None:
            chunk = MemoryChunk.objects.create(
                tenant_id=observation.tenant_id,
                agent_id=observation.agent_id,
                run_id=observation.run_id,
                session_id=observation.session_id,
                content=content,
                chunk_type="observation",
                metadata=metadata,
                embedding=vectors[0],
                embedding_model=selected_model,
                source_timestamp=source_timestamp,
            )
        else:
            chunk.tenant_id = observation.tenant_id
            chunk.agent_id = observation.agent_id
            chunk.run_id = observation.run_id
            chunk.session_id = observation.session_id
            chunk.content = content
            chunk.chunk_type = "observation"
            chunk.metadata = metadata
            chunk.embedding = vectors[0]
            chunk.embedding_model = selected_model
            chunk.source_timestamp = source_timestamp
            chunk.save(
                update_fields=[
                    "tenant_id",
                    "agent_id",
                    "run_id",
                    "session_id",
                    "content",
                    "chunk_type",
                    "metadata",
                    "embedding",
                    "embedding_model",
                    "source_timestamp",
                ]
            )

        if observation.memory_chunk_id != chunk.id:
            observation.memory_chunk = chunk
            observation.save(update_fields=["memory_chunk", "updated_at"])

        _increment_metric("memory_observation_index_success_total", 1)
        return chunk

    def delete_observation_index(self, *, observation_id: UUID | str) -> bool:
        observation_uuid = _as_uuid(observation_id)
        observation = (
            MemoryObservation.objects.select_related("memory_chunk")
            .filter(id=observation_uuid)
            .first()
        )
        chunk = None
        if observation is not None:
            chunk = observation.memory_chunk
            if chunk is None:
                chunk = MemoryChunk.objects.filter(
                    metadata__observation_id=str(observation.id)
                ).first()
            if observation.memory_chunk_id is not None:
                observation.memory_chunk = None
                observation.save(update_fields=["memory_chunk", "updated_at"])
        else:
            chunk = MemoryChunk.objects.filter(
                metadata__observation_id=str(observation_uuid)
            ).first()

        if chunk is None:
            return False

        chunk.delete()
        _increment_metric("memory_observation_index_delete_total", 1)
        return True


def _default_embedding_model() -> str:
    return getattr(
        settings,
        "CURATED_MEMORY_EMBEDDING_MODEL",
        DEFAULT_OBSERVATION_EMBEDDING_MODEL,
    )


def _as_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _observation_document(observation: MemoryObservation) -> str:
    title = observation.title.strip()
    content = observation.content.strip()
    if not title or title.lower() in content.lower():
        return content
    return f"{title}\n\n{content}"


def _observation_metadata(observation: MemoryObservation) -> dict[str, str]:
    return {
        "observation_id": str(observation.id),
        "graph_id": str(observation.graph_id or ""),
        "run_id": str(observation.run_id or ""),
        "session_id": str(observation.session_id or ""),
        "agent_id": str(observation.agent_id or ""),
        "type": observation.type,
        "topic_key": observation.topic_key,
        "scope": observation.scope,
        "tool_name": observation.tool_name,
        "title": observation.title,
    }


def _increment_metric(key: str, amount: int) -> None:
    try:
        cache.incr(key, amount)
    except Exception:
        try:
            current = cache.get(key, 0) or 0
            cache.set(key, current + amount, timeout=None)
        except Exception:
            _metric_fallback_store[key] = _metric_fallback_store.get(key, 0) + amount
