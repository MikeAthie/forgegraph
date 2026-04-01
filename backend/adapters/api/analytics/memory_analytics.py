"""
Memory analytics endpoints.

Provides usage, cost, and performance summaries for the memory system.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from django.core.cache import cache
from django.db import models
from django.db.models import Count, Sum, Value
from django.db.models.functions import Cast, Coalesce, Length
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    MemoryChunk,
    MemoryConfiguration,
    MemoryEntry,
    MemoryObservation,
    MemoryUsage,
    NodeRun,
    TenantRetentionPolicy,
    User,
)


def _tenant_id_for_user(user: User) -> str:
    return get_tenant_id_for_user(user)


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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_date_range(request: Request, default_days: int = 30) -> tuple[date, date] | Response:
    start_param = request.query_params.get("start_date")
    end_param = request.query_params.get("end_date")
    if start_param or end_param:
        start_date = _parse_date(start_param)
        end_date = _parse_date(end_param)
        if not start_date or not end_date:
            return error_response(
                code="VALIDATION_ERROR",
                message="start_date and end_date must be ISO dates (YYYY-MM-DD)",
                status=400,
            )
        if start_date > end_date:
            return error_response(
                code="VALIDATION_ERROR",
                message="start_date must be before end_date",
                status=400,
            )
        return start_date, end_date
    return _date_window(default_days)


def _date_window(days: int) -> tuple[date, date]:
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


def _resolve_tenant_id(request: Request) -> str | Response:
    user = cast(User, request.user)
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        if not getattr(user, "is_staff", False):
            return error_response(
                code="FORBIDDEN",
                message="Only staff users can query memory analytics for other tenants.",
                status=403,
            )
        return tenant_id
    return _tenant_id_for_user(user)


def _memory_indexing_metrics() -> dict[str, int | str | None]:
    return {
        "jobs_total": int(cache.get("memory_observation_index_jobs_total", 0) or 0),
        "success_total": int(cache.get("memory_observation_index_success_total", 0) or 0),
        "delete_total": int(cache.get("memory_observation_index_delete_total", 0) or 0),
        "enqueue_errors_total": int(
            cache.get("memory_observation_index_enqueue_errors_total", 0) or 0
        ),
        "delete_enqueue_errors_total": int(
            cache.get("memory_observation_delete_enqueue_errors_total", 0) or 0
        ),
        "memory_gc_last_run_at": cache.get("memory_gc_last_run_at"),
        "memory_gc_last_reindex": cache.get("memory_gc_last_reindex"),
    }


def _retention_posture_payload(tenant_id: str) -> dict[str, object]:
    policy = TenantRetentionPolicy.objects.filter(tenant_id=tenant_id).first()
    return {
        "policy_configured": policy is not None,
        "runs_retention_days": policy.runs_retention_days if policy else None,
        "run_logs_retention_days": policy.run_logs_retention_days if policy else None,
        "audit_logs_retention_days": policy.audit_logs_retention_days if policy else None,
        "usage_retention_days": policy.usage_retention_days if policy else None,
        "observations_retention_days": None,
        "memory_chunks_retention_days": None,
        "observations_retention_mode": "manual",
        "memory_chunks_retention_mode": "manual",
        "summary": (
            "Runs, logs, audit logs, and usage follow the tenant retention policy. "
            "Curated observations and indexed chunks currently require manual cleanup."
            if policy
            else "No tenant retention policy is configured. Curated observations and indexed chunks currently require manual cleanup."
        ),
    }


def _curated_memory_payload(tenant_id: str, start_date: date, end_date: date) -> dict[str, int]:
    tenant_uuid = UUID(tenant_id)
    observation_qs = MemoryObservation.objects.for_tenant(tenant_id)
    active_qs = observation_qs.active()
    period_qs = observation_qs.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    return {
        "observations_total": active_qs.count(),
        "observations_created_in_period": period_qs.count(),
        "deleted_observations_total": observation_qs.filter(deleted_at__isnull=False).count(),
        "indexed_observations_total": active_qs.filter(memory_chunk__isnull=False).count(),
        "pending_index_total": active_qs.filter(memory_chunk__isnull=True).count(),
        "graph_scope_total": active_qs.filter(scope="graph").count(),
        "run_scope_total": active_qs.filter(scope="run").count(),
        "session_scope_total": active_qs.filter(scope="session").count(),
        "retrieval_runs_in_period": NodeRun.objects.filter(
            run__owner__default_organization_id=tenant_uuid,
            node_type__in=["observation_search", "observation_context", "observation_timeline"],
            started_at__date__gte=start_date,
            started_at__date__lte=end_date,
        ).count(),
    }


def _memory_usage_payload(
    user: User,
    tenant_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
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
        total_prompt=Coalesce(Sum("summarization_prompt_tokens"), Value(0)),
        total_completion=Coalesce(Sum("summarization_completion_tokens"), Value(0)),
        total_tokens=Coalesce(Sum("summarization_total_tokens"), Value(0)),
        total_cost=Coalesce(Sum("summarization_cost_usd"), Value(Decimal("0"))),
    )

    buffer_sizes = list(
        MemoryConfiguration.objects.filter(
            models.Q(graph__owner=user) | models.Q(user=user),
            buffer_enabled=True,
        ).values_list("buffer_size", flat=True)
    )
    if not buffer_sizes:
        buffer_sizes = [20]
    avg_buffer_size = sum(buffer_sizes) / len(buffer_sizes)
    peak_buffer_size = max(buffer_sizes)

    total_messages = NodeRun.objects.filter(
        run__owner=user,
        node_type="prompt",
        started_at__date__gte=start_date,
        started_at__date__lte=end_date,
    ).count()

    namespace_prefix = f"user:{user.id}"
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
    top_agents = chunk_qs.values("agent_id").annotate(chunks=Count("id")).order_by("-chunks")[:10]

    return {
        "period": f"{(end_date - start_date).days + 1}d",
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
        "curated_memory": _curated_memory_payload(tenant_id, start_date, end_date),
        "retention": _retention_posture_payload(tenant_id),
        "costs": {
            "summarization_usd": float(usage_totals["total_cost"]),
            "embedding_usd": 0.0,
            "total_usd": float(usage_totals["total_cost"]),
        },
        "usage_series": usage_series,
        "top_agents": [
            {
                "agent_id": str(row["agent_id"]) if row["agent_id"] else None,
                "chunks": row["chunks"],
            }
            for row in top_agents
        ],
        "totals": {
            "summarization_prompt_tokens": int(usage_totals["total_prompt"]),
            "summarization_completion_tokens": int(usage_totals["total_completion"]),
            "summarization_total_tokens": int(usage_totals["total_tokens"]),
        },
    }


def _memory_performance_payload(
    tenant_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    chunk_qs = MemoryChunk.objects.filter(
        tenant_id=tenant_id,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    indexing_metrics = _memory_indexing_metrics()
    curated_memory = _curated_memory_payload(tenant_id, start_date, end_date)

    return {
        "period": f"{(end_date - start_date).days + 1}d",
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
            "memory_gc_last_run_at": indexing_metrics["memory_gc_last_run_at"],
            "memory_gc_last_reindex": indexing_metrics["memory_gc_last_reindex"],
        },
        "indexing": {
            "jobs_total": indexing_metrics["jobs_total"],
            "success_total": indexing_metrics["success_total"],
            "delete_total": indexing_metrics["delete_total"],
            "enqueue_errors_total": indexing_metrics["enqueue_errors_total"],
            "delete_enqueue_errors_total": indexing_metrics["delete_enqueue_errors_total"],
            "pending_observations_total": curated_memory["pending_index_total"],
            "indexed_observations_total": curated_memory["indexed_observations_total"],
        },
    }


class MemoryUsageAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        date_range = _parse_date_range(request)
        if isinstance(date_range, Response):
            return date_range
        start_date, end_date = date_range
        user = cast(User, request.user)
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id
        return success_response(_memory_usage_payload(user, tenant_id, start_date, end_date))


class MemoryCostsAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        date_range = _parse_date_range(request)
        if isinstance(date_range, Response):
            return date_range
        start_date, end_date = date_range
        days = (end_date - start_date).days + 1
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id

        usage_qs = (
            MemoryUsage.objects.filter(
                tenant_id=tenant_id, usage_date__gte=start_date, usage_date__lte=end_date
            )
            .order_by("usage_date")
            .values("usage_date", "summarization_cost_usd")
        )

        series = [
            {
                "date": record["usage_date"].isoformat(),
                "summarization_cost_usd": float(record["summarization_cost_usd"]),
            }
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
        date_range = _parse_date_range(request)
        if isinstance(date_range, Response):
            return date_range
        start_date, end_date = date_range
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id
        return success_response(_memory_performance_payload(tenant_id, start_date, end_date))


class MemoryAnalyticsExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response | HttpResponse:
        user = cast(User, request.user)
        if not (has_min_role(user, "admin") or getattr(user, "is_staff", False)):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to export memory analytics for this organization.",
                status=403,
            )

        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed
        date_range = _parse_date_range(request, default_days=days)
        if isinstance(date_range, Response):
            return date_range
        start_date, end_date = date_range
        days = (end_date - start_date).days + 1
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id

        dataset = (request.query_params.get("dataset") or "report").lower()
        export_format = (request.query_params.get("export_format") or "json").lower()
        if dataset != "report":
            return error_response(
                code="VALIDATION_ERROR",
                message="dataset must be 'report'",
                status=400,
            )

        usage_payload = _memory_usage_payload(user, tenant_id, start_date, end_date)
        performance_payload = _memory_performance_payload(tenant_id, start_date, end_date)
        report = {
            "dataset": "report",
            "period": f"{days}d",
            "exported_at": timezone.now().isoformat(),
            "usage": usage_payload,
            "costs": usage_payload["costs"],
            "performance": performance_payload,
        }

        if export_format == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = "attachment; filename=memory-analytics-export.csv"
            writer = csv.writer(response)
            writer.writerow(["metric", "value"])
            curated_memory = cast(dict[str, object], usage_payload["curated_memory"])
            indexing = cast(dict[str, object], performance_payload["indexing"])
            totals = cast(dict[str, object], usage_payload["totals"])
            costs = cast(dict[str, object], usage_payload["costs"])
            writer.writerow(["period", report["period"]])
            writer.writerow(["summarization_total_usd", costs["total_usd"]])
            writer.writerow(["summarization_total_tokens", totals["summarization_total_tokens"]])
            writer.writerow(["observations_total", curated_memory["observations_total"]])
            writer.writerow(
                ["observations_created_in_period", curated_memory["observations_created_in_period"]]
            )
            writer.writerow(
                ["indexed_observations_total", curated_memory["indexed_observations_total"]]
            )
            writer.writerow(["pending_index_total", curated_memory["pending_index_total"]])
            writer.writerow(
                ["retrieval_runs_in_period", curated_memory["retrieval_runs_in_period"]]
            )
            retention = cast(dict[str, object], usage_payload["retention"])
            writer.writerow(
                ["observations_retention_mode", retention["observations_retention_mode"]]
            )
            writer.writerow(
                ["memory_chunks_retention_mode", retention["memory_chunks_retention_mode"]]
            )
            writer.writerow(["usage_retention_days", retention["usage_retention_days"]])
            writer.writerow(["index_jobs_total", indexing["jobs_total"]])
            writer.writerow(["index_success_total", indexing["success_total"]])
            writer.writerow(["index_enqueue_errors_total", indexing["enqueue_errors_total"]])
            return response

        return success_response(report)
