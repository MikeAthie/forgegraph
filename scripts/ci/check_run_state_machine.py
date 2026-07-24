#!/usr/bin/env python3
"""Fail if backend run status transitions bypass the run state-machine service."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
STATE_MACHINE = Path("backend/application/services/run_state_machine.py")
IGNORED_PARTS = {
    "__pycache__",
    "migrations",
    "tests",
    "testsprite_tests",
    ".hermes",
    ".uv-review-venv",
    ".venv",
}

DIRECT_STATUS_ASSIGNMENT = re.compile(
    r"""\b(?:run|locked_run|failed_run|refreshed_run|replay_run|paused_run|running_run)\.status\s*(?<![=!<>])=(?![=])"""
)
QUERYSET_STATUS_UPDATE = re.compile(r"""Run\.objects\.filter\([^)]*\)\.update\(\s*status=""")


def _ignored(path: Path) -> bool:
    if path.relative_to(REPO_ROOT) == STATE_MACHINE:
        return True
    return any(part in IGNORED_PARTS or part.startswith(".venv") for part in path.parts)


def main() -> int:
    failures: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if _ignored(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if DIRECT_STATUS_ASSIGNMENT.search(line) or QUERYSET_STATUS_UPDATE.search(line):
                failures.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line_number}: {line.strip()}")

    if failures:
        print(
            "Run status transitions must use application.services.run_state_machine.",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
