#!/usr/bin/env python3
"""Block public 500-agent claims until Phase 3 Gate E has evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable


CLAIM_PATTERN = re.compile(
    r"\b(?:500\+?|five hundred)\s*(?:\+?\s*)?(?:concurrent\s+)?agents\b|\b500-agent\b",
    re.IGNORECASE,
)
QUALIFIED_PATTERN = re.compile(
    r"\b(?:roadmap|until measured|evidence|gate e|not (?:a )?claim|do not market|blocked)\b",
    re.IGNORECASE,
)
PUBLIC_CLAIM_PATHS = [
    "README.md",
    "frontend/pages",
    "frontend/components",
    "frontend/lib/seo.ts",
    "docs/product",
]


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    findings = list(find_unqualified_claims(root))
    if not findings:
        return 0
    gate_e_count = passed_gate_e_count(root)
    if gate_e_count >= 3:
        return 0
    for path, line_no, line in findings:
        print(f"{path}:{line_no}: unqualified 500-agent claim: {line}", file=sys.stderr)
    print(
        "500-agent public claims require three passing Phase 3 Gate E evidence reports.",
        file=sys.stderr,
    )
    return 1


def find_unqualified_claims(root: Path) -> Iterable[tuple[str, int, str]]:
    for path in iter_public_claim_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            if CLAIM_PATTERN.search(line) and not QUALIFIED_PATTERN.search(line):
                yield str(path.relative_to(root)), index, line.strip()


def iter_public_claim_files(root: Path) -> Iterable[Path]:
    for raw_path in PUBLIC_CLAIM_PATHS:
        path = root / raw_path
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from (
                item
                for item in path.rglob("*")
                if item.is_file()
                and item.suffix.lower() in {".md", ".mdx", ".ts", ".tsx", ".js", ".jsx"}
                and "node_modules" not in item.parts
            )


def passed_gate_e_count(root: Path) -> int:
    count = 0
    for path in (root / "logs" / "stress").glob("**/phase3-gate-E.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("gate") == "E" and payload.get("passed") is True:
            count += 1
    return count


if __name__ == "__main__":
    raise SystemExit(main())
