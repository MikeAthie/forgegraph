from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from adapters.embedding.openai_embedder import OpenAIEmbedder
from adapters.worker.celery_app import celery_app
from application.services.chunking_service import Message, TurnBasedChunking
from application.services.embedding_pipeline import EmbeddingPipeline
from application.services.embedding_service import CachedEmbeddingService


def _parse_messages(messages: list[dict[str, Any]]) -> list[Message]:
    parsed: list[Message] = []
    for message in messages:
        timestamp = message.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.now(timezone.utc)
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(timezone.utc)
        parsed.append(
            Message(
                role=message.get("role", "user"),
                content=message.get("content", ""),
                timestamp=timestamp,
                metadata=message.get("metadata") or {},
            )
        )
    return parsed


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_embeddings(self, payload: dict[str, Any]) -> int:
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
