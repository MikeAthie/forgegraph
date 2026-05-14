"""Report large backend Python files without enforcing a hard gate.

The report is advisory by default. Use --fail-over-target only after the
existing outliers have been brought under the configured targets.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "migrations",
}


@dataclass(frozen=True)
class FileTarget:
    label: str
    path_part: str
    max_lines: int


TARGETS = (
    FileTarget("run adapter", "adapters/api/runs", 1_000),
    FileTarget("model group", "infrastructure/orm/models", 1_200),
    FileTarget("run API test", "tests/integration/adapters/runs", 900),
)


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _target_for(path: Path) -> FileTarget | None:
    normalized = path.as_posix()
    for target in TARGETS:
        if target.path_part in normalized:
            return target
    return None


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Report large backend Python files.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument(
        "--fail-over-target",
        action="store_true",
        help="Exit 1 if a file exceeds an advisory target.",
    )
    args = parser.parse_args()

    rows: list[tuple[int, str, str, int | None]] = []
    over_target = False
    for path in _iter_python_files(args.root):
        count = _line_count(path)
        target = _target_for(path)
        max_lines = target.max_lines if target else None
        label = target.label if target else "unclassified"
        if max_lines is not None and count > max_lines:
            over_target = True
        rows.append((count, label, path.relative_to(args.root).as_posix(), max_lines))

    print("Largest backend Python files:")
    for count, label, rel_path, max_lines in sorted(rows, reverse=True)[: args.top]:
        target_text = f"target={max_lines}" if max_lines is not None else "target=none"
        marker = "OVER" if max_lines is not None and count > max_lines else "ok"
        print(f"{count:5d}  {marker:4s}  {target_text:11s}  {label:14s}  {rel_path}")

    if over_target and args.fail_over_target:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
