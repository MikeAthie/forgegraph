from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from application.services.backend_watchdog import evaluate_backend_watchdog
from infrastructure.orm.models import (
    AuditLog,
    CostLedgerEntry,
    DecisionRecord,
    MemoryObservation,
    RetryOperation,
    Run,
    RunEvent,
    RuntimeIntentOutcome,
    ServiceMetricSample,
    TaskDeadLetterRecord,
    TaskLifecycleRecord,
    TaskRecord,
)

REQUIRED_SLO_IDS = {
    "api_availability",
    "runtime_intent_processing_p95",
    "websocket_delivery_p95",
    "approval_to_resume_p95",
    "task_projection_lag_p95",
    "dead_letter_visibility",
    "backend_health_recovery",
    "silent_task_loss",
}

REQUIRED_DASHBOARD_IDS = {
    "runtime_intent_backlog",
    "runtime_intent_lag",
    "dead_letter_count",
    "run_status_distribution",
    "stuck_runs",
    "paused_runs",
    "approval_latency",
    "resume_failure_rate",
    "websocket_connected_clients",
    "websocket_fanout_latency",
    "backend_api_latency",
    "engine_queue_depth",
    "llm_queue_depth",
    "llm_timeout_rate",
    "cost_per_org",
    "memory_write_rate",
    "audit_event_rate",
}

REQUIRED_ALERT_IDS = {
    "intent_backlog_growing",
    "no_progress_despite_backlog",
    "dead_letter_spike",
    "approval_resume_failures",
    "backend_health_degradation",
    "engine_callback_signature_failures",
    "websocket_fanout_degradation",
    "org_rate_limit_breach",
    "llm_queue_saturation",
    "cost_anomaly",
}

Comparison = Literal["gte", "lte"]


@dataclass(frozen=True)
class Objective:
    id: str
    title: str
    target: float
    actual: float | None
    unit: str
    comparison: Comparison
    source: str
    observed_count: int
    missing_data: bool
    description: str = ""

    def as_payload(self) -> dict[str, Any]:
        if self.missing_data:
            status = "no_data"
        elif self.actual is None:
            status = "no_data"
        elif self.comparison == "gte":
            status = "passing" if self.actual >= self.target else "breaching"
        else:
            status = "passing" if self.actual <= self.target else "breaching"
        return {
            "id": self.id,
            "title": self.title,
            "target": self.target,
            "actual": self.actual,
            "unit": self.unit,
            "comparison": self.comparison,
            "status": status,
            "source": self.source,
            "observed_count": self.observed_count,
            "missing_data": self.missing_data,
            "description": self.description,
        }


def load_production_slo_catalog() -> dict[str, Any]:
    catalog_path = production_slo_catalog_path()
    return yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}


def production_slo_catalog_path() -> Path:
    return Path(settings.BASE_DIR).parent / "docs" / "ops" / "production-slos.yaml"


def validate_production_slo_catalog(catalog: dict[str, Any] | None = None) -> dict[str, set[str]]:
    catalog = catalog if catalog is not None else load_production_slo_catalog()
    slo_ids = {str(item.get("id")) for item in catalog.get("slo_targets", [])}
    dashboard_ids = {str(item.get("id")) for item in catalog.get("dashboard_panels", [])}
    alert_ids = {str(item.get("id")) for item in catalog.get("alert_rules", [])}
    return {
        "missing_slos": REQUIRED_SLO_IDS - slo_ids,
        "missing_dashboard_panels": REQUIRED_DASHBOARD_IDS - dashboard_ids,
        "missing_alerts": REQUIRED_ALERT_IDS - alert_ids,
    }


