#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
READ_VIEW_FILES = [
    BACKEND_ROOT / "adapters/api/system_state/views.py",
    BACKEND_ROOT / "adapters/api/agents/views.py",
    BACKEND_ROOT / "adapters/api/tasks/views.py",
    BACKEND_ROOT / "adapters/api/decisions/views.py",
    BACKEND_ROOT / "adapters/api/accounting/views.py",
]
LEGACY_CALLS = (
    "refresh_phase1_projections",
    "sync_agent_registry_for_organization",
    "sync_task_records_for_organization",
    "sync_decision_records_for_organization",
    "sync_accounting_for_organization",
)


def main() -> int:
    failures: list[str] = []
    for path in READ_VIEW_FILES:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for call in LEGACY_CALLS:
            if call in source:
                failures.append(f"{path.relative_to(REPO_ROOT)} calls legacy projection sweep: {call}")

    projections_dir = BACKEND_ROOT / "application/projections"
    for path in projections_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r"\[:\s*500\s*\]", source):
            failures.append(f"{path.relative_to(REPO_ROOT)} contains latest-500 truncation")
        if "time.sleep" in source:
            failures.append(f"{path.relative_to(REPO_ROOT)} sleeps inside projection logic")

    settings_source = (BACKEND_ROOT / "config/settings.py").read_text(encoding="utf-8")
    if 'ENABLE_LEGACY_OS_PROJECTION_SWEEP", False' not in settings_source:
        failures.append("ENABLE_LEGACY_OS_PROJECTION_SWEEP must default to False")

    if failures:
        print("Projection guardrails failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
