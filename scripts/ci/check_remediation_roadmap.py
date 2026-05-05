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
]

REQUIRED_TEXT = {
    "docs/ops/remediation-roadmap-coverage.md": [
        "P1.3 canonical event envelope | Covered",
        "P2.4 formal run state machine | Covered",
        "Remaining No-Go Blockers",
        "three successful Gate E reports",
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