def build_sre_read_model(
    *,
    run_metrics: Any,
    api_metrics: Any,
    websocket_metrics: Any,
    runtime_transport_metrics: Any,
    queue_total: int,
    queue_processing: int,
    stalled_runs: int,
    active_runs: int,
) -> dict[str, Any]:
    now = timezone.now()
    window_seconds = int(getattr(settings, "SLO_EVALUATION_WINDOW_SECONDS", 3600))
    since = now - timedelta(seconds=max(window_seconds, 60))
    catalog = load_production_slo_catalog()
    validation = validate_production_slo_catalog(catalog)
    release_tier = str(getattr(settings, "FORGEGRAPH_RELEASE_TIER", "beta")).strip().lower()

    objectives = _build_objectives(
        since=since,
        release_tier=release_tier,
        api_metrics=api_metrics,
        websocket_metrics=websocket_metrics,
        runtime_transport_metrics=runtime_transport_metrics,
    )
    objective_payloads = [objective.as_payload() for objective in objectives]
    dashboard_panels = _build_dashboard_panels(
        since=since,
        objectives=objective_payloads,
        run_metrics=run_metrics,
        api_metrics=api_metrics,
        websocket_metrics=websocket_metrics,
        runtime_transport_metrics=runtime_transport_metrics,
        queue_total=queue_total,
        queue_processing=queue_processing,
        stalled_runs=stalled_runs,
        active_runs=active_runs,
    )
    alerts = _evaluate_alerts(
        since=since,
        objectives=objective_payloads,
        dashboard_panels=dashboard_panels,
        api_metrics=api_metrics,
        websocket_metrics=websocket_metrics,
        runtime_transport_metrics=runtime_transport_metrics,
        queue_total=queue_total,
        stalled_runs=stalled_runs,
    )

    return {
        "catalog_version": catalog.get("version", 1),
        "catalog_path": "docs/ops/production-slos.yaml",
        "release_tier": release_tier,
        "window_seconds": window_seconds,
        "objectives": objective_payloads,
        "dashboard_panels": dashboard_panels,
        "alerts": {
            "active_total": sum(1 for alert in alerts if alert["state"] == "active"),
            "items": alerts,
        },
        "catalog_validation": {
            key: sorted(value) for key, value in validation.items()
        },
        "generated_at": now.isoformat(),
    }


def _build_objectives(
    *,
    since: Any,
    release_tier: str,
    api_metrics: Any,
    websocket_metrics: Any,
    runtime_transport_metrics: Any,
) -> list[Objective]:
    api_availability, api_total, api_source = _api_availability(since, api_metrics)
    runtime_p95, runtime_count = _sample_p95("runtime_intent_processing_ms", since)
    websocket_p95, websocket_count = _sample_p95("websocket_delivery_ms", since)
    websocket_source = "durable_metric_samples"
    if websocket_p95 is None and websocket_metrics.send_latency_ms_p95 is not None:
        websocket_p95 = float(websocket_metrics.send_latency_ms_p95)
        websocket_count = int(getattr(websocket_metrics, "messages_sent_total", 0))
        websocket_source = "process_snapshot"

    approval_p95, approval_count = _approval_to_resume_p95(since)
    projection_p95, projection_count = _task_projection_lag_p95(since)
    dead_letter_visibility, dead_letter_count = _dead_letter_visibility_seconds(since)
    watchdog = evaluate_backend_watchdog()
    silent_loss_count = _silent_task_loss_count()

    api_target = (
        float(getattr(settings, "SLO_API_AVAILABILITY_PRODUCTION", 0.999))
        if release_tier in {"production", "prod", "production_v1", "production-v1"}
        else float(getattr(settings, "SLO_API_AVAILABILITY_BETA", 0.995))
    )

    return [
        Objective(
            id="api_availability",
            title="API availability",
            target=api_target,
            actual=api_availability,
            unit="ratio",
            comparison="gte",
            source=api_source,
            observed_count=api_total,
            missing_data=api_total == 0,
            description="Successful API requests divided by all production API requests in the SLO window.",
        ),
        Objective(
            id="runtime_intent_processing_p95",
            title="Runtime intent processing p95",
            target=float(getattr(settings, "SLO_RUNTIME_INTENT_PROCESSING_P95_MS", 1000)),
            actual=runtime_p95,
            unit="ms",
            comparison="lte",
            source="durable_metric_samples",
            observed_count=runtime_count,
            missing_data=runtime_count == 0,
        ),
        Objective(
            id="websocket_delivery_p95",
            title="WebSocket delivery p95",
            target=float(getattr(settings, "SLO_WEBSOCKET_DELIVERY_P95_MS", 2000)),
            actual=websocket_p95,
            unit="ms",
            comparison="lte",
            source=websocket_source,
            observed_count=websocket_count,
            missing_data=websocket_count == 0,
        ),
        Objective(
            id="approval_to_resume_p95",
            title="Approval-to-resume p95",
            target=float(getattr(settings, "SLO_APPROVAL_TO_RESUME_P95_MS", 5000)),
            actual=approval_p95,
            unit="ms",
            comparison="lte",
            source="backend_ledger",
            observed_count=approval_count,
            missing_data=approval_count == 0,
        ),
        Objective(
            id="task_projection_lag_p95",
            title="Task projection lag p95",
            target=float(getattr(settings, "SLO_TASK_PROJECTION_LAG_P95_MS", 2000)),
            actual=projection_p95,
            unit="ms",
            comparison="lte",
            source="backend_ledger",
            observed_count=projection_count,
            missing_data=projection_count == 0,
        ),
        Objective(
            id="dead_letter_visibility",
            title="Dead-letter visibility",
            target=float(getattr(settings, "SLO_DEAD_LETTER_VISIBILITY_SECONDS", 30)),
            actual=dead_letter_visibility,
            unit="seconds",
            comparison="lte",
            source="backend_ledger",
            observed_count=dead_letter_count,
            missing_data=False,
        ),
        Objective(
            id="backend_health_recovery",
            title="Backend health recovery",
            target=1.0,
            actual=1.0 if watchdog.healthy else 0.0,
            unit="healthy",
            comparison="gte",
            source="backend_watchdog",
            observed_count=1,
            missing_data=False,
            description="Expected load must not require manual backend restart.",
        ),
        Objective(
            id="silent_task_loss",
            title="Silent task loss",
            target=float(getattr(settings, "SLO_SILENT_TASK_LOSS_MAX", 0)),
            actual=float(silent_loss_count),
            unit="count",
            comparison="lte",
            source="backend_ledger",
            observed_count=1,
            missing_data=False,
        ),
    ]


