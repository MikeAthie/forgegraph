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
        failures.extend(validate_terminal_run_evidence(repo_root, latest.path))
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
        elif not (artifact_root / "metrics-summary.json").is_file():
            failures.append(
                f"Gate {gate} raw artifact metrics summary is missing: "
                f"{latest.artifacts_root / 'metrics-summary.json'}"
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


def validate_terminal_run_evidence(repo_root: Path, report_path: Path) -> list[str]:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not read capacity report {report_path}: {exc}"]

    target = payload.get("target")
    metrics = payload.get("metrics")
    if not isinstance(target, dict) or not isinstance(metrics, dict):
        return [
            f"Gate report is missing target/metrics payload: "
            f"{report_path.relative_to(repo_root)}"
        ]

    tenants = int_value(target.get("tenants"))
    runs_per_tenant = int_value(target.get("runs_per_tenant"))
    expected_runs = tenants * runs_per_tenant
    runs_started = int_value(metrics.get("runs_started"))
    runs_completed = int_value(metrics.get("runs_completed"))
    runs_failed = int_value(metrics.get("runs_failed"))
    silent_drops = int_value(metrics.get("silent_drops"))

    failures: list[str] = []
    rel_path = report_path.relative_to(repo_root)
    if expected_runs <= 0:
        failures.append(f"Gate report has invalid expected run count: {rel_path}")
    if runs_started < expected_runs:
        failures.append(
            f"Gate report did not start all planned runs: {rel_path} "
            f"started={runs_started} expected={expected_runs}"
        )
    if runs_completed != runs_started:
        failures.append(
            f"Gate report did not complete all started runs: {rel_path} "
            f"completed={runs_completed} started={runs_started} failed={runs_failed}"
        )
    if runs_failed != 0:
        failures.append(
            f"Gate report has terminal run failures: {rel_path} failed={runs_failed}"
        )
    if silent_drops != 0:
        failures.append(
            f"Gate report has silent drops: {rel_path} silent_drops={silent_drops}"
        )
    artifacts = payload.get("artifacts")
    runs_jsonl = None
    if isinstance(artifacts, dict) and isinstance(artifacts.get("runs_jsonl"), str):
        runs_jsonl = resolve_report_path(repo_root, Path(artifacts["runs_jsonl"]))
    if runs_jsonl is None:
        failures.append(f"Gate report has no runs_jsonl artifact path: {rel_path}")
    elif not runs_jsonl.is_file():
        failures.append(
            f"Gate report runs_jsonl artifact is missing: "
            f"{runs_jsonl.relative_to(repo_root)}"
        )
    else:
        succeeded, failed_statuses = count_run_statuses(runs_jsonl)
        if succeeded < runs_completed:
            failures.append(
                f"Gate report runs_jsonl does not contain completed evidence: "
                f"{runs_jsonl.relative_to(repo_root)} succeeded={succeeded} "
                f"runs_completed={runs_completed}"
            )
        if failed_statuses != runs_failed:
            failures.append(
                f"Gate report runs_jsonl failure count disagrees with metrics: "
                f"{runs_jsonl.relative_to(repo_root)} statuses={failed_statuses} "
                f"runs_failed={runs_failed}"
            )
    return failures


def count_run_statuses(path: Path) -> tuple[int, int]:
    succeeded = 0
    failed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return succeeded, failed
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(record.get("status") or "")
        if status == "succeeded":
            succeeded += 1
        elif status in {"failed", "canceled", "cancelled"}:
            failed += 1
    return succeeded, failed


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


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
