from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import (
    CompanyOperationObjective,
    Graph,
    GraphVersion,
    NodeRun,
    Run,
    TaskRecord,
    User,
)

REQUIRED_BRIEF_NAMES = {"GAGA", "HENDRIX", "WINEHOUSE", "WATSON", "MAVERICK"}


class Command(BaseCommand):
    help = "Seed a backend-owned Legacy Phase 6 objective run from prior provider evidence."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--company-id", default="")
        parser.add_argument(
            "--source-evidence-path",
            default="",
            help="Path to prior Legacy Phase 6 evidence JSON. Defaults to logs/legacy-phase6-2026-05-08.json.",
        )
        parser.add_argument("--json", action="store_true", dest="output_json")

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        source_path = _source_path(str(options["source_evidence_path"] or "").strip())
        source = _load_json(source_path)
        objective_output = _objective_output_from_source(source, source_path=source_path)

        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"Legacy user {email} was not found. Run Phase 0/bootstrap first.")
        ensure_default_organization(user)
        organization = user.default_organization
        if organization is None:
            raise CommandError(f"Legacy user {email} has no default organization.")

        company = _legacy_company(user=user, company_id=str(options["company_id"] or "").strip())
        if company is None:
            raise CommandError(
                "Legacy company was not found. Run legacy_glasswear_first_run first."
            )

        graph_json = _mock_operation_graph_json()
        operation_graph = Graph.objects.create(
            owner=user,
            organization=organization,
            name="Legacy Phase 6 Visual Asset Brief Objective",
            description="Mocked provider response operation seeded from prior Legacy evidence.",
        )
        graph_version = GraphVersion.objects.create(
            graph=operation_graph,
            version=1,
            graph_json=graph_json,
        )

        now = timezone.now()
        raw_response = json.dumps(objective_output, ensure_ascii=False)
        run = Run.objects.create(
            owner=user,
            organization=organization,
            graph_version=graph_version,
            status="succeeded",
            started_at=now,
            ended_at=now,
            input_json={
                "company_id": str(company.id),
                "mock_provider_response": True,
                "source_evidence_path": str(source_path),
            },
            dispatch_graph_json=graph_json,
            output_json={
                "visual_asset_brief": objective_output,
                "raw_visual_asset_brief": raw_response,
                "planner_trace": {
                    "response": objective_output,
                    "raw_response": raw_response,
                    "provider": "mock",
                    "mock_provider_response": True,
                },
            },
        )
        node_run = NodeRun.objects.create(
            run=run,
            node_id="visual_asset_brief",
            node_type="agent",
            status="succeeded",
            started_at=now,
            ended_at=now,
            input_json={"company_id": str(company.id), "mock_provider_response": True},
            output_json={
                "response": objective_output,
                "raw_response": raw_response,
                "provider": "mock",
                "mock_provider_response": True,
            },
        )
        task = TaskRecord.objects.create(
            organization=organization,
            execution=run,
            source_node_id=node_run.node_id,
            external_key=f"{run.id}:{node_run.node_id}",
            title="Legacy Phase 6 Visual Asset Brief task",
            status="completed",
            priority="normal",
            summary="Produced mocked Phase 6 visual asset briefs from prior backend evidence.",
            current_step=node_run,
            started_at=now,
            ended_at=now,
        )
        objective = CompanyOperationObjective.objects.create(
            organization=organization,
            company=company,
            operation=run,
            created_by=user,
            run_type="rehearsal",
            status="evaluated",
            run_goal="Produce Legacy Phase 6 visual asset briefs without spending provider credits.",
            hypothesis=(
                "Prior accepted provider output can verify downstream Legacy tasks, approvals, "
                "reservation proof, and judging when external provider credits are unavailable."
            ),
            target_signal="approval-gated visual/content preparation",
            action_plan_json=objective_output.get("next_run_plan") or [],
            integrity_gates_json={
                "mock_provider_response": True,
                "zero_cash_spend": True,
                "approval_gated": True,
                "live_media_generation": False,
                "public_posting": False,
                "procurement_execution": False,
            },
            success_score=100,
            miss_analysis="No provider call made; this run verifies downstream task wiring only.",
            next_decision="Use live provider mode only when Gemini/OpenRouter credits are available.",
            evaluated_at=now,
        )

        payload = {
            "schema": "legacy_phase6_mock_objective_seed.v1",
            "generated_at": now.isoformat(),
            "source_evidence_path": str(source_path),
            "company_id": str(company.id),
            "run_id": str(run.id),
            "graph_id": str(operation_graph.id),
            "graph_version_id": str(graph_version.id),
            "node_run_id": str(node_run.id),
            "task_id": str(task.id),
            "objective_contract_id": str(objective.id),
            "mock_provider_response": True,
            "visual_asset_brief_count": len(objective_output["visual_asset_briefs"]),
            "required_briefs_present": sorted(REQUIRED_BRIEF_NAMES),
        }

        if options["output_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded mock Legacy Phase 6 objective run {run.id} from {source_path}."
                )
            )


