from __future__ import annotations

from typing import Iterable

from adapters.repositories.memory_chunk_repository import MemoryChunkRepository
from application.services.chunking_service import Chunk, ChunkingStrategy, Message
from application.services.embedding_service import EmbeddingService
from infrastructure.orm.models import MemoryChunk


class EmbeddingPipeline:
    def __init__(
        self,
        chunker: ChunkingStrategy,
        embedder: EmbeddingService,
        repository: MemoryChunkRepository | None = None,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._repository = repository or MemoryChunkRepository()

    async def process_messages(
        self,
        *,
        tenant_id: str,
        messages: list[Message],
        embedding_model: str,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> list[MemoryChunk]:
        chunks = self._chunker.chunk(messages)
        if not chunks:
            return []

        embeddings = await self._embedder.embed(
            [chunk.content for chunk in chunks], model=embedding_model
        )

        records = [
            MemoryChunk(
                tenant_id=tenant_id,
                agent_id=agent_id,
                run_id=run_id,
                session_id=session_id,
                content=chunk.content,
                chunk_type=chunk.chunk_type,
                metadata=_chunk_metadata(chunk),
                embedding=embedding,
                embedding_model=embedding_model,
                source_timestamp=chunk.source_timestamp,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]

        return self._repository.bulk_create(records)


def _chunk_metadata(chunk: Chunk) -> dict:
    return {
        "message_count": len(chunk.messages),
        "roles": [message.role for message in chunk.messages],
    }
