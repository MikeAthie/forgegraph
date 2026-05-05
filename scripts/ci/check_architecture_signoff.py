#!/usr/bin/env python3
"""Validate architecture signoff blocks.

Default mode is PR-safe: the required signoff block must exist and contain each
role. Release mode additionally requires every checkbox to be approved.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_DOCS = [
    "docs/architecture/state-ownership.md",
    "docs/architecture/event-contracts.md",
    "docs/architecture/frontend-state-contract.md",
    "docs/architecture/launch-claims.md",
]
REQUIRED_ROLES = [
    "Product Lead",
    "Backend Lead",
    "Engine Lead",
    "Frontend Lead",
    "Platform/SRE Lead",
]

SIGNOFF_HEADING = re.compile(r"^## Signoff\s*$", re.MULTILINE)
NEXT_HEADING = re.compile(r"^##\s+", re.MULTILINE)


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Require every required signoff checkbox to be checked.",
    )
    args = parser.parse_args(argv)

    repo_root = root or Path(__file__).resolve().parents[2]
    failures = validate_signoff_blocks(repo_root, require_approved=args.require_approved)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


def validate_signoff_blocks(root: Path, *, require_approved: bool) -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_DOCS:
        path = root / relative
        if not path.is_file():
            failures.append(f"{relative}: missing required architecture signoff document")
            continue

        source = path.read_text(encoding="utf-8")
        block = extract_signoff_block(source)
        if block is None:
            failures.append(f"{relative}: missing required '## Signoff' block")
            continue

        for role in REQUIRED_ROLES:
            role_pattern = re.compile(
                rf"^- \[(?P<mark>[ xX])\]\s+{re.escape(role)}\s*$",
                re.MULTILINE,
            )
            match = role_pattern.search(block)
            if match is None:
                failures.append(f"{relative}: missing signoff checkbox for {role}")
                continue
            if require_approved and match.group("mark").lower() != "x":
                failures.append(f"{relative}: release signoff is pending for {role}")
    return failures


def extract_signoff_block(source: str) -> str | None:
    heading = SIGNOFF_HEADING.search(source)
    if heading is None:
        return None

    next_heading = NEXT_HEADING.search(source, heading.end())
    end = next_heading.start() if next_heading else len(source)
    return source[heading.end() : end]


if __name__ == "__main__":
    raise SystemExit(main())
