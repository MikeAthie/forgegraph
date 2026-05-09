#!/usr/bin/env python3
"""Block test-company terminology from reusable commerce surfaces."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCANNED_PATHS = [
    "backend/application/services/commerce.py",
    "backend/application/services/inventory.py",
    "backend/application/services/gemini_media.py",
    "backend/adapters/api/commerce",
    "backend/adapters/api/storefront",
    "backend/adapters/api/archive",
    "frontend/components/company/CommerceInventoryPanel.tsx",
    "frontend/components/company/CompanyWorkspaceShell.tsx",
    "frontend/pages/storefront",
    "frontend/lib/api.ts",
]

FORBIDDEN = [
    "Legacy",
    "legacy-glasswear",
    "legacy_csv",
    "legacy-media",
]


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for relative in SCANNED_PATHS:
        path = REPO_ROOT / relative
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix in {".py", ".ts", ".tsx"}
            )
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in _iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN:
            if token in text:
                failures.append(f"{path.relative_to(REPO_ROOT)} contains forbidden token {token!r}")
    if failures:
        print(
            "Reusable commerce/media/storefront code must stay business-agnostic.", file=sys.stderr
        )
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
