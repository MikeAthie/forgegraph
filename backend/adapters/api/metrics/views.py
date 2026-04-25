"""
Metrics API views.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.metrics import (
    get_api_metrics_snapshot,
    get_run_metrics_snapshot,
    get_websocket_metrics_snapshot,
)
from application.services.runtime_transport_metrics import (
    get_runtime_transport_metrics_snapshot,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import Run, RunQueueEntry, User


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
        websocket_metrics = get_websocket_metrics_snapshot()
        api_metrics = get_api_metrics_snapshot()
        runtime_transport_metrics = get_runtime_transport_metrics_snapshot()
        queue_pending = RunQueueEntry.objects.filter(status="pending").count()
        queue_processing = RunQueueEntry.objects.filter(status="processing").count()
        queue_total = queue_pending + queue_processing
        oldest_pending = (
            RunQueueEntry.objects.filter(status="pending").order_by("available_at").first()
        )
        oldest_pending_age_seconds: float | None = None
        if oldest_pending is not None:
            oldest_pending_age_seconds = max(
                0.0, (timezone.now() - oldest_pending.available_at).total_seconds()
            )
        queue_by_tenant = (
            RunQueueEntry.objects.filter(status__in=["pending", "processing"])
            .values("tenant_id")
            .annotate(
                pending=Count("id", filter=Q(status="pending")),
                processing=Count("id", filter=Q(status="processing")),
            )
            .order_by("-pending", "-processing")[:10]
        )
        active_runs = Run.objects.filter(status__in=["pending", "running", "paused"]).count()
        failure_rate = None
        if run_metrics.run_completed_total > 0:
            failure_rate = float(run_metrics.run_failed_total) / float(
                run_metrics.run_completed_total
            )

        payload: dict[str, Any] = {
            "runs": {
                "started_total": run_metrics.run_started_total,
                "completed_total": run_metrics.run_completed_total,
                "failed_total": run_metrics.run_failed_total,
                "canceled_total": run_metrics.run_canceled_total,
                "success_rate": run_metrics.run_success_rate,
                "failure_rate": failure_rate,
                "latency_ms_p50": run_metrics.run_latency_ms_p50,
                "latency_ms_p95": run_metrics.run_latency_ms_p95,
                "window_size": run_metrics.window_size,
                "active_total": active_runs,
                "liveness_reconciled_total": run_metrics.liveness_reconciled_total,
                "liveness_reconciled_by_reason": run_metrics.liveness_reconciled_by_reason,
                "stale_attempt_ignored_total": run_metrics.stale_attempt_ignored_total,
                "stale_attempt_ignored_by_source": run_metrics.stale_attempt_ignored_by_source,
            },
            "queue": {
                "pending": queue_pending,
                "processing": queue_processing,
                "total_depth": queue_total,
                "oldest_pending_age_seconds": oldest_pending_age_seconds,
                "by_tenant": [
                    {
                        "tenant_id": str(item["tenant_id"]),
                        "pending": int(item["pending"]),
                        "processing": int(item["processing"]),
                        "total": int(item["pending"]) + int(item["processing"]),
                    }
                    for item in queue_by_tenant
                ],
            },
            "websocket": {
                "active_connections": websocket_metrics.active_connections,
                "connection_failures_total": websocket_metrics.connection_failures_total,
                "messages_sent_total": websocket_metrics.messages_sent_total,
                "messages_dropped_total": websocket_metrics.messages_dropped_total,
                "message_rate_per_minute": websocket_metrics.message_rate_per_minute,
            },
            "api": {
                "requests_total": api_metrics.requests_total,
                "server_errors_total": api_metrics.server_errors_total,
                "latency_ms_p50": api_metrics.latency_ms_p50,
                "latency_ms_p95": api_metrics.latency_ms_p95,
                "callback_auth_failures_total": api_metrics.callback_auth_failures_total,
                "callback_auth_failures_by_reason": api_metrics.callback_auth_failures_by_reason,
            },
            "runtime_transport": {
                "intent_publish_failures_total": (
                    runtime_transport_metrics.intent_publish_failures_total
                ),
                "intent_received_total": runtime_transport_metrics.intent_received_total,
                "intent_applied_total": runtime_transport_metrics.intent_applied_total,
                "intent_ack_total": runtime_transport_metrics.intent_ack_total,
                "intent_reclaimed_total": runtime_transport_metrics.intent_reclaimed_total,
                "duplicate_intent_ignored_total": (
                    runtime_transport_metrics.duplicate_intent_ignored_total
                ),
                "dead_lettered_total": runtime_transport_metrics.dead_lettered_total,
                "stream_pending": runtime_transport_metrics.stream_pending,
                "stream_lag": runtime_transport_metrics.stream_lag,
                "stream_backlog": runtime_transport_metrics.stream_backlog,
                "consumer_idle_ms": runtime_transport_metrics.consumer_idle_ms,
                "oldest_pending_idle_ms": runtime_transport_metrics.oldest_pending_idle_ms,
                "dead_letter_count": runtime_transport_metrics.dead_letter_count,
                "generated_at": runtime_transport_metrics.generated_at,
            },
            "slo": {
                "run_success_rate_target": getattr(settings, "SLO_RUN_SUCCESS_RATE", 0.99),
                "run_p95_latency_ms_target": getattr(settings, "SLO_RUN_P95_LATENCY_MS", 60000),
                "queue_max_depth_target": getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500),
            },
            "guardrails": {
                "run_max_active_per_tenant": getattr(settings, "RUN_MAX_ACTIVE_PER_TENANT", 0),
                "run_input_max_bytes": getattr(settings, "RUN_INPUT_MAX_BYTES", 0),
                "queue_max_concurrency_per_tenant": getattr(
                    settings, "RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT", 0
                ),
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
                "queue_depth": queue_total > int(getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500)),
            },
            "generated_at": run_metrics.generated_at,
        }

        return success_response(payload)
