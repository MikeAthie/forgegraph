"""
LLM analytics endpoints.

Provides usage, cost, and budget summaries for LLM calls.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from infrastructure.orm.models import LLMBudget, LLMUsage, User


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

    def put(self, request: Request) -> Response:
        tenant_id = _tenant_id_for_user(cast(User, request.user))
        raw_limit = request.data.get("monthly_limit_usd")
        raw_threshold = request.data.get("warning_threshold_pct", 0.8)

        try:
            monthly_limit = Decimal(str(raw_limit))
        except (InvalidOperation, TypeError):
            return error_response(
                code="VALIDATION_ERROR",
                message="monthly_limit_usd must be a number",
                status=400,
            )

        try:
            threshold = Decimal(str(raw_threshold))
        except (InvalidOperation, TypeError):
            return error_response(
                code="VALIDATION_ERROR",
                message="warning_threshold_pct must be a number",
                status=400,
            )

        if threshold > 1:
            threshold = threshold / Decimal("100")

        if monthly_limit <= 0:
            return error_response(
                code="VALIDATION_ERROR",
                message="monthly_limit_usd must be greater than 0",
                status=400,
            )
        if threshold <= 0 or threshold > 1:
            return error_response(
                code="VALIDATION_ERROR",
                message="warning_threshold_pct must be between 0 and 1",
                status=400,
            )

        budget, _ = LLMBudget.objects.update_or_create(
            tenant_id=tenant_id,
            defaults={
                "monthly_limit_usd": monthly_limit.quantize(Decimal("0.01")),
                "warning_threshold_pct": threshold.quantize(Decimal("0.01")),
            },
        )

        month_start, now = _month_window()
        month_cost = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=month_start, created_at__lte=now
        ).aggregate(total=Coalesce(Sum("cost_usd"), Value(Decimal("0")))).get("total") or Decimal(
            "0"
        )

        return success_response(_build_budget_payload(budget, month_cost))
