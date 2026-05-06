#!/usr/bin/env python3
"""Verify remediation roadmap coverage artifacts stay present."""

from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_FILES = [
    "docs/architecture/state-ownership.md",
    "docs/architecture/event-contracts.md",
    "docs/architecture/frontend-state-contract.md",
    "docs/architecture/launch-claims.md",
    "docs/launch/claims-policy.md",
    "docs/ops/remediation-roadmap-coverage.md",
    "docs/ops/beta-launch-verification-plan.md",
    "docs/ops/event-spool-growth-runbook.md",
    "docs/ops/runbooks/event_spool_growth.md",
    "docs/ops/runbooks/dead_letter_spike.md",
    "docs/ops/runbooks/projection_lag.md",
    "docs/ops/runbooks/websocket_replay_failure.md",
    "docs/ops/runbooks/websocket_fanout_degradation.md",
    "docs/ops/runbooks/redis_degradation.md",
    "docs/ops/runbooks/llm_queue_saturation.md",
    "scripts/ci/check_engine_ownership.sh",
    "scripts/check-engine-ownership.ps1",
    "scripts/ci/check_architecture_signoff.py",
    "scripts/ci/check_launch_claims.py",
    "scripts/ci/check_capacity_claims.py",
    "scripts/ci/check_frontend_accounting_metrics.py",
    "scripts/ci/check_engine_event_envelope.sh",
    "scripts/ci/check_run_state_machine.py",
    "frontend/__tests__/unit/pages/financial-provenance.test.ts",
    "backend/tests/unit/api/test_projection_request_path_guardrails.py",
    "backend/tests/unit/services/test_state_feed.py",
    "backend/tests/unit/services/test_event_dead_letters.py",
    "backend/tests/unit/services/test_memory_intents.py",
    "backend/tests/unit/services/test_processed_commands.py",
    "backend/tests/unit/services/test_run_state_machine.py",
    "backend/tests/unit/scripts/test_stress_runner.py",
    "docs/perf/500-agent-benchmark.md",
    "tools/loadgen/go.mod",
    "scripts/ci/run_loadgen_smoke.sh",
    "scripts/ci/check_beta_capacity_evidence.py",
    "scripts/ci/run_beta_capacity_gates.sh",
    "scripts/ci/run_beta_pr_gate.sh",
    "scripts/ci/run_beta_nightly_gate.sh",
    "scripts/ci/run_beta_release_gate.sh",
]

REQUIRED_TEXT = {
    "docs/ops/remediation-roadmap-coverage.md": [
        "P1.3 canonical event envelope | Covered",
        "P2.4 formal run state machine | Covered",
        "Remaining No-Go Blockers",
        "Gate A and Gate B loadgen evidence",
        "three successful latest consecutive Gate E reports",
    ],
    "docs/ops/beta-launch-verification-plan.md": [
        "The target is a measured beta",
        "CI load smoke is regression evidence only",
        "tools/loadgen",
        "Gate A",
        "Gate B",
        "No public 500-agent claim",
    ],
    "docs/ops/production-evidence-gate.md": [
        "Beta Gate Profiles",
        "run_beta_pr_gate.sh",
        "run_beta_nightly_gate.sh",
        "run_beta_release_gate.sh",
        "check_beta_capacity_evidence.py",
    ],
    "docs/ops/scalability-program.md": [
        "Gate E must pass three consecutive checked-in reports",
        "tools/loadgen",
        "duplicate-event",
    ],
    "scripts/stress_runner.py": [
        "PHASE3_CAPACITY_GATES",
        "websocket-reconnect-storm",
        "duplicate-event-storm",
        "aggregate_phase3_gate_result",
    ],
    "scripts/ci/run_required_checks.sh": [
        "run_governance_checks.sh",
        "check_run_state_machine.py",
    ],
    "scripts/ci/run_beta_capacity_gates.sh": [
        "go run ./tools/loadgen",
        "check_beta_capacity_evidence.py",
    ],
    "scripts/ci/run_beta_release_gate.sh": [
        "run_local_production_evidence.sh",
        "run_beta_capacity_gates.sh",
        "run_docker_full_stack_smoke.sh",
    ],
    "scripts/ci/run_governance_checks.sh": [
        "check_architecture_signoff.py",
        "check_launch_claims.py",
        "check_frontend_accounting_metrics.py",
        "check_remediation_roadmap.py",
    ],
    "scripts/ci/check_engine_ownership.sh": [
        "Temporary engine durable memory exception manifest must not be reintroduced",
        "Engine durable product-memory persistence detected",
    ],
}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    failures: list[str] = []

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing required roadmap artifact: {relative}")

    for relative, snippets in REQUIRED_TEXT.items():
        path = root / relative
        if not path.is_file():
            failures.append(f"missing required roadmap text file: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                failures.append(f"{relative}: missing expected text: {snippet}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
