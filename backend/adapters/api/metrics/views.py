"""
Metrics API views.
"""

from __future__ import annotations

from datetime import timedelta
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
from application.services.rbac import has_min_role
from application.services.runtime_transport_observability import (
    get_runtime_transport_observability_snapshot,
)
from application.services.sre_readiness import build_sre_read_model
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
        runtime_transport_metrics = get_runtime_transport_observability_snapshot()
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
        stalled_before = timezone.now() - timedelta(
            seconds=max(
                int(
                    getattr(
                        settings,
                        "RUN_ENGINE_STALLED_TIMEOUT_SECONDS",
                        getattr(settings, "RUN_LIVENESS_TIMEOUT_SECONDS", 60),
                    )
                ),
                1,
            )
        )
        stalled_runs = (
            Run.objects.filter(status__in=["running", "resume_requested"])
            .filter(
                Q(last_progress_at__lt=stalled_before)
                | Q(last_progress_at__isnull=True, started_at__lt=stalled_before)
                | Q(status="resume_requested", resume_requested_at__lt=stalled_before)
            )
            .count()
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
        sre = build_sre_read_model(
            run_metrics=run_metrics,
            api_metrics=api_metrics,
            websocket_metrics=websocket_metrics,
            runtime_transport_metrics=runtime_transport_metrics,
            queue_total=queue_total,
            queue_processing=queue_processing,
            stalled_runs=stalled_runs,
            active_runs=active_runs,
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
                "stalled_total": stalled_runs,
                "liveness_reconciled_total": run_metrics.liveness_reconciled_total,
                "liveness_reconciled_by_reason": run_metrics.liveness_reconciled_by_reason,
                "stale_attempt_ignored_total": run_metrics.stale_attempt_ignored_total,
                "stale_attempt_ignored_by_source": run_metrics.stale_attempt_ignored_by_source,
            },
            "queue": {
                "pending": queue_pending,
                "processing": queue_processing,
                "total_depth": queue_total,
                "backlog": queue_total,
                "oldest_pending_age_seconds": oldest_pending_age_seconds,
                "stalled_runs": stalled_runs,
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
                "messages_filtered_total": websocket_metrics.messages_filtered_total,
                "slow_client_disconnects_total": (
                    websocket_metrics.slow_client_disconnects_total
                ),
                "message_rate_per_minute": websocket_metrics.message_rate_per_minute,
                "send_latency_ms_p50": websocket_metrics.send_latency_ms_p50,
                "send_latency_ms_p95": websocket_metrics.send_latency_ms_p95,
            },
            "api": {
                "requests_total": api_metrics.requests_total,
                "server_errors_total": api_metrics.server_errors_total,
                "timeout_like_requests_total": api_metrics.timeout_like_requests_total,
                "timeout_like_rate_per_minute": api_metrics.timeout_like_rate_per_minute,
                "timeout_threshold_ms": api_metrics.timeout_threshold_ms,
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
                "stream_length": runtime_transport_metrics.stream_length,
                "pending": runtime_transport_metrics.pending,
                "lag": runtime_transport_metrics.lag,
                "backlog": runtime_transport_metrics.backlog,
                "stream_pending": runtime_transport_metrics.pending,
                "stream_lag": runtime_transport_metrics.lag,
                "stream_backlog": runtime_transport_metrics.backlog,
                "consumer_idle_ms": runtime_transport_metrics.consumer_idle_ms,
                "oldest_pending_idle_ms": runtime_transport_metrics.oldest_pending_idle_ms,
                "dead_letter_count": runtime_transport_metrics.dead_letter_count,
                "source": runtime_transport_metrics.source,
                "error": runtime_transport_metrics.error,
                "generated_at": runtime_transport_metrics.generated_at,
            },
            "slo": {
                "api_availability_beta_target": getattr(
                    settings, "SLO_API_AVAILABILITY_BETA", 0.995
                ),
                "api_availability_production_target": getattr(
                    settings, "SLO_API_AVAILABILITY_PRODUCTION", 0.999
                ),
                "runtime_intent_processing_p95_ms_target": getattr(
                    settings,
                    "SLO_RUNTIME_INTENT_PROCESSING_P95_MS",
                    1000,
                ),
                "approval_to_resume_p95_ms_target": getattr(
                    settings, "SLO_APPROVAL_TO_RESUME_P95_MS", 5000
                ),
                "task_projection_lag_p95_ms_target": getattr(
                    settings, "SLO_TASK_PROJECTION_LAG_P95_MS", 2000
                ),
                "dead_letter_visibility_seconds_target": getattr(
                    settings, "SLO_DEAD_LETTER_VISIBILITY_SECONDS", 30
                ),
                "silent_task_loss_max": getattr(settings, "SLO_SILENT_TASK_LOSS_MAX", 0),
                "run_success_rate_target": getattr(settings, "SLO_RUN_SUCCESS_RATE", 0.99),
                "run_p95_latency_ms_target": getattr(settings, "SLO_RUN_P95_LATENCY_MS", 60000),
                "queue_max_depth_target": getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500),
                "api_p95_latency_ms_target": getattr(
                    settings,
                    "SLO_API_P95_LATENCY_MS",
                    5000,
                ),
                "websocket_send_p95_latency_ms_target": getattr(
                    settings,
                    "SLO_WEBSOCKET_SEND_P95_LATENCY_MS",
                    2000,
                ),
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
                "api_p95_latency": (
                    api_metrics.latency_ms_p95 is not None
                    and api_metrics.latency_ms_p95
                    > float(getattr(settings, "SLO_API_P95_LATENCY_MS", 5000))
                ),
                "websocket_send_p95_latency": (
                    websocket_metrics.send_latency_ms_p95 is not None
                    and websocket_metrics.send_latency_ms_p95
                    > float(getattr(settings, "SLO_WEBSOCKET_SEND_P95_LATENCY_MS", 2000))
                ),
            },
            "sre": sre,
            "generated_at": run_metrics.generated_at,
        }

        return success_response(payload)


class MetricsSloView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User) or not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to access SLO metrics.",
                status=403,
            )

        run_metrics = get_run_metrics_snapshot()
        websocket_metrics = get_websocket_metrics_snapshot()
        api_metrics = get_api_metrics_snapshot()
        runtime_transport_metrics = get_runtime_transport_observability_snapshot()
        queue_pending = RunQueueEntry.objects.filter(status="pending").count()
        queue_processing = RunQueueEntry.objects.filter(status="processing").count()
        queue_total = queue_pending + queue_processing
        stalled_before = timezone.now() - timedelta(
            seconds=max(
                int(
                    getattr(
                        settings,
                        "RUN_ENGINE_STALLED_TIMEOUT_SECONDS",
                        getattr(settings, "RUN_LIVENESS_TIMEOUT_SECONDS", 60),
                    )
                ),
                1,
            )
        )
        stalled_runs = (
            Run.objects.filter(status__in=["running", "resume_requested"])
            .filter(
                Q(last_progress_at__lt=stalled_before)
                | Q(last_progress_at__isnull=True, started_at__lt=stalled_before)
                | Q(status="resume_requested", resume_requested_at__lt=stalled_before)
            )
            .count()
        )
        active_runs = Run.objects.filter(status__in=["pending", "running", "paused"]).count()
        return success_response(
            build_sre_read_model(
                run_metrics=run_metrics,
                api_metrics=api_metrics,
                websocket_metrics=websocket_metrics,
                runtime_transport_metrics=runtime_transport_metrics,
                queue_total=queue_total,
                queue_processing=queue_processing,
                stalled_runs=stalled_runs,
                active_runs=active_runs,
            )
        )
