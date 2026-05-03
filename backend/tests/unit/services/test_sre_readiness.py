from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from django.utils import timezone

from application.services.sre_readiness import (
    REQUIRED_ALERT_IDS,
    REQUIRED_DASHBOARD_IDS,
    REQUIRED_SLO_IDS,
    build_sre_read_model,
    load_production_slo_catalog,
    validate_production_slo_catalog,
)
from infrastructure.orm.models import (
    DecisionRecord,
    Graph,
    GraphVersion,
    Run,
    RunEvent,
    RuntimeIntentOutcome,
    ServiceMetricSample,
    TaskDeadLetterRecord,
    TaskLifecycleRecord,
    TaskRecord,
)


def _snapshots():
    run_metrics = SimpleNamespace(run_success_rate=1.0)
    api_metrics = SimpleNamespace(
        requests_total=0,
        server_errors_total=0,
        timeout_like_rate_per_minute=0.0,
        latency_ms_p95=120.0,
        callback_auth_failures_total=0,
        callback_auth_failures_by_reason={},
    )
    websocket_metrics = SimpleNamespace(
        active_connections=0,
        send_latency_ms_p95=None,
        messages_sent_total=0,
        slow_client_disconnects_total=0,
    )
    runtime_transport_metrics = SimpleNamespace(
        backlog=0,
        lag=0,
        pending=0,
        dead_letter_count=0,
    )
    return run_metrics, api_metrics, websocket_metrics, runtime_transport_metrics


def test_production_slo_catalog_contains_required_targets():
    validation = validate_production_slo_catalog(load_production_slo_catalog())

    assert validation["missing_slos"] == set()
    assert validation["missing_dashboard_panels"] == set()
    assert validation["missing_alerts"] == set()
    assert REQUIRED_SLO_IDS
    assert REQUIRED_DASHBOARD_IDS
    assert REQUIRED_ALERT_IDS


def test_sre_read_model_uses_backend_owned_slo_sources(db, user):
    now = timezone.now()
    organization = user.default_organization
    graph = Graph.objects.create(owner=user, organization=organization, name="SRE Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [{"id": "approve", "type": "human_gate"}], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=now - timedelta(minutes=1),
    )

    for status_code, latency in [(200, 120), (200, 180), (500, 250)]:
        ServiceMetricSample.objects.create(
            metric_name="api_request_duration_ms",
            source="test",
            organization=organization,
            value=latency,
            unit="ms",
            dimensions={"status_code": status_code, "path": "/api/runs", "method": "GET"},
            observed_at=now - timedelta(seconds=10),
        )
    ServiceMetricSample.objects.create(
        metric_name="runtime_intent_processing_ms",
        source="test",
        organization=organization,
        run=run,
        value=420,
        unit="ms",
        observed_at=now - timedelta(seconds=9),
    )
    ServiceMetricSample.objects.create(
        metric_name="websocket_delivery_ms",
        source="test",
        organization=organization,
        run=run,
        value=75,
        unit="ms",
        observed_at=now - timedelta(seconds=8),
    )
    ServiceMetricSample.objects.create(
        metric_name="llm_queue_depth",
        source="test",
        organization=organization,
        value=3,
        unit="count",
        observed_at=now - timedelta(seconds=7),
    )

    decision = DecisionRecord.objects.create(
        organization=organization,
        execution=run,
        decision_type="human_approval",
        status="approved",
        external_key=f"decision:{run.id}",
        requested_at=now - timedelta(seconds=20),
        resolved_at=now - timedelta(seconds=5),
    )
    RunEvent.objects.create(
        run=run,
        event_type="ack_run_resumed",
        external_id=f"ack:{run.id}",
        payload={"decision_id": str(decision.id)},
        created_at=now - timedelta(seconds=3),
    )

    lifecycle = TaskLifecycleRecord.objects.create(
        organization=organization,
        run=run,
        source_node_id="approve",
        external_key=f"{run.id}:approve",
        title="Approval task",
        status="running",
        last_transition_at=now - timedelta(seconds=4),
    )
    task = TaskRecord.objects.create(
        organization=organization,
        execution=run,
        lifecycle_task=lifecycle,
        source_node_id="approve",
        external_key=f"task:{run.id}:approve",
        title="Approval task",
        status="running",
    )
    TaskRecord.objects.filter(id=task.id).update(updated_at=now - timedelta(seconds=3))

    outcome = RuntimeIntentOutcome.objects.create(
        intent_id=uuid4(),
        run=run,
        intent_type="task_lifecycle_transition",
        outcome="dead_lettered",
        reason="poison message",
    )
    TaskDeadLetterRecord.objects.create(
        lifecycle_task=lifecycle,
        run=run,
        runtime_intent_outcome=outcome,
        reason="poison message",
        attempt_count=3,
        last_error="bad payload",
        recovery_options=["acknowledge"],
    )

    run_metrics, api_metrics, websocket_metrics, runtime_transport_metrics = _snapshots()
    payload = build_sre_read_model(
        run_metrics=run_metrics,
        api_metrics=api_metrics,
        websocket_metrics=websocket_metrics,
        runtime_transport_metrics=runtime_transport_metrics,
        queue_total=0,
        queue_processing=0,
        stalled_runs=0,
        active_runs=1,
    )

    objectives = {item["id"]: item for item in payload["objectives"]}
    panels = {item["id"]: item for item in payload["dashboard_panels"]}
    alerts = {item["id"]: item for item in payload["alerts"]["items"]}

    assert objectives["api_availability"]["actual"] == 2 / 3
    assert objectives["runtime_intent_processing_p95"]["missing_data"] is False
    assert objectives["websocket_delivery_p95"]["actual"] == 75
    assert objectives["approval_to_resume_p95"]["actual"] is not None
    assert objectives["task_projection_lag_p95"]["actual"] is not None
    assert objectives["silent_task_loss"]["actual"] == 0
    assert panels["llm_queue_depth"]["value"] == 3
    assert panels["dead_letter_count"]["value"] >= 1
    assert alerts["dead_letter_spike"]["state"] == "active"