def _build_dashboard_panels(
    *,
    since: Any,
    objectives: list[dict[str, Any]],
    run_metrics: Any,
    api_metrics: Any,
    websocket_metrics: Any,
    runtime_transport_metrics: Any,
    queue_total: int,
    queue_processing: int,
    stalled_runs: int,
    active_runs: int,
) -> list[dict[str, Any]]:
    status_distribution = {
        row["status"]: int(row["count"])
        for row in Run.objects.values("status").annotate(count=Count("id")).order_by("status")
    }
    paused_runs = int(status_distribution.get("paused", 0))
    resume_failures = Run.objects.filter(
        recovery_state="resume_dispatch_failed",
        resume_requested_at__gte=since,
    ).count()
    approved_decisions = DecisionRecord.objects.filter(
        decision_type="human_approval",
        resolved_at__gte=since,
        status__in=["approved", "resolved"],
    ).count()
    resume_failure_rate = (
        float(resume_failures) / float(approved_decisions) if approved_decisions else 0.0
    )
    llm_queue_depth, llm_queue_missing = _latest_sample_value("llm_queue_depth", since)
    llm_timeout_count = _sample_count("llm_timeout", since)
    cost_by_org = _cost_by_org_since(since)
    memory_write_count = MemoryObservation.objects.filter(created_at__gte=since).count()
    audit_event_count = AuditLog.objects.filter(created_at__gte=since).count()
    window_minutes = max((timezone.now() - since).total_seconds() / 60.0, 1.0)

    objective_by_id = {item["id"]: item for item in objectives}
    return [
        _panel("runtime_intent_backlog", "Runtime intent backlog", runtime_transport_metrics.backlog, "count"),
        _panel("runtime_intent_lag", "Runtime intent lag", runtime_transport_metrics.lag, "count"),
        _panel("dead_letter_count", "Dead-letter count", _dead_letter_count(), "count"),
        _panel("run_status_distribution", "Run status distribution", status_distribution, "distribution"),
        _panel("stuck_runs", "Stuck runs", stalled_runs, "count"),
        _panel("paused_runs", "Paused runs", paused_runs, "count"),
        _panel(
            "approval_latency",
            "Approval latency",
            objective_by_id["approval_to_resume_p95"]["actual"],
            "ms",
            missing_data=objective_by_id["approval_to_resume_p95"]["missing_data"],
        ),
        _panel("resume_failure_rate", "Resume failure rate", resume_failure_rate, "ratio"),
        _panel("websocket_connected_clients", "WebSocket connected clients", websocket_metrics.active_connections, "count"),
        _panel(
            "websocket_fanout_latency",
            "WebSocket fanout latency",
            objective_by_id["websocket_delivery_p95"]["actual"],
            "ms",
            missing_data=objective_by_id["websocket_delivery_p95"]["missing_data"],
        ),
        _panel("backend_api_latency", "Backend API latency", api_metrics.latency_ms_p95, "ms", missing_data=api_metrics.latency_ms_p95 is None),
        _panel("engine_queue_depth", "Engine queue depth", queue_total, "count"),
        _panel("llm_queue_depth", "LLM queue depth", llm_queue_depth, "count", missing_data=llm_queue_missing),
        _panel("llm_timeout_rate", "LLM timeout rate", llm_timeout_count / window_minutes, "per_minute"),
        _panel("cost_per_org", "Cost per org", cost_by_org, "usd"),
        _panel("memory_write_rate", "Memory write rate", memory_write_count / window_minutes, "per_minute"),
        _panel("audit_event_rate", "Audit event rate", audit_event_count / window_minutes, "per_minute"),
        _panel("active_runs", "Active runs", active_runs, "count"),
        _panel("api_availability", "API availability", objective_by_id["api_availability"]["actual"], "ratio", missing_data=objective_by_id["api_availability"]["missing_data"]),
        _panel("api_timeouts", "API timeout-like requests", api_metrics.timeout_like_rate_per_minute, "per_minute"),
        _panel("callback_auth_failures", "Callback signature failures", api_metrics.callback_auth_failures_total, "count"),
        _panel("run_success_rate", "Run success rate", run_metrics.run_success_rate, "ratio", missing_data=run_metrics.run_success_rate is None),
    ]


