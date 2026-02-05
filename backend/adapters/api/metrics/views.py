"""
Metrics API views.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.metrics import get_run_metrics_snapshot
from application.services.rbac import has_min_role
from infrastructure.orm.models import RunQueueEntry, User


class MetricsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User) or not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to access metrics.",
                status=403,
            )

        run_metrics = get_run_metrics_snapshot()
        queue_pending = RunQueueEntry.objects.filter(status="pending").count()
        queue_processing = RunQueueEntry.objects.filter(status="processing").count()

        payload: dict[str, Any] = {
            "runs": {
                "started_total": run_metrics.run_started_total,
                "completed_total": run_metrics.run_completed_total,
                "failed_total": run_metrics.run_failed_total,
                "canceled_total": run_metrics.run_canceled_total,
                "success_rate": run_metrics.run_success_rate,
                "latency_ms_p50": run_metrics.run_latency_ms_p50,
                "latency_ms_p95": run_metrics.run_latency_ms_p95,
                "window_size": run_metrics.window_size,
            },
            "queue": {
                "pending": queue_pending,
                "processing": queue_processing,
            },
            "slo": {
                "run_success_rate_target": getattr(settings, "SLO_RUN_SUCCESS_RATE", 0.99),
                "run_p95_latency_ms_target": getattr(settings, "SLO_RUN_P95_LATENCY_MS", 60000),
                "queue_max_depth_target": getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500),
            },
            "violations": {
                "run_success_rate": (
                    run_metrics.run_success_rate is not None
                    and run_metrics.run_success_rate
                    < float(getattr(settings, "SLO_RUN_SUCCESS_RATE", 0.99))
                ),
                "run_p95_latency": (
                    run_metrics.run_latency_ms_p95 is not None
                    and run_metrics.run_latency_ms_p95
                    > float(getattr(settings, "SLO_RUN_P95_LATENCY_MS", 60000))
                ),
                "queue_depth": (queue_pending + queue_processing)
                > int(getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500)),
            },
            "generated_at": run_metrics.generated_at,
        }

        return success_response(payload)
