from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass
class MemoryUsageEntity:
    id: UUID
    tenant_id: UUID
    usage_date: date
    summarization_prompt_tokens: int
    summarization_completion_tokens: int
    summarization_total_tokens: int
    summarization_cost_usd: Decimal
