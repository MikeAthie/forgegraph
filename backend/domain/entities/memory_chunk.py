from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
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
    agent_id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    metadata: dict[str, Any] | None = None
    created_at: Optional[datetime] = None
