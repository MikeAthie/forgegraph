#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
RUNTIME_INVARIANTS = REPO_ROOT / "docs" / "architecture" / "runtime-invariants.md"

IGNORED_PARTS = {
    "__pycache__",
    "migrations",
    "tests",
    "testsprite_tests",
    ".hermes",
    ".uv-review-venv",
    ".venv",
}

ALLOWED_RUNTIME_WRITERS = {
    Path("backend/adapters/api/engine/views.py"),
    Path("backend/adapters/api/integrations/run_dispatch.py"),
    Path("backend/adapters/api/operator/views.py"),
    Path("backend/adapters/api/runs/authenticated_event_views.py"),
    Path("backend/adapters/api/runs/cancel_view.py"),
    Path("backend/adapters/api/runs/command_dispatch.py"),
    Path("backend/adapters/api/runs/engine_callback_ingestion.py"),
    Path("backend/adapters/api/runs/engine_node_lifecycle.py"),
    Path("backend/adapters/api/runs/engine_run_lifecycle.py"),
    Path("backend/adapters/api/runs/invoke_view.py"),
    Path("backend/adapters/api/runs/replay_view.py"),
    Path("backend/adapters/api/runs/responses.py"),
    Path("backend/adapters/api/runs/resume_view.py"),
    Path("backend/adapters/api/runs/start_view.py"),
    Path("backend/adapters/api/runs/state_projection.py"),
    Path("backend/adapters/api/runs/views.py"),
    Path("backend/adapters/api/integrations/telegram_views.py"),
    Path("backend/adapters/api/integrations/whatsapp_views.py"),
    Path("backend/adapters/api/integrations/webhook_views.py"),
    Path("backend/application/services/audit_log.py"),
    Path("backend/application/services/career_ops_approvals.py"),
    Path("backend/application/services/career_ops_pipeline.py"),
    Path("backend/application/services/gateway_schedules.py"),
    Path("backend/application/services/os_projections.py"),
    Path("backend/application/services/operator_actions.py"),
    Path("backend/application/services/runtime_write_intents.py"),
    Path("backend/application/services/run_liveness.py"),
    Path("backend/application/services/run_state_machine.py"),
    Path("backend/application/services/task_lifecycle.py"),
    Path("backend/infrastructure/orm/management/commands/process_run_queue.py"),
}

ALLOWED_FIXTURE_WRITERS = {
    Path("backend/infrastructure/orm/management/commands/seed_frontend_control_plane_fixture.py"),
    Path("backend/infrastructure/orm/management/commands/seed_fiverr_portfolio_demo.py"),
    Path("backend/infrastructure/orm/management/commands/seed_legacy_phase6_mock_objective.py"),
    Path("backend/infrastructure/orm/management/commands/seed_run_trace.py"),
    Path("backend/infrastructure/orm/management/commands/seed_strategy_report_fixture.py"),
    Path("backend/infrastructure/orm/management/commands/seed_testsprite_frontend_fixture.py"),
    Path("backend/infrastructure/orm/management/commands/seed_whiteboard_hitl_fixture.py"),
    Path("backend/infrastructure/orm/management/commands/stream_run_trace.py"),
}

WRITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Run ORM write",
        re.compile(
            r"""\bRun\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "Run ORM update",
        re.compile(r"""\bRun\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "Run state mutation",
        re.compile(
            r"""\b(?:run|replay_run|paused_run|running_run|failed_run)\.status\s*(?<![=!<>])=(?![=])"""
        ),
    ),
    (
        "Run pause mutation",
        re.compile(
            r"""\b(?:run|replay_run|paused_run|running_run|failed_run)\.(?:paused_node_id|pause_state_json)\s*(?<![=!<>])=(?![=])""",
        ),
    ),
    (
        "Run save",
        re.compile(r"""\b(?:run|replay_run|paused_run|running_run|failed_run)\.save\("""),
    ),
    (
        "NodeRun ORM write",
        re.compile(
            r"""NodeRun\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "NodeRun ORM update",
        re.compile(r"""NodeRun\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "NodeRun state mutation",
        re.compile(
            r"""\b(?:node_run|waiting_node_run|skipped)\.status\s*(?<![=!<>])=(?![=])"""
        ),
    ),
    (
        "NodeRun save",
        re.compile(r"""\b(?:node_run|waiting_node_run|skipped)\.save\("""),
    ),
    (
        "ApprovalTask ORM write",
        re.compile(
            r"""ApprovalTask\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "ApprovalTask ORM update",
        re.compile(r"""ApprovalTask\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "ApprovalTask state mutation",
        re.compile(r"""\b(?:approval_task|task)\.status\s*(?<![=!<>])=(?![=])"""),
    ),
    (
        "TaskLifecycleRecord ORM write",
        re.compile(
            r"""TaskLifecycleRecord\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "TaskLifecycleRecord ORM update",
        re.compile(r"""TaskLifecycleRecord\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "TaskLifecycleRecord state mutation",
        re.compile(r"""\b(?:lifecycle_task|task)\.status\s*(?<![=!<>])=(?![=])"""),
    ),
    (
        "TaskLifecycleRecord save",
        re.compile(r"""\b(?:lifecycle_task|task)\.save\("""),
    ),
    (
        "TaskLifecycleEvent ORM write",
        re.compile(
            r"""TaskLifecycleEvent\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "TaskDeadLetterRecord ORM write",
        re.compile(
            r"""TaskDeadLetterRecord\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "TaskDeadLetterRecord ORM update",
        re.compile(r"""TaskDeadLetterRecord\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "RetryOperation ORM write",
        re.compile(
            r"""RetryOperation\.objects\.(?:create|get_or_create|update_or_create|bulk_create|bulk_update)""",
        ),
    ),
    (
        "RetryOperation ORM update",
        re.compile(r"""RetryOperation\.objects\.filter\([^)]*\)\.update\("""),
    ),
    (
        "RuntimeIntentOutcome acknowledgement mutation",
        re.compile(r"""\b(?:outcome|runtime_intent_outcome)\.acknowledged_at\s*(?<![=!<>])=(?![=])"""),
    ),
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line_number: int
    label: str
    line: str


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS or part.startswith(".venv") for part in path.parts)


def _is_allowed(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    return relative in ALLOWED_RUNTIME_WRITERS or relative in ALLOWED_FIXTURE_WRITERS


def _collect_violations(path: Path) -> list[Violation]:
    if _is_ignored(path) or _is_allowed(path):
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in WRITE_PATTERNS:
            if pattern.search(line):
                violations.append(
                    Violation(
                        path=path.relative_to(REPO_ROOT),
                        line_number=line_number,
                        label=label,
                        line=line.strip(),
                    )
                )
                break
    return violations


def main() -> int:
    if not RUNTIME_INVARIANTS.exists():
        print(
            "Missing canonical runtime contract: docs/architecture/runtime-invariants.md",
            file=sys.stderr,
        )
        return 1

    violations: list[Violation] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        violations.extend(_collect_violations(path))

    if not violations:
        return 0

    print("Unapproved backend runtime write paths detected.", file=sys.stderr)
    print(
        "Durable Run/NodeRun/ApprovalTask mutations must stay inside the approved backend write boundary.",
        file=sys.stderr,
    )
    print("Allowed runtime writers:", file=sys.stderr)
    for allowed in sorted(ALLOWED_RUNTIME_WRITERS):
        print(f"  - {allowed.as_posix()}", file=sys.stderr)
    print("Allowed fixture/ops writers:", file=sys.stderr)
    for allowed in sorted(ALLOWED_FIXTURE_WRITERS):
        print(f"  - {allowed.as_posix()}", file=sys.stderr)
    print("Violations:", file=sys.stderr)
    for violation in violations:
        print(
            f"  - {violation.path.as_posix()}:{violation.line_number} [{violation.label}] {violation.line}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
