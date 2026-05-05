#!/usr/bin/env python3
"""Block public launch claims that are ahead of checked-in evidence."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PUBLIC_CLAIM_PATHS = [
    "README.md",
    "frontend/pages",
    "frontend/components",
    "frontend/lib/seo.ts",
    "docs/product",
]

QUALIFIED_CAPACITY_PATTERN = re.compile(
    r"\b(?:roadmap|until measured|evidence|gate e|not (?:a )?claim|do not market|blocked)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimRule:
    name: str
    pattern: re.Pattern[str]
    requires_gate_e: bool = False
    allows_evidence_link: bool = False


CLAIM_RULES = [
    ClaimRule(
        name="500+ concurrent agents",
        pattern=re.compile(
            r"\b(?:500\+?|five hundred)\s*(?:\+?\s*)?(?:concurrent\s+)?agents\b|"
            r"\b500-agent\b",
            re.IGNORECASE,
        ),
        requires_gate_e=True,
    ),
    ClaimRule(
        name="production-grade company OS",
        pattern=re.compile(r"\bproduction-grade\s+company\s+OS\b", re.IGNORECASE),
        allows_evidence_link=True,
    ),
    ClaimRule(
        name="run entire companies at scale",
        pattern=re.compile(r"\brun\s+entire\s+companies\s+at\s+scale\b", re.IGNORECASE),
        allows_evidence_link=True,
    ),
    ClaimRule(
        name="complete accounting visibility",
        pattern=re.compile(r"\bcomplete\s+accounting\s+visibility\b", re.IGNORECASE),
        allows_evidence_link=True,
    ),
]

EVIDENCE_LINK_PATTERN = re.compile(
    r"\b(?:evidence|gate|production-evidence-gate|capacity)\b.*(?:https?://|\]\(|docs/)",
    re.IGNORECASE,
)


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    if argv:
        print("check_launch_claims.py does not accept arguments.", file=sys.stderr)
        return 2

    repo_root = root or Path(__file__).resolve().parents[2]
    findings = list(find_forbidden_claims(repo_root))
    if not findings:
        return 0

    for path, line_no, rule_name, line in findings:
        print(f"{path}:{line_no}: unsupported launch claim ({rule_name}): {line}", file=sys.stderr)
    print(
        "Launch claims must match checked-in evidence and docs/launch/claims-policy.md.",
        file=sys.stderr,
    )
    return 1


def find_forbidden_claims(root: Path) -> Iterable[tuple[str, int, str, str]]:
    gate_e_count = passed_gate_e_count(root)
    for path in iter_public_claim_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            for rule in CLAIM_RULES:
                if not rule.pattern.search(line):
                    continue
                if rule.requires_gate_e and gate_e_count >= 3:
                    continue
                if rule.requires_gate_e and QUALIFIED_CAPACITY_PATTERN.search(line):
                    continue
                if rule.allows_evidence_link and EVIDENCE_LINK_PATTERN.search(line):
                    continue
                yield str(path.relative_to(root)), index, rule.name, line.strip()


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
    """Return the number of latest consecutive passing checked-in Gate E reports.

    Public 500-agent claims require the latest Gate E evidence set to contain
    three consecutive passing reports under docs/ops/capacity. Older legacy
    stress logs remain useful regression evidence but do not unlock launch copy.
    """

    reports = sorted(_iter_gate_e_reports(root), key=lambda report: report.sort_key, reverse=True)
    count = 0
    for report in reports:
        if report.passed:
            count += 1
            continue
        break
    return count


@dataclass(frozen=True)
class GateEReport:
    path: Path
    passed: bool
    sort_key: datetime


def _iter_gate_e_reports(root: Path) -> Iterable[GateEReport]:
    for path in (root / "docs" / "ops" / "capacity").glob("gate-e-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("gate") or "").upper() != "E":
            continue
        yield GateEReport(
            path=path,
            passed=payload.get("passed") is True,
            sort_key=_report_sort_key(path, payload),
        )


def _report_sort_key(path: Path, payload: dict[str, object]) -> datetime:
    for field in ("completed_at", "started_at", "created_at"):
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return datetime.fromtimestamp(0, timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
