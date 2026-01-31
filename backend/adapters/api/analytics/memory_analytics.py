"""
Memory analytics endpoints.

Provides usage, cost, and performance summaries for the memory system.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.db.models import Count, Sum
from django.db.models.functions import Cast, Length
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from infrastructure.orm.models import MemoryChunk, MemoryConfiguration, MemoryEntry, MemoryUsage, NodeRun


def _tenant_id_for_user(user) -> str:
    if hasattr(user, "tenant_id") and user.tenant_id:
        return str(user.tenant_id)
    return str(user.id)


def _parse_period(request: Request, default_days: int = 30) -> int | Response:
    raw = request.query_params.get("period") or request.query_params.get("days") or ""
    if not raw:
        return default_days

    value = raw.strip().lower()
    if value.endswith("d"):
        value = value[:-1]

    try:
        days = int(value)
    except ValueError:
        return error_response(
            code="VALIDATION_ERROR",
            message="period must be a day count like '7', '30', or '30d'",
            status=400,
        )

    if days <= 0 or days > 365:
        return error_response(
            code="VALIDATION_ERROR",
            message="period must be between 1 and 365 days",
            status=400,
        )
    return days


def _date_window(days: int):
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


class MemoryUsageAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed

        start_date, end_date = _date_window(days)
        tenant_id = _tenant_id_for_user(request.user)

        usage_qs = (
            MemoryUsage.objects.filter(
                tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
            )
            .order_by("usage_date")
            .values(
                "usage_date",
                "summarization_prompt_tokens",
                "summarization_completion_tokens",
                "summarization_total_tokens",
                "summarization_cost_usd",
            )
        )

        usage_series = [
            {
                "date": record["usage_date"].isoformat(),
                "summarization_prompt_tokens": record["summarization_prompt_tokens"],
                "summarization_completion_tokens": record["summarization_completion_tokens"],
                "summarization_total_tokens": record["summarization_total_tokens"],
                "summarization_cost_usd": float(record["summarization_cost_usd"]),
            }
            for record in usage_qs
        ]

        usage_totals = MemoryUsage.objects.filter(
            tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
        ).aggregate(
            total_prompt=models.Sum("summarization_prompt_tokens"),
            total_completion=models.Sum("summarization_completion_tokens"),
            total_tokens=models.Sum("summarization_total_tokens"),
            total_cost=models.Sum("summarization_cost_usd"),
        )

        total_prompt = int(usage_totals["total_prompt"] or 0)
        total_completion = int(usage_totals["total_completion"] or 0)
        total_tokens = int(usage_totals["total_tokens"] or 0)
        total_cost = float(usage_totals["total_cost"] or 0)

        buffer_sizes = list(
            MemoryConfiguration.objects.filter(
                models.Q(graph__owner=request.user) | models.Q(user=request.user),
                buffer_enabled=True,
            ).values_list("buffer_size", flat=True)
        )
        if not buffer_sizes:
            buffer_sizes = [20]
        avg_buffer_size = sum(buffer_sizes) / len(buffer_sizes)
        peak_buffer_size = max(buffer_sizes)

        total_messages = NodeRun.objects.filter(
            run__owner=request.user,
            node_type="prompt",
            started_at__date__gte=start_date,
            started_at__date__lte=end_date,
        ).count()

        namespace_prefix = f"user:{request.user.id}"
        entry_qs = MemoryEntry.objects.filter(
            namespace__startswith=namespace_prefix,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        storage_bytes = (
            entry_qs.annotate(size=Length(Cast("value_json", models.TextField())))
            .aggregate(total=Sum("size"))
            .get("total")
            or 0
        )

        chunk_qs = MemoryChunk.objects.filter(
            tenant_id=tenant_id,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        top_agents = (
            chunk_qs.values("agent_id")
            .annotate(chunks=Count("id"))
            .order_by("-chunks")
        )

        payload = {
            "period": f"{days}d",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "tier1": {
                "total_messages": total_messages,
                "avg_buffer_size": round(avg_buffer_size, 1),
                "peak_buffer_size": peak_buffer_size,
            },
            "tier2": {
                "redis_keys": entry_qs.count(),
                "storage_mb": round(storage_bytes / (1024 * 1024), 2),
                "hit_rate": None,
            },
            "tier3": {
                "chunks_stored": chunk_qs.count(),
                "embeddings_generated": chunk_qs.count(),
                "search_queries": 0,
                "avg_search_latency_ms": None,
            },
            "costs": {
                "summarization_usd": total_cost,
                "embedding_usd": 0.0,
                "total_usd": total_cost,
            },
            "usage_series": usage_series,
            "top_agents": [
                {"agent_id": str(row["agent_id"]) if row["agent_id"] else None, "chunks": row["chunks"]}
                for row in top_agents
            ],
            "totals": {
                "summarization_prompt_tokens": total_prompt,
                "summarization_completion_tokens": total_completion,
                "summarization_total_tokens": total_tokens,
            },
        }

        return success_response(payload)


class MemoryCostsAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed

        start_date, end_date = _date_window(days)
        tenant_id = _tenant_id_for_user(request.user)

        usage_qs = (
            MemoryUsage.objects.filter(
                tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
            )
            .order_by("usage_date")
            .values("usage_date", "summarization_cost_usd")
        )

        series = [
            {"date": record["usage_date"].isoformat(), "summarization_cost_usd": float(record["summarization_cost_usd"])}
            for record in usage_qs
        ]
        total = float(
            MemoryUsage.objects.filter(
                tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
            ).aggregate(total=Sum("summarization_cost_usd"))["total"]
            or 0
        )

        payload = {
            "period": f"{days}d",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": "USD",
            "summarization_total_usd": total,
            "embedding_total_usd": 0.0,
            "series": series,
        }
        return success_response(payload)


class MemoryPerformanceAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed

        start_date, end_date = _date_window(days)
        tenant_id = _tenant_id_for_user(request.user)

        chunk_qs = MemoryChunk.objects.filter(
            tenant_id=tenant_id,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        payload = {
            "period": f"{days}d",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "vector": {
                "search_queries": 0,
                "avg_search_latency_ms": None,
                "chunks_indexed": chunk_qs.count(),
            },
            "summarization": {
                "runs": MemoryUsage.objects.filter(
                    tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
                ).count(),
                "avg_latency_ms": None,
            },
            "grpc": {
                "requests_total": cache.get("memory_grpc_requests_total", 0),
                "errors_total": cache.get("memory_grpc_errors_total", 0),
            },
            "maintenance": {
                "memory_gc_last_run_at": cache.get("memory_gc_last_run_at"),
                "memory_gc_last_reindex": cache.get("memory_gc_last_reindex"),
            },
        }
        return success_response(payload)
