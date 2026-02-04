"""
LLM analytics endpoints.

Provides usage, cost, and budget summaries for LLM calls.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, paginated_response, success_response
from infrastructure.orm.models import LLMBudget, LLMQuota, LLMUsage, User


def _tenant_id_for_user(user: User) -> str:
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


def _resolve_tenant_id(request: Request) -> str | Response:
    user = cast(User, request.user)
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        if not getattr(user, "is_staff", False):
            return error_response(
                code="FORBIDDEN",
                message="Only admins can export usage for other tenants.",
                status=403,
            )
        return tenant_id
    return _tenant_id_for_user(user)


def _date_window(days: int) -> tuple[date, date]:
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


def _month_window() -> tuple[datetime, datetime]:
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _build_budget_payload(budget: LLMBudget | None, month_cost: Decimal) -> dict[str, object]:
    budget_payload = None
    warning_threshold_usd = None
    warning = False
    over_budget = False

    if budget is not None:
        warning_threshold_usd = (budget.monthly_limit_usd * budget.warning_threshold_pct).quantize(
            Decimal("0.01")
        )
        warning = month_cost >= warning_threshold_usd
        over_budget = month_cost >= budget.monthly_limit_usd
        budget_payload = {
            "monthly_limit_usd": float(budget.monthly_limit_usd),
            "warning_threshold_pct": float(budget.warning_threshold_pct),
        }

    return {
        "budget": budget_payload,
        "usage": {
            "month_cost_usd": float(month_cost),
        },
        "warning_threshold_usd": float(warning_threshold_usd) if warning_threshold_usd else None,
        "warning": warning,
        "over_budget": over_budget,
    }


class LLMUsageAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed

        start_date, end_date = _date_window(days)
        tenant_id = _tenant_id_for_user(cast(User, request.user))

        usage_qs = LLMUsage.objects.filter(
            tenant_id=tenant_id,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        series = (
            usage_qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                prompt_tokens=Coalesce(Sum("prompt_tokens"), Value(0)),
                completion_tokens=Coalesce(Sum("completion_tokens"), Value(0)),
                total_tokens=Coalesce(Sum("total_tokens"), Value(0)),
                cost_usd=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
            )
            .order_by("day")
        )

        totals = usage_qs.aggregate(
            prompt_tokens=Coalesce(Sum("prompt_tokens"), Value(0)),
            completion_tokens=Coalesce(Sum("completion_tokens"), Value(0)),
            total_tokens=Coalesce(Sum("total_tokens"), Value(0)),
            cost_usd=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
        )

        by_model = (
            usage_qs.values("provider", "model")
            .annotate(
                total_tokens=Coalesce(Sum("total_tokens"), Value(0)),
                cost_usd=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
                calls=Count("id"),
            )
            .order_by("-cost_usd")[:6]
        )

        by_provider = (
            usage_qs.values("provider")
            .annotate(
                total_tokens=Coalesce(Sum("total_tokens"), Value(0)),
                cost_usd=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
                calls=Count("id"),
            )
            .order_by("-cost_usd")
        )

        payload = {
            "period": f"{days}d",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "totals": {
                "prompt_tokens": int(totals["prompt_tokens"]),
                "completion_tokens": int(totals["completion_tokens"]),
                "total_tokens": int(totals["total_tokens"]),
                "cost_usd": float(totals["cost_usd"]),
            },
            "series": [
                {
                    "date": row["day"].isoformat(),
                    "prompt_tokens": int(row["prompt_tokens"]),
                    "completion_tokens": int(row["completion_tokens"]),
                    "total_tokens": int(row["total_tokens"]),
                    "cost_usd": float(row["cost_usd"]),
                }
                for row in series
            ],
            "by_model": [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "total_tokens": int(row["total_tokens"]),
                    "cost_usd": float(row["cost_usd"]),
                    "calls": int(row["calls"]),
                }
                for row in by_model
            ],
            "by_provider": [
                {
                    "provider": row["provider"],
                    "total_tokens": int(row["total_tokens"]),
                    "cost_usd": float(row["cost_usd"]),
                    "calls": int(row["calls"]),
                }
                for row in by_provider
            ],
        }

        return success_response(payload)


class LLMUsageExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response | HttpResponse:
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id

        date_range = _parse_date_range(request)
        if isinstance(date_range, Response):
            return date_range
        start_date, end_date = date_range

        pagination = _parse_pagination(request)
        if isinstance(pagination, Response):
            return pagination
        limit, offset = pagination

        usage_qs = LLMUsage.objects.filter(
            tenant_id=tenant_id,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).order_by("-created_at")

        export_format = (request.query_params.get("format") or "json").lower()

        if export_format == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = "attachment; filename=llm-usage-export.csv"
            writer = csv.writer(response)
            writer.writerow(
                [
                    "run_id",
                    "node_id",
                    "provider",
                    "model",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "cost_usd",
                    "created_at",
                ]
            )
            for usage in usage_qs[offset : offset + limit]:
                writer.writerow(
                    [
                        str(usage.run_id),
                        usage.node_id,
                        usage.provider,
                        usage.model,
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        f"{usage.cost_usd:.6f}",
                        usage.created_at.isoformat(),
                    ]
                )
            return response

        total_count = usage_qs.count()
        page = usage_qs[offset : offset + limit]
        data = [
            {
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
            for usage in page
        ]

        return paginated_response(
            data=data,
            page=(offset // limit) + 1,
            page_size=limit,
            total_count=total_count,
        )


class LLMCostsAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        parsed = _parse_period(request)
        if isinstance(parsed, Response):
            return parsed
        days = parsed

        start_date, end_date = _date_window(days)
        tenant_id = _tenant_id_for_user(cast(User, request.user))

        usage_qs = LLMUsage.objects.filter(
            tenant_id=tenant_id,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        series = (
            usage_qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(cost_usd=Coalesce(Sum("cost_usd"), Value(Decimal("0"))))
            .order_by("day")
        )

        total = usage_qs.aggregate(total=Coalesce(Sum("cost_usd"), Value(Decimal("0")))).get(
            "total", Decimal("0")
        )

        payload = {
            "period": f"{days}d",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": "USD",
            "total_usd": float(total),
            "series": [
                {
                    "date": row["day"].isoformat(),
                    "cost_usd": float(row["cost_usd"]),
                }
                for row in series
            ],
        }

        return success_response(payload)


class LLMBudgetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        tenant_id = _tenant_id_for_user(cast(User, request.user))
        budget = LLMBudget.objects.filter(tenant_id=tenant_id).first()

        month_start, now = _month_window()
        month_cost = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=month_start, created_at__lte=now
        ).aggregate(total=Coalesce(Sum("cost_usd"), Value(Decimal("0")))).get("total") or Decimal(
            "0"
        )

        return success_response(_build_budget_payload(budget, month_cost))


class LLMQuotaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id

        quota = LLMQuota.objects.filter(tenant_id=tenant_id).first()

        month_start, now = _month_window()
        totals = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=month_start, created_at__lte=now
        ).aggregate(
            total_tokens=Coalesce(Sum("total_tokens"), Value(0)),
            total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
        )

        payload = {
            "quota": None
            if quota is None
            else {
                "monthly_token_limit": quota.monthly_token_limit,
                "monthly_cost_limit_usd": float(quota.monthly_cost_limit_usd)
                if quota.monthly_cost_limit_usd is not None
                else None,
            },
            "usage": {
                "month_total_tokens": int(totals["total_tokens"]),
                "month_cost_usd": float(totals["total_cost"]),
            },
        }

        return success_response(payload)

    def put(self, request: Request) -> Response:
        tenant_id = _resolve_tenant_id(request)
        if isinstance(tenant_id, Response):
            return tenant_id

        raw_tokens = request.data.get("monthly_token_limit")
        raw_cost = request.data.get("monthly_cost_limit_usd")

        monthly_token_limit: int | None = None
        monthly_cost_limit_usd: Decimal | None = None

        if raw_tokens is not None and raw_tokens != "":
            try:
                monthly_token_limit = int(raw_tokens)
            except (TypeError, ValueError):
                return error_response(
                    code="VALIDATION_ERROR",
                    message="monthly_token_limit must be an integer",
                    status=400,
                )
            if monthly_token_limit <= 0:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="monthly_token_limit must be greater than 0",
                    status=400,
                )

        if raw_cost is not None and raw_cost != "":
            try:
                monthly_cost_limit_usd = Decimal(str(raw_cost))
            except (InvalidOperation, TypeError):
                return error_response(
                    code="VALIDATION_ERROR",
                    message="monthly_cost_limit_usd must be a number",
                    status=400,
                )
            if monthly_cost_limit_usd <= 0:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="monthly_cost_limit_usd must be greater than 0",
                    status=400,
                )

        if monthly_token_limit is None and monthly_cost_limit_usd is None:
            return error_response(
                code="VALIDATION_ERROR",
                message="Provide monthly_token_limit or monthly_cost_limit_usd",
                status=400,
            )

        quota, _ = LLMQuota.objects.update_or_create(
            tenant_id=tenant_id,
            defaults={
                "monthly_token_limit": monthly_token_limit,
                "monthly_cost_limit_usd": monthly_cost_limit_usd.quantize(Decimal("0.01"))
                if monthly_cost_limit_usd is not None
                else None,
            },
        )

        return success_response(
            {
                "quota": {
                    "monthly_token_limit": quota.monthly_token_limit,
                    "monthly_cost_limit_usd": float(quota.monthly_cost_limit_usd)
                    if quota.monthly_cost_limit_usd is not None
                    else None,
                }
            }
        )
