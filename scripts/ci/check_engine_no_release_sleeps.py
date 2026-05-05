#!/usr/bin/env python3
"""Fail release-critical engine tests that use arbitrary time.Sleep calls."""

from __future__ import annotations

from pathlib import Path
import sys


def has_legacy_timing_tag(source: str) -> bool:
    header = "\n".join(source.splitlines()[:8])
    return any(
        line.startswith("//go:build") and "legacy_timing" in line
        for line in header.splitlines()
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    engine_root = repo_root / "engine"
    offenders: list[str] = []

    for path in engine_root.rglob("*_test.go"):
        source = path.read_text(encoding="utf-8")
        if "time.Sleep(" not in source:
            continue
        if has_legacy_timing_tag(source):
            continue
        offenders.append(str(path.relative_to(repo_root)).replace("\\", "/"))

    if offenders:
        print("Release-critical engine tests must not use arbitrary time.Sleep calls.", file=sys.stderr)
        print("Use deterministic waits/channels/select timeouts, or add the legacy_timing build tag.", file=sys.stderr)
        for offender in offenders:
            print(f" - {offender}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
