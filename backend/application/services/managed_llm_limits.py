from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from application.services.rate_limit import RateLimitResult, check_rate_limit
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import LLMUsage, User

DEFAULT_PROMPT_MAX_TOKENS = 1000
DEFAULT_AGENT_MAX_STEPS = 6
DEFAULT_AGENT_MAX_TOKENS = 800


@dataclass(frozen=True)
class ManagedLLMUsageEstimate:
    max_llm_calls: int
    max_tokens: int


@dataclass(frozen=True)
class ManagedLLMLimitResult:
    allowed: bool
    details: list[dict[str, Any]]
    rate_limit: RateLimitResult | None = None


def estimate_managed_llm_usage(graph_json: dict[str, Any]) -> ManagedLLMUsageEstimate:
    calls = 0
    tokens = 0
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return ManagedLLMUsageEstimate(max_llm_calls=0, max_tokens=0)

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "").strip().lower()
        config_raw = node.get("config")
        config: dict[str, Any] = config_raw if isinstance(config_raw, dict) else {}
        if node_type == "prompt":
            calls += 1
            tokens += _positive_int(config.get("max_tokens"), DEFAULT_PROMPT_MAX_TOKENS)
        elif node_type == "agent":
            max_steps = _positive_int(config.get("max_steps"), DEFAULT_AGENT_MAX_STEPS)
            max_tokens = _positive_int(config.get("max_tokens"), DEFAULT_AGENT_MAX_TOKENS)
            token_budget = _positive_int(config.get("token_budget"), 0)
            calls += max_steps
            estimated_tokens = max_steps * max_tokens
            tokens += min(estimated_tokens, token_budget) if token_budget > 0 else estimated_tokens

    return ManagedLLMUsageEstimate(max_llm_calls=calls, max_tokens=tokens)


def check_managed_llm_limits(
    *,
    graph_json: dict[str, Any],
    user: User,
) -> ManagedLLMLimitResult:
    tenant_id = get_tenant_id_for_user(user)
    details: list[dict[str, Any]] = []
    estimate = estimate_managed_llm_usage(graph_json)

    max_calls = int(
        getattr(
            settings,
            "MANAGED_LLM_MAX_CALLS_PER_RUN",
            getattr(settings, "RUN_RUNTIME_LIMIT_MAX_LLM_CALLS", 24),
        )
        or 0
    )
    if max_calls > 0 and estimate.max_llm_calls > max_calls:
        details.append(
            {
                "reason": "managed_max_llm_calls_per_run",
                "estimated_llm_calls": estimate.max_llm_calls,
                "limit_llm_calls": max_calls,
            }
        )

    max_tokens = int(getattr(settings, "MANAGED_LLM_MAX_TOKENS_PER_RUN", 25000) or 0)
    if max_tokens > 0 and estimate.max_tokens > max_tokens:
        details.append(
            {
                "reason": "managed_max_tokens_per_run",
                "estimated_max_tokens": estimate.max_tokens,
                "limit_max_tokens": max_tokens,
            }
        )

    daily_cap = Decimal(str(getattr(settings, "MANAGED_LLM_DAILY_COST_CAP_USD", "10.00") or "0"))
    if daily_cap > 0:
        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_cost = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=day_start
        ).aggregate(total=Sum("cost_usd")).get("total") or Decimal("0")
        if daily_cost >= daily_cap:
            details.append(
                {
                    "reason": "managed_daily_cost_cap",
                    "current_cost_usd": float(daily_cost),
                    "limit_cost_usd": float(daily_cap),
                }
            )

    if details:
        return ManagedLLMLimitResult(allowed=False, details=details)

    rate_limit = check_rate_limit(
        scope="managed_llm_run_start",
        tenant_id=f"{tenant_id}:user:{user.id}",
        limit=int(getattr(settings, "MANAGED_LLM_RATE_LIMIT_PER_USER_PER_MIN", 600) or 0),
        window_seconds=int(getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60) or 60),
    )
    if not rate_limit.allowed:
        return ManagedLLMLimitResult(
            allowed=False,
            details=[
                {
                    "reason": "managed_rate_limit_per_user",
                    "limit": rate_limit.limit,
                    "remaining": rate_limit.remaining,
                    "reset_at": rate_limit.reset_at.isoformat(),
                    "retry_after_seconds": rate_limit.retry_after_seconds,
                }
            ],
            rate_limit=rate_limit,
        )

    return ManagedLLMLimitResult(allowed=True, details=[])


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
