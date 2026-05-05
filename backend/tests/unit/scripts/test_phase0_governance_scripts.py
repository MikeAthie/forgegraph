from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script(name: str) -> ModuleType:
    module_path = Path(__file__).resolve().parents[4] / "scripts" / "ci" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_required_signoff_docs(root: Path, *, approved: bool = False) -> None:
    mark = "x" if approved else " "
    for relative in (
        "docs/architecture/state-ownership.md",
        "docs/architecture/event-contracts.md",
        "docs/architecture/frontend-state-contract.md",
        "docs/architecture/launch-claims.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "# Contract",
                    "",
                    "## Signoff",
                    "",
                    f"- [{mark}] Product Lead",
                    f"- [{mark}] Backend Lead",
                    f"- [{mark}] Engine Lead",
                    f"- [{mark}] Frontend Lead",
                    f"- [{mark}] Platform/SRE Lead",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def test_architecture_signoff_presence_passes_without_approvals(tmp_path: Path) -> None:
    module = _load_script("check_architecture_signoff.py")
    _write_required_signoff_docs(tmp_path, approved=False)

    failures = module.validate_signoff_blocks(tmp_path, require_approved=False)

    assert failures == []


def test_architecture_signoff_release_mode_blocks_pending_approvals(tmp_path: Path) -> None:
    module = _load_script("check_architecture_signoff.py")
    _write_required_signoff_docs(tmp_path, approved=False)

    failures = module.validate_signoff_blocks(tmp_path, require_approved=True)

    assert any("release signoff is pending for Product Lead" in failure for failure in failures)


def test_architecture_signoff_blocks_malformed_role(tmp_path: Path) -> None:
    module = _load_script("check_architecture_signoff.py")
    _write_required_signoff_docs(tmp_path, approved=True)
    malformed = tmp_path / "docs/architecture/state-ownership.md"
    malformed.write_text(
        malformed.read_text(encoding="utf-8").replace("- [x] Engine Lead", "- [x] Engine"),
        encoding="utf-8",
    )

    failures = module.validate_signoff_blocks(tmp_path, require_approved=False)

    assert any("missing signoff checkbox for Engine Lead" in failure for failure in failures)


def test_launch_claim_checker_blocks_forbidden_public_claim(tmp_path: Path) -> None:
    module = _load_script("check_launch_claims.py")
    readme = tmp_path / "README.md"
    readme.write_text("ForgeGraph delivers complete accounting visibility.\n", encoding="utf-8")

    findings = list(module.find_forbidden_claims(tmp_path))

    assert findings == [
        (
            "README.md",
            1,
            "complete accounting visibility",
            "ForgeGraph delivers complete accounting visibility.",
        )
    ]


def test_launch_claim_checker_allows_qualified_capacity_policy(tmp_path: Path) -> None:
    module = _load_script("check_launch_claims.py")
    readme = tmp_path / "README.md"
    readme.write_text(
        "500+ concurrent agents remain blocked until Gate E evidence passes.\n",
        encoding="utf-8",
    )

    findings = list(module.find_forbidden_claims(tmp_path))

    assert findings == []


def _write_gate_e_report(root: Path, name: str, *, passed: bool, completed_at: str) -> None:
    capacity_dir = root / "docs/ops/capacity"
    capacity_dir.mkdir(parents=True, exist_ok=True)
    (capacity_dir / name).write_text(
        (
            "{"
            f'"gate": "E", "passed": {"true" if passed else "false"}, '
            f'"completed_at": "{completed_at}"'
            "}"
        ),
        encoding="utf-8",
    )


def test_launch_claim_checker_requires_three_latest_gate_e_passes(tmp_path: Path) -> None:
    module = _load_script("check_launch_claims.py")
    readme = tmp_path / "README.md"
    readme.write_text("ForgeGraph supports 500 concurrent agents.\n", encoding="utf-8")
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-01.json",
        passed=True,
        completed_at="2026-05-01T00:00:00Z",
    )
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-02.json",
        passed=True,
        completed_at="2026-05-02T00:00:00Z",
    )
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-03.json",
        passed=True,
        completed_at="2026-05-03T00:00:00Z",
    )

    findings = list(module.find_forbidden_claims(tmp_path))

    assert findings == []


def test_launch_claim_checker_blocks_when_newer_gate_e_fails(tmp_path: Path) -> None:
    module = _load_script("check_launch_claims.py")
    readme = tmp_path / "README.md"
    readme.write_text("ForgeGraph supports 500 concurrent agents.\n", encoding="utf-8")
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-01.json",
        passed=True,
        completed_at="2026-05-01T00:00:00Z",
    )
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-02.json",
        passed=True,
        completed_at="2026-05-02T00:00:00Z",
    )
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-03.json",
        passed=True,
        completed_at="2026-05-03T00:00:00Z",
    )
    _write_gate_e_report(
        tmp_path,
        "gate-e-2026-05-04.json",
        passed=False,
        completed_at="2026-05-04T00:00:00Z",
    )

    findings = list(module.find_forbidden_claims(tmp_path))

    assert findings
    assert findings[0][2] == "500+ concurrent agents"
