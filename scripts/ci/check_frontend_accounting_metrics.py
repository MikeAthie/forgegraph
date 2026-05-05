#!/usr/bin/env python3
"""Guard against frontend-invented accounting metrics."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SEARCH_PATHS = [
    "frontend/pages",
    "frontend/components",
    "frontend/domain/repositories",
    "frontend/lib",
]
SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}


@dataclass(frozen=True)
class ForbiddenPattern:
    name: str
    pattern: re.Pattern[str]


FORBIDDEN_PATTERNS = [
    ForbiddenPattern(
        "legacy synthetic financial variable",
        re.compile(r"\b(?:revenueMultiplier|profitToday|revenueToday)\b"),
    ),
    ForbiddenPattern(
        "local revenue/profit multiplier",
        re.compile(r"\b(?:revenue|profit|weekly|monthly)[A-Za-z0-9_]*Multiplier\b"),
    ),
    ForbiddenPattern(
        "mocked financial claim text",
        re.compile(
            r"Mock value for company-OS scenarios|modeled revenue|projected profit|"
            r"Projected revenue|Projected profit",
            re.IGNORECASE,
        ),
    ),
    ForbiddenPattern(
        "local revenue/profit formatter",
        re.compile(r"formatCurrency\([^)]*\b(?:revenue|profit)\b", re.IGNORECASE),
    ),
]


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    if argv:
        print("check_frontend_accounting_metrics.py does not accept arguments.", file=sys.stderr)
        return 2

    repo_root = root or Path(__file__).resolve().parents[2]
    findings = list(find_forbidden_patterns(repo_root))
    if not findings:
        return 0

    for path, line_no, name, line in findings:
        print(f"{path}:{line_no}: forbidden frontend accounting metric ({name}): {line}", file=sys.stderr)
    print(
        "Frontend financial metrics must come from backend accounting DTO status/source/computed_at.",
        file=sys.stderr,
    )
    return 1


def find_forbidden_patterns(root: Path) -> Iterable[tuple[str, int, str, str]]:
    for path in iter_source_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            for forbidden in FORBIDDEN_PATTERNS:
                if forbidden.pattern.search(line):
                    yield str(path.relative_to(root)), index, forbidden.name, line.strip()


def iter_source_files(root: Path) -> Iterable[Path]:
    for raw_path in SEARCH_PATHS:
        path = root / raw_path
        if path.is_file() and path.suffix in SOURCE_EXTENSIONS:
            yield path
        elif path.is_dir():
            yield from (
                item
                for item in path.rglob("*")
                if item.is_file()
                and item.suffix in SOURCE_EXTENSIONS
                and "node_modules" not in item.parts
            )


if __name__ == "__main__":
    raise SystemExit(main())
