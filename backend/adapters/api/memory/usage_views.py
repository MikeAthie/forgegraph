"""
Memory usage endpoints.

Provides daily summarization usage totals.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from infrastructure.orm.models import MemoryUsage


def _tenant_id_for_user(user) -> str:
    if hasattr(user, "tenant_id") and user.tenant_id:
        return str(user.tenant_id)
    return str(user.id)


class MemoryUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        days_raw = request.query_params.get("days", "7")
        try:
            days = int(days_raw)
        except ValueError:
            return error_response(
                code="VALIDATION_ERROR",
                message="days must be an integer",
                status=400,
            )
        if days <= 0 or days > 365:
            return error_response(
                code="VALIDATION_ERROR",
                message="days must be between 1 and 365",
                status=400,
            )

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)

        tenant_id = _tenant_id_for_user(request.user)
        records = (
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

        payload = [
            {
                "date": record["usage_date"].isoformat(),
                "prompt_tokens": record["summarization_prompt_tokens"],
                "completion_tokens": record["summarization_completion_tokens"],
                "total_tokens": record["summarization_total_tokens"],
                "cost_usd": float(record["summarization_cost_usd"]),
            }
            for record in records
        ]

        return success_response(
            {
                "tenant_id": tenant_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days,
                "usage": payload,
            }
        )
