#!/usr/bin/env python3
"""Validate checked-in beta capacity evidence produced by tools/loadgen."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_GATES = ("A", "B")


@dataclass(frozen=True)
class CapacityReport:
    path: Path
    gate: str
    passed: bool
    sort_key: datetime
    artifacts_root: Path | None


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate beta Gate A/B capacity reports and raw artifacts.",
    )
    parser.add_argument(
        "--gates",
        nargs="+",
        default=list(DEFAULT_GATES),
        help="Capacity gates to require. Defaults to A B.",
    )
    parser.add_argument(
        "--capacity-report-dir",
        default="docs/ops/capacity",
        help="Directory that must contain checked-in gate reports.",
    )
    parser.add_argument(
        "--raw-artifact-dir",
        default="logs/loadgen",
        help="Directory that must contain loadgen raw artifacts.",
    )
    args = parser.parse_args(argv)

    repo_root = root or Path(__file__).resolve().parents[2]
    report_dir = (repo_root / args.capacity_report_dir).resolve()
    raw_dir = (repo_root / args.raw_artifact_dir).resolve()
    gates = [gate.upper() for gate in args.gates]

    failures: list[str] = []
    if not report_dir.is_dir():
        failures.append(
            f"missing capacity report directory: {report_dir.relative_to(repo_root)}"
        )
    if not raw_dir.is_dir():
        failures.append(
            f"missing raw loadgen artifact directory: {raw_dir.relative_to(repo_root)}"
        )

    reports = list(iter_reports(report_dir)) if report_dir.is_dir() else []
    for gate in gates:
        latest = latest_report_for_gate(reports, gate)
        if latest is None:
            failures.append(
                f"missing checked-in Gate {gate} report under {report_dir.relative_to(repo_root)}"
            )
            continue
        if not latest.passed:
            failures.append(
                f"latest Gate {gate} report is not passing: {latest.path.relative_to(repo_root)}"
            )
        if latest.path.parent.resolve() != report_dir:
            failures.append(
                f"Gate {gate} report is outside capacity report dir: {latest.path}"
            )
        if latest.artifacts_root is None:
            failures.append(
                f"Gate {gate} report has no artifacts.root: {latest.path.relative_to(repo_root)}"
            )
            continue
        artifact_root = resolve_report_path(repo_root, latest.artifacts_root)
        if not is_relative_to(artifact_root, raw_dir):
            failures.append(
                f"Gate {gate} raw artifact root is outside {raw_dir.relative_to(repo_root)}: "
                f"{latest.artifacts_root}"
            )
        elif not artifact_root.is_dir():
            failures.append(
                f"Gate {gate} raw artifact root is missing: {latest.artifacts_root}"
            )

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


def iter_reports(report_dir: Path) -> Iterable[CapacityReport]:
    for path in report_dir.glob("gate-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gate = str(payload.get("gate") or "").upper()
        if gate == "":
            continue
        artifacts = payload.get("artifacts")
        artifacts_root: Path | None = None
        if isinstance(artifacts, dict) and isinstance(artifacts.get("root"), str):
            artifacts_root = Path(artifacts["root"])
        yield CapacityReport(
            path=path.resolve(),
            gate=gate,
            passed=payload.get("passed") is True,
            sort_key=report_sort_key(path, payload),
            artifacts_root=artifacts_root,
        )


def latest_report_for_gate(
    reports: Iterable[CapacityReport], gate: str
) -> CapacityReport | None:
    matching = [report for report in reports if report.gate == gate]
    if not matching:
        return None
    return max(matching, key=lambda report: report.sort_key)


def report_sort_key(path: Path, payload: dict[str, object]) -> datetime:
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


def resolve_report_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
