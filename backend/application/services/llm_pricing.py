from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Pricing:
    input_per_1k: Decimal
    output_per_1k: Decimal


PRICING: Mapping[tuple[str, str], Pricing] = {
    ("openai", "gpt-4"): Pricing(Decimal("0.03"), Decimal("0.06")),
    ("openai", "gpt-4-turbo"): Pricing(Decimal("0.01"), Decimal("0.03")),
    ("openai", "gpt-3.5-turbo"): Pricing(Decimal("0.0005"), Decimal("0.0015")),
    ("anthropic", "claude-3-opus"): Pricing(Decimal("0.015"), Decimal("0.075")),
    ("anthropic", "claude-3-sonnet"): Pricing(Decimal("0.003"), Decimal("0.015")),
    ("anthropic", "claude-3-haiku"): Pricing(Decimal("0.00025"), Decimal("0.00125")),
}


def calculate_cost(
    provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> Decimal:
    pricing = PRICING.get((provider, model))
    if not pricing:
        return Decimal("0")

    prompt_cost = (Decimal(prompt_tokens) / Decimal(1000)) * pricing.input_per_1k
    completion_cost = (Decimal(completion_tokens) / Decimal(1000)) * pricing.output_per_1k
    return prompt_cost + completion_cost
