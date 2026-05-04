from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_stress_runner_module():
    module_path = Path(__file__).resolve().parents[4] / "scripts" / "stress_runner.py"
    spec = importlib.util.spec_from_file_location("stress_runner", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_error_recognizes_timeout_and_connection():
    module = _load_stress_runner_module()

    assert module.classify_error("deadline exceeded while waiting for response") == "timeout"
    assert module.classify_error("connection refused by upstream") == "connection"
    assert module.classify_error("too many requests", http_status=429) == "rate_limit"


def test_compute_metrics_and_analysis_detect_breaking_point():
    module = _load_stress_runner_module()

    harness = object.__new__(module.StressHarness)
    records = [
        module.RunRecord(
            scenario="endpoint-saturation",
            concurrency=5,
            tenant_slot=0,
            run_id="run-1",
            start_time="2026-04-25T00:00:00+00:00",
            end_time="2026-04-25T00:00:01+00:00",
            latency_ms=1000,
            status="success",
            error="",
            error_type="unknown",
        ),
        module.RunRecord(
            scenario="endpoint-saturation",
            concurrency=10,
            tenant_slot=0,
            run_id="run-2",
            start_time="2026-04-25T00:00:02+00:00",
            end_time="2026-04-25T00:00:04+00:00",
            latency_ms=2000,
            status="failure",
            error="provider timeout",
            error_type="timeout",
            node_retry_count=1,
            redis_backlog=8,
        ),
    ]

    metrics = module.StressHarness.compute_metrics(
        harness,
        records,
        metrics_before={},
        metrics_after={},
    )
    analysis = module.StressHarness.analyze_scenario(
        harness,
        scenario="endpoint-saturation",
        concurrency_levels=[5, 10],
        records=records,
        failure_plan=None,
    )

    assert metrics.total_runs == 2
    assert metrics.successful_runs == 1
    assert metrics.failed_runs == 1
    assert metrics.timeouts == 1
    assert metrics.retry_count == 1
    assert analysis.breaking_point == "concurrency 10"
    assert analysis.first_failure_type == "timeout"
    assert analysis.system_behavior == "stalls"
    assert analysis.data_integrity == "safe"


def test_phase3_gate_evaluation_blocks_missing_evidence():
    module = _load_stress_runner_module()

    result = module.ScenarioResult(
        scenario="endpoint-saturation",
        started_at="2026-04-25T00:00:00+00:00",
        completed_at="2026-04-25T00:00:10+00:00",
        concurrency_levels=[25],
        runs_per_level=25,
        duration_seconds=10,
        capacity_gate="A",
        requested_features={},
        records=[],
        metrics=module.ScenarioMetrics(
            total_runs=25,
            successful_runs=25,
            failed_runs=0,
            avg_latency_ms=100,
            max_latency_ms=120,
            latency_p95_ms=120,
            timeouts=0,
            retry_count=0,
            duplicate_node_execution_count=0,
            error_types={},
            max_queue_backlog=0,
            max_runtime_backlog=0,
            max_runtime_lag=0,
            backend_api_latency_p95_ms=100,
            websocket_send_latency_p95_ms=100,
            backend_api_latency_within_target=True,
            websocket_send_latency_within_target=True,
            websocket_messages_dropped_delta=0,
            runtime_dead_letter_delta=0,
            queue_bounded=True,
            success_rate=1.0,
            dead_letter_rate=0.0,
            event_dead_letter_delta=0,
            projection_lag_p95_ms=100,
            event_ingestion_latency_p95_ms=100,
            tenant_slots=1,
            decision_count=0,
            memory_write_count=0,
            cost_usd_total=0.0,
            websocket_reconnects=0,
            duplicate_event_attempts=0,
        ),
        analysis=module.FailureAnalysis(
            scenario="endpoint-saturation",
            breaking_point="not observed up to concurrency 25",
            first_failure_type="none",
            system_behavior="degrades",
            data_integrity="safe",
        ),
    )

    evaluation = module.evaluate_phase3_gate(result, tenant_client_count=1)

    assert evaluation is not None
    assert evaluation.passed is False
    assert evaluation.requirements["duration"] is False


def test_phase3_gate_aggregates_multiple_scenarios():
    module = _load_stress_runner_module()

    def metrics(*, websocket_reconnects: int) -> object:
        return module.ScenarioMetrics(
            total_runs=250,
            successful_runs=250,
            failed_runs=0,
            avg_latency_ms=100,
            max_latency_ms=120,
            latency_p95_ms=120,
            timeouts=0,
            retry_count=0,
            duplicate_node_execution_count=0,
            error_types={},
            max_queue_backlog=0,
            max_runtime_backlog=0,
            max_runtime_lag=0,
            backend_api_latency_p95_ms=100,
            websocket_send_latency_p95_ms=100,
            backend_api_latency_within_target=True,
            websocket_send_latency_within_target=True,
            websocket_messages_dropped_delta=0,
            runtime_dead_letter_delta=0,
            queue_bounded=True,
            success_rate=1.0,
            dead_letter_rate=0.0,
            event_dead_letter_delta=0,
            projection_lag_p95_ms=100,
            event_ingestion_latency_p95_ms=100,
            tenant_slots=10,
            decision_count=0,
            memory_write_count=0,
            cost_usd_total=0.0,
            websocket_reconnects=websocket_reconnects,
            duplicate_event_attempts=0,
        )

    def result(
        *,
        scenario: str,
        started_at: str,
        completed_at: str,
        websocket_reconnects: int,
    ) -> object:
        return module.ScenarioResult(
            scenario=scenario,
            started_at=started_at,
            completed_at=completed_at,
            concurrency_levels=[250],
            runs_per_level=250,
            duration_seconds=14400,
            capacity_gate="D",
            requested_features={"ws_reconnects": True},
            records=[],
            metrics=metrics(websocket_reconnects=websocket_reconnects),
            analysis=module.FailureAnalysis(
                scenario=scenario,
                breaking_point="not observed up to concurrency 250",
                first_failure_type="none",
                system_behavior="degrades",
                data_integrity="safe",
            ),
        )

    aggregate = module.aggregate_phase3_gate_result(
        [
            result(
                scenario="endpoint-saturation",
                started_at="2026-04-25T00:00:00+00:00",
                completed_at="2026-04-25T01:00:00+00:00",
                websocket_reconnects=0,
            ),
            result(
                scenario="websocket-reconnect-storm",
                started_at="2026-04-25T03:00:00+00:00",
                completed_at="2026-04-25T04:00:00+00:00",
                websocket_reconnects=25,
            ),
        ],
        capacity_gate="D",
    )
    assert aggregate is not None

    evaluation = module.evaluate_phase3_gate(aggregate, tenant_client_count=10)

    assert evaluation is not None
    assert evaluation.passed is True
    assert aggregate.metrics.websocket_reconnects == 25
