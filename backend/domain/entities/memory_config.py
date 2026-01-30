from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class MemoryConfigEntity:
    id: UUID

    # Scope (one must be set)
    graph_id: Optional[UUID] = None
    user_id: Optional[UUID] = None

    # Tier 1: Local Buffer
    buffer_enabled: bool = True
    buffer_size: int = 20
    auto_prepend: bool = True

    # Tier 2: Redis
    redis_enabled: bool = False
    redis_summary_ttl: int = 86400  # 24 hours
    redis_facts_ttl: int = 604800  # 7 days

    # Tier 3: Vector (Phase 3)
    vector_enabled: bool = False
    vector_top_k: int = 5
    vector_threshold: float = 0.7
    vector_recency_weight: float = 0.2
    embedding_model: str = "text-embedding-ada-002"

    # Summarization (Phase 2)
    summarization_enabled: bool = False
    summarization_threshold: int = 30
    summarization_keep_recent: int = 10
    summarization_model: str = "gpt-4"
