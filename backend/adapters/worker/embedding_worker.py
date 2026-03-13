from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from adapters.embedding.openai_embedder import OpenAIEmbedder
from adapters.worker.celery_app import celery_app
from application.services.chunking_service import Message, TurnBasedChunking
from application.services.embedding_pipeline import EmbeddingPipeline
from application.services.embedding_service import CachedEmbeddingService
from application.services.memory_observation_indexing import (
    MemoryObservationIndexingService,
)

F = TypeVar("F", bound=Callable[..., Any])
celery_task = cast(Callable[..., Callable[[F], F]], celery_app.task)


def _parse_messages(messages: list[dict[str, Any]]) -> list[Message]:
    parsed: list[Message] = []
    for message in messages:
        timestamp = message.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.now(UTC)
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(UTC)
        parsed.append(
            Message(
                role=message.get("role", "user"),
                content=message.get("content", ""),
                timestamp=timestamp,
                metadata=message.get("metadata") or {},
            )
        )
    return parsed


@celery_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_embeddings(self: Any, payload: dict[str, Any]) -> int:
    tenant_id = payload["tenant_id"]
    embedding_model = payload.get("embedding_model", "text-embedding-ada-002")
    messages = _parse_messages(payload.get("messages", []))
    agent_id = payload.get("agent_id")
    run_id = payload.get("run_id")
    session_id = payload.get("session_id")

    embedder = CachedEmbeddingService(OpenAIEmbedder(model=embedding_model))
    pipeline = EmbeddingPipeline(TurnBasedChunking(), embedder)

    created = asyncio.run(
        pipeline.process_messages(
            tenant_id=tenant_id,
            messages=messages,
            embedding_model=embedding_model,
            agent_id=agent_id,
            run_id=run_id,
            session_id=session_id,
        )
    )
    return len(created) if hasattr(created, "__len__") else 0


@celery_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def index_memory_observation(self: Any, payload: dict[str, Any]) -> str | None:
    observation_id = payload["observation_id"]
    embedding_model = payload.get("embedding_model")

    embedder = CachedEmbeddingService(
        OpenAIEmbedder(
            model=embedding_model or "text-embedding-ada-002",
        )
    )
    service = MemoryObservationIndexingService(embedder)
    chunk = service.upsert_observation(
        observation_id=observation_id,
        embedding_model=embedding_model,
    )
    return str(chunk.id) if chunk is not None else None


@celery_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def delete_memory_observation_index(self: Any, payload: dict[str, Any]) -> bool:
    observation_id = payload["observation_id"]
    service = MemoryObservationIndexingService()
    return service.delete_observation_index(observation_id=observation_id)
