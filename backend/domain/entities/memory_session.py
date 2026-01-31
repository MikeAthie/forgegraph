from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class MemorySessionEntity:
    id: UUID
    session_id: UUID
    owner_id: UUID
    expires_at: datetime
    agent_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