def _evaluate_alerts(
    *,
    since: Any,
    objectives: list[dict[str, Any]],
    dashboard_panels: list[dict[str, Any]],
    api_metrics: Any,
    websocket_metrics: Any,
    runtime_transport_metrics: Any,
    queue_total: int,
    stalled_runs: int,
) -> list[dict[str, Any]]:
    objective_by_id = {item["id"]: item for item in objectives}
    panel_by_id = {item["id"]: item for item in dashboard_panels}
    watchdog = evaluate_backend_watchdog()
    dead_letters = _dead_letter_count()
    rate_limit_breaches = _sample_count("api_rate_limit_breach", since)
    llm_queue_depth, llm_queue_missing = _latest_sample_value("llm_queue_depth", since)
    llm_timeouts = _sample_count("llm_timeout", since)
    cost_values = panel_by_id["cost_per_org"]["value"]
    max_org_cost = max((float(item["total_cost_usd"]) for item in cost_values), default=0.0)

    return [
        _alert(
            "intent_backlog_growing",
            active=runtime_transport_metrics.backlog
            > int(getattr(settings, "SLO_RUNTIME_INTENT_BACKLOG_WARNING", 50)),
            evidence={"backlog": runtime_transport_metrics.backlog, "lag": runtime_transport_metrics.lag},
        ),
        _alert(
            "no_progress_despite_backlog",
            active=runtime_transport_metrics.backlog > 0 and stalled_runs > 0,
            evidence={"backlog": runtime_transport_metrics.backlog, "stalled_runs": stalled_runs},
        ),
        _alert(
            "dead_letter_spike",
            active=dead_letters >= int(getattr(settings, "SLO_DEAD_LETTER_SPIKE_THRESHOLD", 1)),
            evidence={"dead_letters": dead_letters},
        ),
        _alert(
            "approval_resume_failures",
            active=bool(
                objective_by_id["approval_to_resume_p95"]["status"] == "breaching"
                or panel_by_id["resume_failure_rate"]["value"] > 0
            ),
            evidence={
                "approval_to_resume_p95_ms": objective_by_id["approval_to_resume_p95"]["actual"],
                "resume_failure_rate": panel_by_id["resume_failure_rate"]["value"],
            },
        ),
        _alert(
            "backend_health_degradation",
            active=not watchdog.healthy,
            evidence=watchdog.as_payload(),
        ),
        _alert(
            "engine_callback_signature_failures",
            active=api_metrics.callback_auth_failures_total
            > int(getattr(settings, "SLO_CALLBACK_AUTH_FAILURE_THRESHOLD", 0)),
            evidence={
                "callback_auth_failures_total": api_metrics.callback_auth_failures_total,
                "by_reason": api_metrics.callback_auth_failures_by_reason,
            },
        ),
        _alert(
            "websocket_fanout_degradation",
            active=bool(
                objective_by_id["websocket_delivery_p95"]["status"] == "breaching"
                or websocket_metrics.slow_client_disconnects_total
                > int(getattr(settings, "SLO_WS_SLOW_DISCONNECT_THRESHOLD", 0))
            ),
            evidence={
                "websocket_delivery_p95_ms": objective_by_id["websocket_delivery_p95"]["actual"],
                "slow_client_disconnects_total": websocket_metrics.slow_client_disconnects_total,
            },
        ),
        _alert(
            "org_rate_limit_breach",
            active=rate_limit_breaches > int(getattr(settings, "SLO_RATE_LIMIT_BREACH_THRESHOLD", 0)),
            evidence={"rate_limit_breaches": rate_limit_breaches},
        ),
        _alert(
            "llm_queue_saturation",
            active=(
                (llm_queue_depth is not None and llm_queue_depth >= float(getattr(settings, "SLO_LLM_QUEUE_DEPTH_THRESHOLD", 25)))
                or llm_timeouts > int(getattr(settings, "SLO_LLM_TIMEOUT_THRESHOLD", 0))
                or RetryOperation.objects.filter(
                    retry_class="llm_backpressure",
                    status__in=["scheduled", "running"],
                    updated_at__gte=since,
                ).exists()
            ),
            evidence={
                "llm_queue_depth": llm_queue_depth,
                "llm_queue_missing": llm_queue_missing,
                "llm_timeouts": llm_timeouts,
            },
            no_data=llm_queue_missing and llm_timeouts == 0,
        ),
        _alert(
            "cost_anomaly",
            active=max_org_cost >= float(getattr(settings, "SLO_COST_ANOMALY_USD_PER_WINDOW", 100.0)),
            evidence={"max_org_cost_usd": max_org_cost},
        ),
    ]


