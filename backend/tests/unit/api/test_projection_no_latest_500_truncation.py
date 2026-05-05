from __future__ import annotations

from pathlib import Path


def test_projection_handlers_do_not_use_latest_500_truncation() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    projection_root = backend_root / "application" / "projections"

    offenders: list[str] = []
    for path in projection_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "[:500]" in source or "[0:500]" in source:
            offenders.append(str(path.relative_to(backend_root)))

    assert offenders == []
