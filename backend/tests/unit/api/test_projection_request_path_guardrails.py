from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REQUEST_VIEW_FILES = [
    BACKEND_ROOT / "adapters/api/system_state/views.py",
    BACKEND_ROOT / "adapters/api/agents/views.py",
    BACKEND_ROOT / "adapters/api/tasks/views.py",
    BACKEND_ROOT / "adapters/api/decisions/views.py",
    BACKEND_ROOT / "adapters/api/accounting/views.py",
]
PROJECTION_HANDLER_ROOT = BACKEND_ROOT / "application/projections"


def test_os_read_views_do_not_refresh_projections_in_request_path() -> None:
    for path in REQUEST_VIEW_FILES:
        source = path.read_text(encoding="utf-8")
        assert "refresh_phase1_projections" not in source, (
            f"{path.relative_to(BACKEND_ROOT)} refreshes projections from a request path; "
            "GET views must read materialized backend-owned models only."
        )
        assert "projection_organization_for_user" in source, (
            f"{path.relative_to(BACKEND_ROOT)} should resolve organization without repair/sync side effects."
        )


def test_incremental_projection_handlers_do_not_use_latest_500_windows() -> None:
    for path in PROJECTION_HANDLER_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "[:500]" not in source, (
            f"{path.relative_to(BACKEND_ROOT)} uses a truncated latest-500 projection window."
        )