def _api_availability(since: Any, api_metrics: Any) -> tuple[float | None, int, str]:
    samples = list(
        ServiceMetricSample.objects.filter(
            metric_name="api_request_duration_ms",
            observed_at__gte=since,
        ).values("dimensions")
    )
    if samples:
        total = len(samples)
        errors = 0
        for sample in samples:
            status_code = _dimension_int(sample["dimensions"], "status_code")
            if status_code >= 500:
                errors += 1
        return (float(total - errors) / float(total), total, "durable_metric_samples")

    total = int(getattr(api_metrics, "requests_total", 0))
    if total <= 0:
        return (None, 0, "process_snapshot")
    errors = int(getattr(api_metrics, "server_errors_total", 0))
    return (float(max(total - errors, 0)) / float(total), total, "process_snapshot")


def _sample_p95(metric_name: str, since: Any) -> tuple[float | None, int]:
    values = list(
        ServiceMetricSample.objects.filter(
            metric_name=metric_name,
            observed_at__gte=since,
        ).values_list("value", flat=True)
    )
    return _percentile([float(value) for value in values], 0.95), len(values)


def _sample_count(metric_name: str, since: Any) -> int:
    return ServiceMetricSample.objects.filter(metric_name=metric_name, observed_at__gte=since).count()


def _latest_sample_value(metric_name: str, since: Any) -> tuple[float | None, bool]:
    value = (
        ServiceMetricSample.objects.filter(metric_name=metric_name, observed_at__gte=since)
        .order_by("-observed_at", "-created_at")
        .values_list("value", flat=True)
        .first()
    )
    if value is None:
        return None, True
    return float(value), False


def _approval_to_resume_p95(since: Any) -> tuple[float | None, int]:
    values: list[float] = []
    decisions = DecisionRecord.objects.filter(
        decision_type="human_approval",
        status__in=["approved", "resolved"],
        resolved_at__gte=since,
        resolved_at__isnull=False,
        execution__isnull=False,
    ).only("execution_id", "resolved_at")
    for decision in decisions:
        event = (
            RunEvent.objects.filter(
                run_id=decision.execution_id,
                created_at__gte=decision.resolved_at,
                event_type__in=["ack_run_resumed", "run_resumed"],
            )
            .order_by("created_at")
            .only("created_at")
            .first()
        )
        if event is not None:
            values.append(max(0.0, (event.created_at - decision.resolved_at).total_seconds() * 1000.0))
    return _percentile(values, 0.95), len(values)


