from __future__ import annotations

from datetime import date
from typing import cast
from uuid import UUID

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, paginated_response, success_response
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.retention import DataRetentionService
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    AuditLog,
    LLMUsage,
    MemoryUsage,
    NodeRun,
    Run,
    RunEvent,
    TenantRetentionPolicy,
    User,
)

from .serializers import TenantRetentionPolicySerializer


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_date_range(request: Request) -> tuple[date, date] | Response | None:
    start_param = request.query_params.get("start_date")
    end_param = request.query_params.get("end_date")
    if not start_param and not end_param:
        return None

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


def _parse_pagination(
    request: Request, default_limit: int = 200, max_limit: int = 2000
) -> tuple[int, int] | Response:
    limit_raw = request.query_params.get("limit")
    offset_raw = request.query_params.get("offset")
    try:
        limit = int(limit_raw) if limit_raw is not None else default_limit
        offset = int(offset_raw) if offset_raw is not None else 0
    except ValueError:
        return error_response(
            code="VALIDATION_ERROR",
            message="limit and offset must be integers",
            status=400,
        )
    if limit <= 0 or limit > max_limit:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"limit must be between 1 and {max_limit}",
            status=400,
        )
    if offset < 0:
        return error_response(
            code="VALIDATION_ERROR",
            message="offset must be >= 0",
            status=400,
        )
    return limit, offset


def _resolve_tenant_id(
    request: Request,
    *,
    source: str = "query",
) -> str | Response:
    user = cast(User, request.user)
    tenant_id = (
        request.query_params.get("tenant_id")
        if source == "query"
        else request.data.get("tenant_id")
    )
    if tenant_id:
        if not getattr(user, "is_staff", False):
            return error_response(
                code="FORBIDDEN",
                message="Only admins can access retention settings for other tenants.",
                status=403,
            )
        return tenant_id
    return get_tenant_id_for_user(user)


def _ensure_admin(user: User) -> Response | None:
    if not (getattr(user, "is_staff", False) or has_min_role(user, "admin")):
        return error_response(
            code="FORBIDDEN",
            message="You don't have permission to manage retention settings in this organization.",
            status=403,
        )
    return None


def _validate_retention_hierarchy(
    merged: dict[str, int | None],
) -> str | None:
    runs = merged.get("runs_retention_days")
    run_logs = merged.get("run_logs_retention_days")
    usage = merged.get("usage_retention_days")

    if runs and run_logs and run_logs > runs:
        return "run_logs_retention_days cannot exceed runs_retention_days."
    if runs and usage and usage > runs:
        return "usage_retention_days cannot exceed runs_retention_days."
    return None


class TenantRetentionPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        tenant_id = _resolve_tenant_id(request, source="query")
        if isinstance(tenant_id, Response):
            return tenant_id

        policy = TenantRetentionPolicy.objects.filter(tenant_id=tenant_id).first()
        if not policy:
            return success_response(
                {
                    "runs_retention_days": None,
                    "run_logs_retention_days": None,
                    "audit_logs_retention_days": None,
                    "usage_retention_days": None,
                }
            )

        return success_response(
            {
                "runs_retention_days": policy.runs_retention_days,
                "run_logs_retention_days": policy.run_logs_retention_days,
                "audit_logs_retention_days": policy.audit_logs_retention_days,
                "usage_retention_days": policy.usage_retention_days,
            }
        )

    def put(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        serializer = TenantRetentionPolicySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        tenant_id = _resolve_tenant_id(request, source="body")
        if isinstance(tenant_id, Response):
            return tenant_id

        existing = TenantRetentionPolicy.objects.filter(tenant_id=tenant_id).first()
        data = serializer.validated_data
        merged = {
            "runs_retention_days": data.get(
                "runs_retention_days",
                existing.runs_retention_days if existing else None,
            ),
            "run_logs_retention_days": data.get(
                "run_logs_retention_days",
                existing.run_logs_retention_days if existing else None,
            ),
            "audit_logs_retention_days": data.get(
                "audit_logs_retention_days",
                existing.audit_logs_retention_days if existing else None,
            ),
            "usage_retention_days": data.get(
                "usage_retention_days",
                existing.usage_retention_days if existing else None,
            ),
        }

        validation_error = _validate_retention_hierarchy(merged)
        if validation_error:
            return error_response(
                code="VALIDATION_ERROR",
                message=validation_error,
                status=400,
            )

        policy, _ = TenantRetentionPolicy.objects.update_or_create(
            tenant_id=tenant_id,
            defaults=merged,
        )

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="retention_policy_updated",
            resource_type="tenant_retention_policy",
            resource_id=str(policy.id),
            metadata={
                "previous": {
                    "runs_retention_days": existing.runs_retention_days if existing else None,
                    "run_logs_retention_days": existing.run_logs_retention_days
                    if existing
                    else None,
                    "audit_logs_retention_days": existing.audit_logs_retention_days
                    if existing
                    else None,
                    "usage_retention_days": existing.usage_retention_days if existing else None,
                },
                "current": merged,
            },
        )

        return success_response(
            {
                "runs_retention_days": policy.runs_retention_days,
                "run_logs_retention_days": policy.run_logs_retention_days,
                "audit_logs_retention_days": policy.audit_logs_retention_days,
                "usage_retention_days": policy.usage_retention_days,
            }
        )


class RetentionCleanupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        tenant_id = _resolve_tenant_id(request, source="body")
        if isinstance(tenant_id, Response):
            return tenant_id

        raw_dry_run = request.data.get("dry_run", False)
        dry_run = (
            raw_dry_run
            if isinstance(raw_dry_run, bool)
            else str(raw_dry_run).lower() in {"1", "true", "yes"}
        )

        policy = TenantRetentionPolicy.objects.filter(tenant_id=tenant_id).first()
        service = DataRetentionService()
        result = service.cleanup_tenant(str(tenant_id), policy, dry_run=dry_run)

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="retention_cleanup_preview" if dry_run else "retention_cleanup",
            resource_type="tenant_retention_policy",
            resource_id=str(policy.id) if policy else "none",
            metadata={"dry_run": dry_run, "summary": result},
        )

        return success_response(result)


class RetentionExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        tenant_id = _resolve_tenant_id(request, source="query")
        if isinstance(tenant_id, Response):
            return tenant_id

        export_type_param = (request.query_params.get("type") or "runs").lower()
        export_type = {
            "runs": "runs",
            "run_events": "run_events",
            "logs": "run_events",
            "node_runs": "node_runs",
            "audit_logs": "audit_logs",
            "audit": "audit_logs",
            "usage": "usage",
            "llm_usage": "usage",
            "memory_usage": "memory_usage",
        }.get(export_type_param)

        if not export_type:
            return error_response(
                code="VALIDATION_ERROR",
                message="type must be one of runs, logs, node_runs, audit_logs, usage, memory_usage",
                status=400,
            )

        tenant_uuid = UUID(str(tenant_id))

        date_range = _parse_date_range(request)
        if isinstance(date_range, Response):
            return date_range

        pagination = _parse_pagination(request)
        if isinstance(pagination, Response):
            return pagination
        limit, offset = pagination

        if export_type == "runs":
            run_qs = (
                Run.objects.select_related("graph_version", "graph_version__graph")
                .filter(owner__default_organization_id=tenant_uuid)
                .order_by("-started_at")
            )
            if date_range:
                start_date, end_date = date_range
                run_qs = run_qs.filter(
                    started_at__date__gte=start_date,
                    started_at__date__lte=end_date,
                )

            run_count = run_qs.count()
            run_page = run_qs[offset : offset + limit]
            data = [
                {
                    "id": str(run.id),
                    "graph_id": str(run.graph_version.graph_id),
                    "graph_version_id": str(run.graph_version_id),
                    "graph_version": run.graph_version.version,
                    "status": run.status,
                    "thread_id": str(run.thread_id) if run.thread_id else None,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                    "input_json": run.input_json,
                    "output_json": run.output_json,
                    "error_message": run.error_message,
                }
                for run in run_page
            ]
            return paginated_response(
                data=data,
                page=(offset // limit) + 1,
                page_size=limit,
                total_count=run_count,
            )

        if export_type == "run_events":
            run_events_qs = RunEvent.objects.filter(
                run__owner__default_organization_id=tenant_uuid
            ).order_by("-created_at")
            if date_range:
                start_date, end_date = date_range
                run_events_qs = run_events_qs.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )

            event_count = run_events_qs.count()
            event_page = run_events_qs[offset : offset + limit]
            data = [
                {
                    "id": str(event.id),
                    "run_id": str(event.run_id),
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                for event in event_page
            ]
            return paginated_response(
                data=data,
                page=(offset // limit) + 1,
                page_size=limit,
                total_count=event_count,
            )

        if export_type == "node_runs":
            node_runs_qs = NodeRun.objects.filter(
                run__owner__default_organization_id=tenant_uuid
            ).order_by("-started_at")
            if date_range:
                start_date, end_date = date_range
                node_runs_qs = node_runs_qs.filter(
                    Q(started_at__date__gte=start_date) | Q(started_at__isnull=True),
                    Q(started_at__date__lte=end_date) | Q(started_at__isnull=True),
                )

            node_run_count = node_runs_qs.count()
            node_run_page = node_runs_qs[offset : offset + limit]
            data = [
                {
                    "id": str(node_run.id),
                    "run_id": str(node_run.run_id),
                    "node_id": node_run.node_id,
                    "node_type": node_run.node_type,
                    "status": node_run.status,
                    "attempt": node_run.attempt,
                    "started_at": node_run.started_at.isoformat() if node_run.started_at else None,
                    "ended_at": node_run.ended_at.isoformat() if node_run.ended_at else None,
                    "input_json": node_run.input_json,
                    "output_json": node_run.output_json,
                    "error_json": node_run.error_json,
                }
                for node_run in node_run_page
            ]
            return paginated_response(
                data=data,
                page=(offset // limit) + 1,
                page_size=limit,
                total_count=node_run_count,
            )

        if export_type == "audit_logs":
            audit_logs_qs = AuditLog.objects.filter(tenant_id=tenant_uuid).order_by("-created_at")
            if date_range:
                start_date, end_date = date_range
                audit_logs_qs = audit_logs_qs.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )

            audit_count = audit_logs_qs.count()
            audit_page = audit_logs_qs[offset : offset + limit]
            data = [
                {
                    "id": str(log.id),
                    "actor_id": str(log.actor_id) if log.actor_id else None,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "metadata": log.metadata,
                    "created_at": log.created_at.isoformat(),
                }
                for log in audit_page
            ]
            return paginated_response(
                data=data,
                page=(offset // limit) + 1,
                page_size=limit,
                total_count=audit_count,
            )

        if export_type == "memory_usage":
            memory_usage_qs = MemoryUsage.objects.filter(tenant_id=tenant_uuid).order_by(
                "-usage_date"
            )
            if date_range:
                start_date, end_date = date_range
                memory_usage_qs = memory_usage_qs.filter(
                    usage_date__gte=start_date, usage_date__lte=end_date
                )

            memory_count = memory_usage_qs.count()
            memory_page = memory_usage_qs[offset : offset + limit]
            data = [
                {
                    "id": str(row.id),
                    "usage_date": row.usage_date.isoformat(),
                    "summarization_prompt_tokens": row.summarization_prompt_tokens,
                    "summarization_completion_tokens": row.summarization_completion_tokens,
                    "summarization_total_tokens": row.summarization_total_tokens,
                    "summarization_cost_usd": float(row.summarization_cost_usd),
                }
                for row in memory_page
            ]
            return paginated_response(
                data=data,
                page=(offset // limit) + 1,
                page_size=limit,
                total_count=memory_count,
            )

        llm_usage_qs = LLMUsage.objects.filter(tenant_id=tenant_uuid).order_by("-created_at")
        if date_range:
            start_date, end_date = date_range
            llm_usage_qs = llm_usage_qs.filter(
                created_at__date__gte=start_date, created_at__date__lte=end_date
            )

        usage_count = llm_usage_qs.count()
        usage_page = llm_usage_qs[offset : offset + limit]
        data = [
            {
                "id": str(usage.id),
                "run_id": str(usage.run_id),
                "node_id": usage.node_id,
                "provider": usage.provider,
                "model": usage.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cost_usd": float(usage.cost_usd),
                "created_at": usage.created_at.isoformat(),
            }
            for usage in usage_page
        ]
        return paginated_response(
            data=data,
            page=(offset // limit) + 1,
            page_size=limit,
            total_count=usage_count,
        )