def _source_path(value: str) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return (Path(settings.BASE_DIR).parent / "logs" / "legacy-phase6-2026-05-08.json").resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CommandError(f"Legacy mock evidence file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"Legacy mock evidence file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CommandError(f"Legacy mock evidence file must contain a JSON object: {path}")
    return payload


def _objective_output_from_source(source: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    observed = source.get("observed_data")
    if not isinstance(observed, dict):
        observed = source
    stock_report = observed.get("stock_semantics_report")
    briefs = observed.get("visual_asset_briefs")
    next_run_plan = observed.get("next_run_plan")
    if not isinstance(stock_report, dict):
        raise CommandError(f"Legacy mock evidence is missing stock_semantics_report: {source_path}")
    if not isinstance(briefs, list):
        raise CommandError(f"Legacy mock evidence is missing visual_asset_briefs: {source_path}")
    if not isinstance(next_run_plan, list):
        raise CommandError(f"Legacy mock evidence is missing next_run_plan: {source_path}")

    normalized_briefs = [brief for brief in briefs if isinstance(brief, dict)]
    present = {
        str(brief.get("product_name") or brief.get("name") or "").strip().upper()
        for brief in normalized_briefs
    }
    missing = sorted(REQUIRED_BRIEF_NAMES - present)
    if missing:
        raise CommandError(
            f"Legacy mock evidence is missing required visual briefs: {', '.join(missing)}"
        )

    return {
        "stock_semantics_report": stock_report,
        "visual_asset_briefs": normalized_briefs,
        "next_run_plan": [str(item) for item in next_run_plan if str(item).strip()],
        "mock_provider_response": True,
        "source_evidence": source.get("schema") or "legacy_phase6_evidence.v1",
    }


def _legacy_company(*, user: User, company_id: str) -> Graph | None:
    if company_id:
        return cast(
            Graph | None,
            Graph.objects.filter(
                id=company_id,
                owner=user,
                organization=user.default_organization,
            ).first(),
        )
    return cast(
        Graph | None,
        Graph.objects.filter(
            owner=user,
            organization=user.default_organization,
            external_source=EXTERNAL_SOURCE,
            external_ref=EXTERNAL_REF,
        ).first(),
    )


def _mock_operation_graph_json() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "visual_asset_brief",
                "type": "agent",
                "name": "Visual Asset Brief",
                "config": {
                    "provider": "mock",
                    "model": "legacy-phase6-fixture",
                    "mock_provider_response": True,
                },
            },
            {
                "id": "final_output",
                "type": "output",
                "name": "Final Deliverable",
                "config": {
                    "output_mapping": {
                        "visual_asset_brief": "node.visual_asset_brief.output.response"
                    }
                },
            },
        ],
        "edges": [
            {"id": "start-visual-brief", "from": "START", "to": "visual_asset_brief"},
            {"id": "visual-brief-output", "from": "visual_asset_brief", "to": "final_output"},
            {"id": "final-end", "from": "final_output", "to": "END"},
        ],
        "metadata": {
            "name": "Legacy Phase 6 Visual Asset Brief Objective",
            "description": "Mocked provider response operation for out-of-credit Legacy testing.",
            "legacy_phase": "phase-6",
            "mock_provider_response": True,
            "runtime_contract": {
                "durable_source_of_truth": "backend",
                "engine_owns_durable_state": False,
            },
        },
    }
