#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "reliability" / "idempotency-matrix.md"
FRONTEND_PATHS = [
    ROOT / "frontend" / "domain" / "repositories" / "operationRepository.ts",
    ROOT / "frontend" / "components" / "graph-editor" / "GraphEditor.tsx",
]

REQUIRED_MATRIX_ROWS = [
    "Engine callback event",
    "Runtime intent",
    "Human decision submit",
    "Projection event",
    "Memory write",
    "Accounting write",
    "Frontend command retry",
]

REQUIRED_FRONTEND_PATTERNS = [
    "newClientCommandId",
    "idempotencyKey",
    "operation.resume",
    "graph.run",
]


def main() -> int:
    failures: list[str] = []
    if not MATRIX.exists():
        failures.append("docs/reliability/idempotency-matrix.md is missing")
    else:
        text = MATRIX.read_text(encoding="utf-8")
        for row in REQUIRED_MATRIX_ROWS:
            if row not in text:
                failures.append(f"idempotency matrix missing row: {row}")

    frontend_text = "\n".join(
        path.read_text(encoding="utf-8") for path in FRONTEND_PATHS if path.exists()
    )
    for pattern in REQUIRED_FRONTEND_PATTERNS:
        if pattern not in frontend_text:
            failures.append(f"frontend idempotency guard missing pattern: {pattern}")

    if failures:
        for failure in failures:
            print(failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