def _task_projection_lag_p95(since: Any) -> tuple[float | None, int]:
    values: list[float] = []
    records = (
        TaskRecord.objects.filter(
            lifecycle_task__isnull=False,
            updated_at__gte=since,
            lifecycle_task__last_transition_at__isnull=False,
        )
        .select_related("lifecycle_task")
        .only("updated_at", "lifecycle_task__last_transition_at")
    )
    for record in records:
        transition_at = record.lifecycle_task.last_transition_at
        if transition_at is not None:
            values.append(max(0.0, (record.updated_at - transition_at).total_seconds() * 1000.0))
    return _percentile(values, 0.95), len(values)


def _dead_letter_visibility_seconds(since: Any) -> tuple[float, int]:
    values: list[float] = []
    dead_letters = (
        TaskDeadLetterRecord.objects.filter(created_at__gte=since)
        .select_related("runtime_intent_outcome")
        .only("created_at", "runtime_intent_outcome__processed_at")
    )
    for dead_letter in dead_letters:
        if dead_letter.runtime_intent_outcome_id and dead_letter.runtime_intent_outcome:
            values.append(
                max(
                    0.0,
                    (
                        dead_letter.created_at
                        - dead_letter.runtime_intent_outcome.processed_at
                    ).total_seconds(),
                )
            )
        else:
            values.append(0.0)
    if not values:
        return 0.0, 0
    return float(_percentile(values, 0.95) or 0.0), len(values)


def _silent_task_loss_count() -> int:
    terminal = {"completed", "failed", "dead_lettered", "cancelled"}
    lifecycle_without_projection = (
        TaskLifecycleRecord.objects.exclude(status__in=terminal)
        .filter(task_records__isnull=True)
        .count()
    )
    return int(lifecycle_without_projection)


def _dead_letter_count() -> int:
    return int(
        TaskDeadLetterRecord.objects.filter(status="active").count()
        + RuntimeIntentOutcome.objects.filter(
            outcome="dead_lettered",
            acknowledged_at__isnull=True,
        ).count()
    )


def _cost_by_org_since(since: Any) -> list[dict[str, Any]]:
    rows = (
        CostLedgerEntry.objects.filter(occurred_at__gte=since)
        .values("organization_id")
        .annotate(total=Sum("total_cost_usd"))
        .order_by("-total")[:10]
    )
    return [
        {
            "organization_id": str(row["organization_id"]),
            "total_cost_usd": float(row["total"] or 0),
        }
        for row in rows
    ]


def _panel(
    panel_id: str,
    title: str,
    value: Any,
    unit: str,
    *,
    missing_data: bool = False,
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "value": value,
        "unit": unit,
        "missing_data": missing_data,
    }


def _alert(
    alert_id: str,
    *,
    active: bool,
    evidence: dict[str, Any],
    no_data: bool = False,
) -> dict[str, Any]:
    if no_data:
        state = "no_data"
    else:
        state = "active" if active else "ok"
    severity = {
        "dead_letter_spike": "critical",
        "backend_health_degradation": "critical",
        "intent_backlog_growing": "warning",
        "no_progress_despite_backlog": "critical",
        "approval_resume_failures": "critical",
        "engine_callback_signature_failures": "warning",
        "websocket_fanout_degradation": "warning",
        "org_rate_limit_breach": "warning",
        "llm_queue_saturation": "warning",
        "cost_anomaly": "warning",
    }.get(alert_id, "warning")
    return {
        "id": alert_id,
        "title": alert_id.replace("_", " ").title(),
        "state": state,
        "severity": severity,
        "evidence": evidence,
        "runbook": f"docs/ops/runbooks/{alert_id}.md",
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * percentile
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def _dimension_int(dimensions: dict[str, Any], key: str) -> int:
    try:
        return int(dimensions.get(key) or 0)
    except (TypeError, ValueError):
        return 0
