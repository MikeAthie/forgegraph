from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from application.services.company_ops import company_ops_overview_payload
from application.services.inventory import inventory_overview_payload
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import Graph, User


class Command(BaseCommand):
    help = "Run the repo-owned Legacy Glasswear bootstrap and emit machine-readable evidence."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default="")
        parser.add_argument(
            "--database",
            default="default",
            choices=["default", "postgres", "sqlite"],
            help="Expected database profile. This command does not switch connections.",
        )
        parser.add_argument("--json", action="store_true", dest="output_json")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument(
            "--with-objective",
            default="none",
            choices=["none", "strategy_baseline", "visual_asset_brief"],
        )
        parser.add_argument("--with-task-judge", action="store_true")
        parser.add_argument("--evidence-json-path", default="")

    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        password = str(options["password"] or "").strip()
        strict = bool(options["strict"])
        requested_database = str(options["database"] or "default")

        bootstrap_command = (
            "uv run python manage.py legacy_glasswear_first_run "
            f"--database {requested_database} --json"
            f"{' --strict' if strict else ''}"
        )
        failures: list[str] = []
        warnings: list[str] = []

        database_engine = str(settings.DATABASES["default"].get("ENGINE") or "")
        if requested_database == "postgres" and "postgres" not in database_engine:
            failures.append(f"Requested postgres but default database engine is {database_engine}.")
        if requested_database == "sqlite" and "sqlite" not in database_engine:
            failures.append(f"Requested sqlite but default database engine is {database_engine}.")

        phase0 = _call_json_command(
            "seed_legacy_glasswear_phase0",
            email=email,
            password=password,
            output_json=True,
        )
        inventory_import = _call_json_command(
            "import_legacy_inventory_phase2",
            email=email,
            output_json=True,
        )

        warnings.extend(str(item) for item in phase0.get("warnings") or [])
        warnings.extend(str(item) for item in inventory_import.get("warnings") or [])

        company = _legacy_company(email)
        if company is None:
            raise CommandError("Legacy company was not found after bootstrap.")

        inventory = inventory_overview_payload(company)
        company_ops = company_ops_overview_payload(company)
        inventory_stock_summary = inventory.get("stock_state_summary") or {}
        company_ops_stock_summary = company_ops.get("stock_state_summary") or {}

        observed_data = {
            "user_id": phase0.get("user_id"),
            "organization_id": phase0.get("organization_id"),
            "company_id": phase0.get("company_id"),
            "storefront_slug": phase0.get("storefront_slug"),
            "graph_version_id": phase0.get("graph_version_id"),
            "products_imported": inventory_import.get("products_seen"),
            "active_units_imported": inventory_import.get("total_active_units"),
            "inventory_products_visible": len(inventory.get("products") or []),
            "inventory_total_units": inventory.get("summary", {}).get("total_units"),
            "inventory_available_units": inventory.get("summary", {}).get("available_units"),
            "stock_state_summary": inventory_stock_summary,
            "company_ops_stock_state_summary": company_ops_stock_summary,
        }

        checks = {
            "phase0_single_company": phase0.get("membership_count") == 1
            and phase0.get("company_count") == 1,
            "inventory_products_21": inventory_import.get("products_seen") == 21
            and len(inventory.get("products") or []) == 21,
            "inventory_active_units_62": inventory_import.get("total_active_units") == 62
            and inventory.get("summary", {}).get("total_units") == 62,
            "inventory_zero_warnings": len(inventory_import.get("warnings") or []) == 0,
            "stock_semantics_agree": inventory_stock_summary == company_ops_stock_summary,
        }
        for name, passed in checks.items():
            if not passed:
                failures.append(name)

        payload = {
            "schema": "legacy_glasswear_first_run.v1",
            "generated_at": timezone.now().isoformat(),
            "commands": [bootstrap_command],
            "inputs": {
                "email": email,
                "database": requested_database,
                "strict": strict,
                "with_objective": options["with_objective"],
                "with_task_judge": bool(options["with_task_judge"]),
            },
            "observed_data": observed_data,
            "verification_result": {
                "passed": not failures,
                "checks": checks,
                "warnings": warnings,
                "failures": failures,
            },
            "phase0": phase0,
            "inventory_import": inventory_import,
            "stock_semantics_report": {
                "active_count": inventory_stock_summary.get("active_count"),
                "low_stock_count": inventory_stock_summary.get("low_stock_count"),
                "last_piece_count": inventory_stock_summary.get("last_piece_count"),
                "sold_out_count": inventory_stock_summary.get("sold_out_count"),
                "definition_used": inventory_stock_summary.get("definition_used"),
            },
            "bugs_or_gaps": [],
            "decision": "bootstrap_passed" if not failures else "bootstrap_failed",
        }

        evidence_path = str(options["evidence_json_path"] or "").strip()
        if evidence_path:
            path = Path(evidence_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        if options["output_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Legacy Glasswear first run passed."
                    if not failures
                    else f"Legacy Glasswear first run failed: {', '.join(failures)}"
                )
            )

        if strict and failures:
            raise CommandError(f"Strict Legacy first run failed: {', '.join(failures)}")


def _call_json_command(name: str, **options: Any) -> dict[str, Any]:
    out = StringIO()
    try:
        call_command(name, stdout=out, **options)
    except CommandError:
        raise
    except Exception as exc:  # pragma: no cover - preserves management-command context
        raise CommandError(f"{name} failed: {exc}") from exc
    raw = out.getvalue().strip()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise CommandError(f"{name} emitted non-object JSON: {raw[:500]}")
        return payload
    except json.JSONDecodeError as exc:
        raise CommandError(f"{name} did not emit JSON: {raw[:500]}") from exc


def _legacy_company(email: str) -> Graph | None:
    user = User.objects.filter(email=email).first()
    if user is None:
        return None
    return cast(
        Graph | None,
        Graph.objects.filter(
            owner=user,
            organization=user.default_organization,
            external_source=EXTERNAL_SOURCE,
            external_ref=EXTERNAL_REF,
        )
        .select_related("organization")
        .first(),
    )
