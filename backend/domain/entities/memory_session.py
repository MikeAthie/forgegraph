from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class MemorySessionEntity:
    id: UUID
    session_id: UUID
    owner_id: UUID
    expires_at: datetime
    agent_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
