from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class MemoryChunkEntity:
    id: UUID
    tenant_id: UUID
    content: str
    chunk_type: str
    embedding: list[float]
    embedding_model: str
    source_timestamp: datetime
    agent_id: UUID | None = None
    run_id: UUID | None = None
    session_id: UUID | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
