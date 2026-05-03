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
