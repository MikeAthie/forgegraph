from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Max

from application.services.assertions import create_assertion
from application.services.company_blueprints import create_company_from_blueprint
from application.services.company_programs import create_program
from application.services.evaluations import run_evaluation
from application.services.operating_model_packs import install_pack_for_company
from application.services.periodic_reviews import (
    assemble_report_run,
    create_metric_snapshot,
    current_due_review_period,
    execute_periodic_review,
    periodic_review_payload,
    run_periodic_review,
    upsert_review_definition_from_template,
)
from application.services.program_stage_outputs import execute_stage_output_generation
from application.services.rework_plans import create_rework_plan, execute_rework_plan
from application.services.state_projections import (
    materialize_current_truth_projection,
    materialize_service_history_projection,
)
from application.services.tenancy import set_default_organization
from application.services.validation_decisions import create_validation_decision
from application.services.work_artifacts import create_work_artifact
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    CompanySignal,
    EvaluationRun,
    Graph,
    GraphVersion,
    MetricSnapshot,
    Organization,
    OrganizationMembership,
    PeriodicReviewDefinition,
    ProgramStageState,
    ReportRun,
    User,
    ValidationDecision,
)

DEFAULT_EMAIL = "atlas.marketing.demo@example.com"
DEFAULT_ORG_NAME = "ATLAS MARKETING"
DEFAULT_COMPANY_NAME = "ATLAS MARKETING"
DEFAULT_PASSWORD = "AtlasMarketing!12345"
DEFAULT_PACK_ID = "digital_marketing_pro.v1"
PASSWORD_ENV = "ATLAS_MARKETING_PASSWORD"
EXTERNAL_SOURCE = "atlas-marketing"
EXTERNAL_REF = "pack-backed-demo-company"
PROGRAM_EXTERNAL_KEY = "atlas-marketing:engagement:v1"
SEED_KEY = "atlas_marketing_seed.v1"

COMPANY_OBJECTIVE = (
    "Operate a digital marketing company that runs brand strategy, content, channel "
    "execution, CRM, analytics, QA, compliance, approvals, and continuous improvement "
    "through ForgeGraph company operations."
)

DEFAULT_SERVICES = [
    "Brand intake",
    "Stone vs Opinion mapping",
    "Campaign planning",
    "Content strategy",
    "Channel execution",
    "CRM lifecycle",
    "Analytics reporting",
    "QA and compliance",
]

DEFAULT_REGIONS = ["United States"]


class SeedAssertion(TypedDict):
    kind: str
    pack_label: str
    category: str
    statement: str
    source: str
    confidence: float
    validation_status: str


class Command(BaseCommand):
    help = "Seed the ATLAS MARKETING demo company using the Digital Marketing Pro operating model pack."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=os.environ.get(PASSWORD_ENV, DEFAULT_PASSWORD))
        parser.add_argument("--json", action="store_true", dest="output_json")
        parser.add_argument("--launch-first-operation", action="store_true", default=False)
        parser.add_argument("--parts-1-6", action="store_true", default=False)
        parser.add_argument("--parts-7-12", action="store_true", default=False)
        parser.add_argument("--full-demo", action="store_true", default=False)
        parser.add_argument("--with-signals", action="store_true", default=False)
        parser.add_argument("--with-channel-fanout", action="store_true", default=False)
        parser.add_argument("--with-execution-artifacts", action="store_true", default=False)
        parser.add_argument("--with-atlas-service-model", action="store_true", default=False)
        parser.add_argument("--with-monthly-report", action="store_true", default=False)
        parser.add_argument("--with-kpi-scorecard", action="store_true", default=False)
        parser.add_argument("--with-client-history", action="store_true", default=False)
        parser.add_argument("--with-periodic-reviews", action="store_true", default=False)
        parser.add_argument("--with-monthly-metrics", action="store_true", default=False)
        parser.add_argument("--with-trends", action="store_true", default=False)
        parser.add_argument("--with-periodic-scheduling", action="store_true", default=False)
        parser.add_argument("--with-missing-metrics", action="store_true", default=False)
        parser.add_argument("--with-overdue-review", action="store_true", default=False)

    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        password = str(options["password"] or DEFAULT_PASSWORD)
        launch_first_operation = bool(options["launch_first_operation"])
        full_demo = bool(options["full_demo"])
        include_parts_1_6 = bool(options["parts_1_6"] or full_demo)
        include_parts_7_12 = bool(options["parts_7_12"] or full_demo)
        include_signals = bool(options["with_signals"] or full_demo)
        include_channel_fanout = bool(options["with_channel_fanout"] or full_demo)
        include_execution_artifacts = bool(options["with_execution_artifacts"] or full_demo)
        include_atlas_service_model = bool(options["with_atlas_service_model"] or full_demo)
        include_monthly_report = bool(options["with_monthly_report"] or full_demo)
        include_kpi_scorecard = bool(options["with_kpi_scorecard"] or full_demo)
        include_client_history = bool(options["with_client_history"] or full_demo)
        include_periodic_reviews = bool(options["with_periodic_reviews"] or full_demo)
        include_monthly_metrics = bool(options["with_monthly_metrics"] or full_demo)
        include_trends = bool(options["with_trends"] or full_demo)
        include_periodic_scheduling = bool(options["with_periodic_scheduling"] or full_demo)
        include_missing_metrics = bool(options["with_missing_metrics"] or full_demo)
        include_overdue_review = bool(options["with_overdue_review"] or full_demo)

        user, organization = _ensure_demo_user_and_org(email=email, password=password)
        company, graph_version_id, first_operation_id, created_company = _ensure_company(
            user=user,
            launch_first_operation=launch_first_operation,
        )
        installation = _ensure_pack_installation(company=company, user=user)
        program = _ensure_engagement_program(company=company, user=user)
        assertions = _ensure_assertions(company=company, program=program, user=user)
        artifact = _ensure_artifact(company=company, program=program, user=user)
        validation_decision_ids: list[str] = []
        rework_plan_id = ""
        if include_parts_1_6:
            validation_decision_ids, rework_plan_id = _ensure_parts_1_6_state(
                company=company,
                program=program,
                artifact=artifact,
                user=user,
            )
        generated = []
        if include_parts_7_12:
            generated = _ensure_parts_7_12_state(
                company=company,
                program=program,
                user=user,
                include_signals=include_signals,
                include_channel_fanout=include_channel_fanout,
                include_execution_artifacts=include_execution_artifacts,
            )
        atlas_service_model: dict[str, Any] = {}
        if (
            include_atlas_service_model
            or include_monthly_report
            or include_kpi_scorecard
            or include_client_history
        ):
            atlas_service_model = _ensure_atlas_service_model_state(
                company=company,
                program=program,
                user=user,
                include_monthly_report=include_monthly_report,
                include_kpi_scorecard=include_kpi_scorecard,
                include_client_history=include_client_history,
            )
        periodic_loop: dict[str, Any] = {}
        if (
            include_periodic_reviews
            or include_monthly_metrics
            or include_trends
            or include_periodic_scheduling
            or include_missing_metrics
            or include_overdue_review
        ):
            periodic_loop = _ensure_periodic_loop_state(
                company=company,
                program=program,
                user=user,
                include_monthly_metrics=include_monthly_metrics,
                include_trends=include_trends,
                include_periodic_scheduling=include_periodic_scheduling,
                include_missing_metrics=include_missing_metrics,
                include_overdue_review=include_overdue_review,
            )
        projection = materialize_current_truth_projection(
            company=company,
            program=program,
            projection_type="currently_true_state",
            display_label="Living Instruction File",
        )

        payload = {
            "schema": "atlas_marketing_seed.v1",
            "user_id": str(user.id),
            "organization_id": str(organization.id),
            "company_id": str(company.id),
            "graph_version_id": graph_version_id,
            "first_operation_id": first_operation_id,
            "pack_id": installation.pack_id,
            "program_id": str(program.id),
            "assertion_count": len(assertions),
            "artifact_id": str(artifact.id),
            "state_projection_id": str(projection.id),
            "created_company": created_company,
            "validation_decision_ids": validation_decision_ids,
            "rework_plan_id": rework_plan_id,
            "generated_stage_outputs": generated,
            "atlas_service_model": atlas_service_model,
            "periodic_loop": periodic_loop,
            "stage_status": {
                item.stage_id: item.status
                for item in ProgramStageState.objects.filter(program=program).order_by("sequence")
            },
        }
        if options["output_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {DEFAULT_COMPANY_NAME} ({company.id}) with {DEFAULT_PACK_ID}."
            )
        )


def _ensure_demo_user_and_org(*, email: str, password: str) -> tuple[User, Organization]:
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email=email, password=password)
    elif password:
        user.set_password(password)
        user.save(update_fields=["password"])
    user.refresh_from_db()

    organization = Organization.objects.filter(name=DEFAULT_ORG_NAME).first()
    if organization is None and user.default_organization_id:
        organization = user.default_organization
        if organization is not None:
            organization.name = DEFAULT_ORG_NAME
            organization.save(update_fields=["name", "updated_at"])
    if organization is None:
        organization = Organization.objects.create(name=DEFAULT_ORG_NAME)

    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"role": "owner", "is_default": False},
    )
    if membership.role != "owner":
        membership.role = "owner"
        membership.save(update_fields=["role", "updated_at"])
    set_default_organization(user, organization.id)
    user.refresh_from_db()
    return user, organization


def _ensure_company(
    *,
    user: User,
    launch_first_operation: bool,
) -> tuple[Graph, str, str | None, bool]:
    existing = Graph.objects.filter(
        owner=user,
        external_source=EXTERNAL_SOURCE,
        external_ref=EXTERNAL_REF,
    ).first()
    if existing is not None:
        latest_version_id = _latest_graph_version_id(existing)
        return existing, latest_version_id, None, False

    result = create_company_from_blueprint(
        user=user,
        company_name=DEFAULT_COMPANY_NAME,
        objective=COMPANY_OBJECTIVE,
        blueprint_id=DEFAULT_PACK_ID,
        services=DEFAULT_SERVICES,
        regions=DEFAULT_REGIONS,
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
        launch_first_operation=launch_first_operation,
        operation_brief="Prepare the first ATLAS engagement intake and currently true state.",
    )
    company = Graph.objects.get(id=result.company_id)
    company.external_source = EXTERNAL_SOURCE
    company.external_ref = EXTERNAL_REF
    company.save(update_fields=["external_source", "external_ref", "updated_at"])
    return company, result.graph_version_id, result.first_operation_id, True


def _ensure_pack_installation(*, company: Graph, user: User) -> CompanyOperatingModelInstallation:
    installation = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        pack_id=DEFAULT_PACK_ID,
        status="active",
    ).first()
    if installation is not None:
        return installation
    return install_pack_for_company(
        company=company,
        user=user,
        pack_id=DEFAULT_PACK_ID,
        config={"selected_services": DEFAULT_SERVICES, "regions": DEFAULT_REGIONS},
    )


def _ensure_engagement_program(*, company: Graph, user: User) -> CompanyProgram:
    existing = CompanyProgram.objects.filter(
        company=company, external_key=PROGRAM_EXTERNAL_KEY
    ).first()
    if existing is not None:
        return existing
    program = create_program(
        company=company,
        user=user,
        template_id="dmp.engagement",
        pack_id=DEFAULT_PACK_ID,
        title="ATLAS Marketing Growth Engagement",
        objective="Run the 12-stage Digital Marketing Pro operating methodology for ATLAS.",
        metadata={"source_seed": SEED_KEY},
    )
    program.external_key = PROGRAM_EXTERNAL_KEY
    program.save(update_fields=["external_key", "updated_at"])
    return program


def _ensure_assertions(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
) -> list[AssertionRecord]:
    seed_assertions: list[SeedAssertion] = [
        {
            "kind": "FACT",
            "pack_label": "Stone",
            "category": "company_model",
            "statement": "ATLAS MARKETING operates as a pack-backed digital marketing company inside ForgeGraph.",
            "source": "ATLAS demo seed",
            "confidence": 0.95,
            "validation_status": "validated",
        },
        {
            "kind": "FACT",
            "pack_label": "Stone",
            "category": "governance",
            "statement": "External publishing, sending, ads launch, CRM sync, and report export actions require policy evaluation before execution.",
            "source": "digital_marketing_pro.v1 policy pack",
            "confidence": 0.95,
            "validation_status": "validated",
        },
        {
            "kind": "OPINION",
            "pack_label": "Opinion",
            "category": "positioning",
            "statement": "ATLAS should position itself around governed marketing operations rather than one-off campaign deliverables.",
            "source": "ATLAS demo hypothesis",
            "confidence": 0.55,
            "validation_status": "unvalidated",
        },
        {
            "kind": "ASSUMPTION",
            "pack_label": "Assumption",
            "category": "execution",
            "statement": "Initial customers will value dry-run execution plans before live connector credentials are configured.",
            "source": "ATLAS demo hypothesis",
            "confidence": 0.5,
            "validation_status": "unvalidated",
        },
        {
            "kind": "QUESTION",
            "pack_label": "Question",
            "category": "research",
            "statement": "Which channel should ATLAS validate first for its first client acquisition loop?",
            "source": "ATLAS demo intake",
            "confidence": 0.5,
            "validation_status": "open",
        },
    ]
    assertions: list[AssertionRecord] = []
    for item in seed_assertions:
        existing = AssertionRecord.objects.filter(
            company=company,
            program=program,
            statement=item["statement"],
            metadata_json__source_seed=SEED_KEY,
        ).first()
        if existing is not None:
            assertions.append(existing)
            continue
        assertions.append(
            create_assertion(
                company=company,
                program=program,
                user=user,
                kind=item["kind"],
                pack_label=item["pack_label"],
                category=item["category"],
                statement=item["statement"],
                source=item["source"],
                confidence=float(item["confidence"]),
                validation_status=item["validation_status"],
                metadata={"source_seed": SEED_KEY},
            )
        )
    return assertions


def _ensure_artifact(*, company: Graph, program: CompanyProgram, user: User) -> Asset:
    existing = Asset.objects.filter(
        company=company,
        title="ATLAS Engagement Intake Summary",
        metadata_json__source_seed=SEED_KEY,
    ).first()
    if existing is not None:
        return existing
    artifact, _ = create_work_artifact(
        company=company,
        program=program,
        user=user,
        title="ATLAS Engagement Intake Summary",
        artifact_type="intake_summary",
        content={
            "summary": "ATLAS MARKETING is seeded as a demo company for the Digital Marketing Pro operating model pack.",
            "current_stage": "Client Inputs",
            "governance": "Side-effecting channel execution remains dry-run and policy-gated.",
            "next_actions": [
                "Validate initial Stone and Opinion records.",
                "Create the first research brief artifact.",
                "Run a QA profile before any external action request.",
            ],
        },
        metadata={"source_seed": SEED_KEY},
    )
    return artifact


def _ensure_parts_1_6_state(
    *,
    company: Graph,
    program: CompanyProgram,
    artifact: Asset,
    user: User,
) -> tuple[list[str], str]:
    existing_decision = ValidationDecision.objects.filter(
        company=company,
        program=program,
        asset=artifact,
        decision="EDIT",
        category="positioning",
        rationale="ATLAS demo validation change for pack-backed rework.",
    ).first()
    if existing_decision is None:
        existing_decision = create_validation_decision(
            company=company,
            program=program,
            user=user,
            asset_id=artifact.id,
            asset_version_id=artifact.versions.order_by("-version_number")
            .values_list("id", flat=True)
            .first(),
            decision="EDIT",
            category="positioning",
            rationale="ATLAS demo validation change for pack-backed rework.",
            proposed_change={
                "content": {
                    "summary": "Client-validated ATLAS positioning with an updated current operating view.",
                    "source_seed": SEED_KEY,
                },
                "label": "v2",
                "stage_id": "stage_06_selective_v2_reruns",
            },
        )
    existing_plan = (
        program.rework_plans.filter(
            trigger_summary="ATLAS demo rework plan for validated feedback."
        )
        .order_by("-created_at")
        .first()
    )
    if existing_plan is None:
        existing_plan = create_rework_plan(
            company=company,
            program=program,
            user=user,
            validation_decision_ids=[existing_decision.id],
            notes="ATLAS demo rework plan for validated feedback.",
        )
        execute_rework_plan(plan=existing_plan, user=user)
    elif existing_plan.status != "executed":
        execute_rework_plan(plan=existing_plan, user=user)
    return [str(existing_decision.id)], str(existing_plan.id)


def _ensure_parts_7_12_state(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
    include_signals: bool,
    include_channel_fanout: bool,
    include_execution_artifacts: bool,
) -> list[dict[str, Any]]:
    del company
    generated: list[dict[str, Any]] = []
    stage_plan: list[tuple[str, dict[str, Any]]] = [
        ("stage_07_preparation", {}),
        ("stage_08_growth_plan", {}),
    ]
    if include_channel_fanout:
        stage_plan.append(
            (
                "stage_09_channel_strategy",
                {
                    "selected_family_ids": [
                        "search_campaign",
                        "paid_platforms",
                        "content_pr",
                        "measurement",
                    ]
                },
            )
        )
    if include_execution_artifacts:
        stage_plan.extend(
            [
                ("stage_10_execution_artifacts", {}),
                ("stage_11_ai_creative_instructions", {}),
            ]
        )
    if include_signals:
        stage_plan.append(("stage_12_continuous_improvement", {}))

    for stage_id, kwargs in stage_plan:
        if _stage_output_exists(program=program, stage_id=stage_id):
            generated.append({"stage_id": stage_id, "status": "already_present"})
            continue
        result = execute_stage_output_generation(
            program=program,
            user=user,
            stage_id=stage_id,
            workflow_id=f"{stage_id}.seed",
            notes="ATLAS full-demo seed output.",
            **kwargs,
        )
        generated.append(
            {
                "stage_id": stage_id,
                "status": result["status"],
                "artifact_ids": [item["id"] for item in result["created_artifacts"]],
                "signal_ids": [item["id"] for item in result["created_signals"]],
                "blockers": result["blockers"],
            }
        )
    return generated


def _stage_output_exists(*, program: CompanyProgram, stage_id: str) -> bool:
    source_prefix = f"program-stage-output:{program.id}:{stage_id}:"
    if Asset.objects.filter(company=program.company, source_key__startswith=source_prefix).exists():
        return True
    if stage_id != "stage_12_continuous_improvement":
        return False
    return CompanySignal.objects.filter(
        company=program.company,
        source="program_stage_output",
        external_key__startswith=f"program-stage-signal:{program.id}:{stage_id}:",
    ).exists()


def _ensure_atlas_service_model_state(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
    include_monthly_report: bool,
    include_kpi_scorecard: bool,
    include_client_history: bool,
) -> dict[str, Any]:
    service_artifacts = [
        _ensure_seed_service_artifact(
            company=company,
            program=program,
            user=user,
            artifact_type="brand_audit",
            title="ATLAS Auditoría de marca actual",
            content={
                "service_area": "Diagnóstico de marca y estrategia",
                "summary": "Auditoría inicial de marca, comunicación, canales y riesgos.",
                "findings": [
                    "La marca necesita un sistema de comunicación medible.",
                    "Las acciones externas siguen gobernadas por política y aprobación.",
                ],
            },
        ),
        _ensure_seed_service_artifact(
            company=company,
            program=program,
            user=user,
            artifact_type="buyer_persona",
            title="ATLAS Buyer Persona",
            content={
                "service_area": "Diagnóstico de marca y estrategia",
                "summary": "Persona demo para compradores que necesitan operaciones de marketing gobernadas.",
                "needs": ["Claridad estratégica", "Ejecución medible", "Historial de servicio"],
            },
        ),
        _ensure_seed_service_artifact(
            company=company,
            program=program,
            user=user,
            artifact_type="communication_strategy",
            title="ATLAS Estrategia de comunicación",
            content={
                "service_area": "Estrategia de comunicación",
                "summary": "Estrategia demo con mensajes clave, pilares, confianza social y canales.",
                "pillars": ["Gobernanza", "Performance", "Aprendizaje continuo"],
            },
        ),
        _ensure_seed_service_artifact(
            company=company,
            program=program,
            user=user,
            artifact_type="communication_calendar",
            title="ATLAS Calendario de comunicaciones",
            content={
                "service_area": "Calendario de comunicaciones",
                "entries": [
                    {
                        "channel": "LinkedIn",
                        "format": "Post",
                        "theme": "Marketing operations",
                        "cta": "Solicitar diagnóstico",
                    }
                ],
            },
        ),
    ]
    if include_monthly_report:
        service_artifacts.extend(
            [
                _ensure_seed_service_artifact(
                    company=company,
                    program=program,
                    user=user,
                    artifact_type="monthly_report",
                    title="ATLAS Reporte mensual demo",
                    content={
                        "service_area": "Reportes y optimización mensual",
                        "learnings": ["La interacción social requiere revisión de hooks."],
                        "recommendations": ["Ejecutar revisión de pilares y piezas de copy."],
                        "next_actions": ["Lanzar operación recomendada desde el scorecard."],
                    },
                ),
                _ensure_seed_service_artifact(
                    company=company,
                    program=program,
                    user=user,
                    artifact_type="monthly_kpi_scorecard",
                    title="ATLAS Autoevaluación KPI mensual demo",
                    content={
                        "service_area": "Reportes y optimización mensual",
                        "profile_id": "atlas_monthly_kpi_scorecard.v1",
                        "summary": "Scorecard mensual generado por el Judge genérico.",
                    },
                ),
            ]
        )
    evaluation = None
    if include_kpi_scorecard:
        evaluation = _ensure_atlas_kpi_scorecard(company=company, program=program, user=user)
    service_history_projection = None
    if include_client_history:
        service_artifacts.append(
            _ensure_seed_service_artifact(
                company=company,
                program=program,
                user=user,
                artifact_type="client_service_history_entry",
                title="ATLAS Entrada de historial del servicio demo",
                content={
                    "report_refs": [
                        str(item.id)
                        for item in service_artifacts
                        if (item.metadata_json or {}).get("artifact_type") == "monthly_report"
                    ],
                    "evaluation_run_id": str(evaluation.id) if evaluation else None,
                    "notes": "Historial demo con reportes, entregables y expediente preservados en backend.",
                },
            )
        )
        service_history_projection = materialize_service_history_projection(
            company=company,
            program=program,
            projection_type="client_service_history",
            display_label="Historial del servicio",
        )
    return {
        "artifact_ids": [str(item.id) for item in service_artifacts],
        "artifact_types": [
            str((item.metadata_json or {}).get("artifact_type") or item.asset_type)
            for item in service_artifacts
        ],
        "evaluation_id": str(evaluation.id) if evaluation else "",
        "scorecard_levels": _scorecard_levels(evaluation),
        "service_history_projection_id": str(service_history_projection.id)
        if service_history_projection
        else "",
        "signal_ids": [
            str(item.id)
            for item in CompanySignal.objects.filter(
                company=company,
                source="evaluation_scorecard",
                metadata_json__program_id=str(program.id),
            )
        ],
    }


def _ensure_seed_service_artifact(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
    artifact_type: str,
    title: str,
    content: dict[str, Any],
) -> Asset:
    source_key = f"atlas-service-model:{program.id}:{artifact_type}"
    asset, _ = create_work_artifact(
        company=company,
        program=program,
        user=user,
        title=title,
        artifact_type=artifact_type,
        content={**content, "source_seed": SEED_KEY},
        metadata={"source_seed": SEED_KEY, "atlas_service_model": True},
        source_key=source_key,
    )
    return asset


def _ensure_atlas_kpi_scorecard(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
) -> EvaluationRun:
    existing = EvaluationRun.objects.filter(
        company=company,
        program=program,
        profile_key="atlas_monthly_kpi_scorecard.v1",
    ).first()
    if existing is not None:
        return existing
    return run_evaluation(
        company=company,
        user=user,
        program=program,
        profile_id="atlas_monthly_kpi_scorecard.v1",
        input_refs=[{"type": "seed", "id": SEED_KEY}],
        inputs={
            "metrics": {
                "social_engagement_rate": 0.7,
                "email_open_rate": 20,
                "roas": 3.5,
                "cost_per_lead_services": {
                    "level": "acceptable",
                    "notes": "Costo sostenible para el ticket demo.",
                },
                "cac_vs_profit": {
                    "level": "good",
                    "notes": "CAC demo por debajo de utilidad bruta esperada.",
                },
                "publishing_frequency": {
                    "level": "bad_or_risky",
                    "notes": "La frecuencia demo está por debajo del ritmo mensual esperado.",
                },
            }
        },
    )


def _ensure_periodic_loop_state(
    *,
    company: Graph,
    program: CompanyProgram,
    user: User,
    include_monthly_metrics: bool,
    include_trends: bool,
    include_periodic_scheduling: bool,
    include_missing_metrics: bool,
    include_overdue_review: bool,
) -> dict[str, Any]:
    review = _ensure_atlas_periodic_review(company=company, user=user)
    snapshots: list[MetricSnapshot] = []
    evaluations: list[EvaluationRun] = []
    reports: list[ReportRun] = []
    if include_monthly_metrics or include_trends:
        snapshots.append(
            _ensure_metric_snapshot(
                company=company,
                program=program,
                review=review,
                user=user,
                period_start="2026-03-01",
                period_end="2026-03-31",
                values={
                    "social_engagement_rate": 0.8,
                    "email_open_rate": 14,
                    "roas": 1.2,
                    "website_bounce_rate": 72,
                    "whatsapp_conversion": 8,
                    "publishing_frequency": {"level": "bad_or_risky", "notes": "Only two posts."},
                    "cost_per_lead_services": {
                        "value": 120,
                        "average_ticket": 2000,
                        "gross_margin": 0.45,
                        "lead_to_sale_conversion_rate": 0.08,
                        "target_profit_margin": 0.25,
                    },
                    "cac_vs_profit": {
                        "customer_acquisition_cost": 850,
                        "gross_profit_per_customer": 1200,
                    },
                },
            )
        )
        snapshots.append(
            _ensure_metric_snapshot(
                company=company,
                program=program,
                review=review,
                user=user,
                period_start="2026-04-01",
                period_end="2026-04-30",
                values={
                    "social_engagement_rate": 2.2,
                    "email_open_rate": 22,
                    "roas": 1.1,
                    "website_bounce_rate": 58,
                    "whatsapp_conversion": 18,
                    "publishing_frequency": 18,
                    "cost_per_lead_services": {
                        "value": 60,
                        "average_ticket": 2000,
                        "gross_margin": 0.45,
                        "lead_to_sale_conversion_rate": 0.08,
                        "target_profit_margin": 0.25,
                    },
                    "cac_vs_profit": {
                        "customer_acquisition_cost": 1450,
                        "gross_profit_per_customer": 1200,
                    },
                },
            )
        )
    for snapshot in snapshots:
        evaluation, report = _ensure_periodic_review_run(
            review=review,
            snapshot=snapshot,
            user=user,
        )
        evaluations.append(evaluation)
        reports.append(report)
    history_projection = materialize_service_history_projection(
        company=company,
        program=program,
        projection_type="client_service_history",
        display_label="Historial del servicio",
    )
    trend_summary = (
        evaluations[-1].result_json.get("trend_summary")
        if evaluations and isinstance(evaluations[-1].result_json, dict)
        else {}
    )
    scheduling = {}
    if include_periodic_scheduling or include_missing_metrics or include_overdue_review:
        scheduling = _ensure_periodic_scheduling_state(
            company=company,
            user=user,
            completed_review=review,
            include_missing_metrics=include_missing_metrics,
            include_overdue_review=include_overdue_review,
        )
    return {
        "review_definition": periodic_review_payload(review),
        "metric_snapshot_ids": [str(item.id) for item in snapshots],
        "evaluation_run_ids": [str(item.id) for item in evaluations],
        "report_run_ids": [str(item.id) for item in reports],
        "report_artifact_ids": [str(item.artifact_id) for item in reports if item.artifact_id],
        "trend_summary": trend_summary,
        "signal_ids": [
            str(item.id)
            for item in CompanySignal.objects.filter(
                company=company,
                source="evaluation_scorecard",
                metadata_json__program_id=str(program.id),
            )
        ],
        "history_projection_id": str(history_projection.id),
        "scheduling": scheduling,
    }


def _ensure_periodic_scheduling_state(
    *,
    company: Graph,
    user: User,
    completed_review: PeriodicReviewDefinition,
    include_missing_metrics: bool,
    include_overdue_review: bool,
) -> dict[str, Any]:
    current_period = current_due_review_period(completed_review)
    completed_ids = (
        [str(completed_review.id)]
        if ReportRun.objects.filter(
            company=company,
            review_definition=completed_review,
            period_start=current_period.period_start,
            period_end=current_period.period_end,
        ).exists()
        else []
    )
    due_review = _ensure_scheduling_review(
        company=company,
        user=user,
        template_id="atlas_monthly_review_due.seed",
        display_name="Reporte mensual demo pendiente",
    )
    due_period = current_due_review_period(due_review)
    due_ids = (
        [str(due_review.id)]
        if not ReportRun.objects.filter(
            company=company,
            review_definition=due_review,
            period_start=due_period.period_start,
            period_end=due_period.period_end,
        ).exists()
        else []
    )
    overdue_ids: list[str] = []
    if include_overdue_review:
        overdue_review = _ensure_scheduling_review(
            company=company,
            user=user,
            template_id="atlas_monthly_review_overdue.seed",
            display_name="Reporte mensual demo vencido",
        )
        overdue_ids.append(str(overdue_review.id))
    missing_summary: dict[str, Any] = {}
    if include_missing_metrics:
        summary = execute_periodic_review(
            review=due_review,
            user=user,
            period_start=due_period.period_start,
            period_end=due_period.period_end,
            notes="ATLAS scheduling demo missing metric request.",
        )
        missing_summary = summary.as_payload()
    return {
        "due_review_ids": due_ids,
        "completed_review_ids": completed_ids,
        "overdue_review_ids": overdue_ids,
        "missing_metric_signal_ids": missing_summary.get("signal_ids", []),
        "missing_metric_blockers": missing_summary.get("blockers", []),
    }


def _ensure_scheduling_review(
    *,
    company: Graph,
    user: User,
    template_id: str,
    display_name: str,
) -> PeriodicReviewDefinition:
    existing = PeriodicReviewDefinition.objects.filter(
        company=company,
        program__isnull=True,
        template_id=template_id,
    ).first()
    if existing is not None:
        return existing
    return upsert_review_definition_from_template(
        company=company,
        user=user,
        pack_id=DEFAULT_PACK_ID,
        template={
            "id": template_id,
            "display_name": display_name,
            "cadence": "monthly",
            "timezone": "America/Mexico_City",
            "evaluation_profile_id": "atlas_monthly_kpi_scorecard.v1",
            "report_template_id": "atlas_monthly_report.v1",
            "history_projection_type": "client_service_history",
            "history_display_label": "Historial del servicio",
            "enabled": True,
            "report_template": {
                "id": "atlas_monthly_report.v1",
                "artifact_schema_id": "monthly_report",
                "sections": ["summary", "kpi_scorecard", "recommendations", "next_actions"],
            },
        },
    )


def _ensure_atlas_periodic_review(*, company: Graph, user: User) -> PeriodicReviewDefinition:
    existing = PeriodicReviewDefinition.objects.filter(
        company=company,
        program__isnull=True,
        template_id="atlas_monthly_review.v1",
    ).first()
    if existing is not None:
        return existing
    return upsert_review_definition_from_template(
        company=company,
        user=user,
        pack_id=DEFAULT_PACK_ID,
        template={
            "id": "atlas_monthly_review.v1",
            "display_name": "Reporte y optimización mensual",
            "cadence": "monthly",
            "timezone": "America/Mexico_City",
            "evaluation_profile_id": "atlas_monthly_kpi_scorecard.v1",
            "report_template_id": "atlas_monthly_report.v1",
            "history_projection_type": "client_service_history",
            "history_display_label": "Historial del servicio",
            "report_template": {
                "id": "atlas_monthly_report.v1",
                "artifact_schema_id": "monthly_report",
                "sections": ["summary", "kpi_scorecard", "recommendations", "next_actions"],
            },
        },
    )


def _ensure_metric_snapshot(
    *,
    company: Graph,
    program: CompanyProgram,
    review: PeriodicReviewDefinition,
    user: User,
    period_start: str,
    period_end: str,
    values: dict[str, Any],
) -> MetricSnapshot:
    existing = MetricSnapshot.objects.filter(
        company=company,
        program=program,
        review_definition=review,
        period_start=period_start,
        period_end=period_end,
        source_type="seed",
    ).first()
    if existing is not None:
        return existing
    from datetime import date

    return create_metric_snapshot(
        company=company,
        program=program,
        review_definition=review,
        user=user,
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        metric_values=values,
        metric_sources={"source": "ATLAS demo seed", "seed_key": SEED_KEY},
        source_type="seed",
        notes="ATLAS periodic operating loop demo snapshot.",
    )


def _ensure_periodic_review_run(
    *,
    review: PeriodicReviewDefinition,
    snapshot: MetricSnapshot,
    user: User,
) -> tuple[EvaluationRun, ReportRun]:
    existing_evaluation = _evaluation_for_snapshot(company=review.company, snapshot=snapshot)
    existing_report = ReportRun.objects.filter(
        company=review.company,
        review_definition=review,
        metric_snapshot=snapshot,
    ).first()
    if existing_evaluation is not None and existing_report is not None:
        return existing_evaluation, existing_report
    if existing_evaluation is not None:
        report = assemble_report_run(
            review=review,
            metric_snapshot=snapshot,
            evaluation=existing_evaluation,
            user=user,
            notes="ATLAS periodic operating loop demo report.",
        )
        return existing_evaluation, report
    return run_periodic_review(
        review=review,
        metric_snapshot=snapshot,
        user=user,
        notes="ATLAS periodic operating loop demo report.",
    )


def _evaluation_for_snapshot(*, company: Graph, snapshot: MetricSnapshot) -> EvaluationRun | None:
    for evaluation in EvaluationRun.objects.filter(company=company).order_by("-created_at")[:50]:
        result = evaluation.result_json if isinstance(evaluation.result_json, dict) else {}
        if str(result.get("metric_snapshot_id") or "") == str(snapshot.id):
            return evaluation
    return None


def _scorecard_levels(evaluation: EvaluationRun | None) -> dict[str, str]:
    if evaluation is None or not isinstance(evaluation.result_json, dict):
        return {}
    metrics = evaluation.result_json.get("metrics")
    if not isinstance(metrics, list):
        return {}
    return {
        str(item.get("metric_id")): str(item.get("level"))
        for item in metrics
        if isinstance(item, dict) and item.get("metric_id")
    }


def _latest_graph_version_id(company: Graph) -> str:
    latest = GraphVersion.objects.filter(graph=company).aggregate(Max("version"))["version__max"]
    if latest is None:
        return ""
    version_id = (
        GraphVersion.objects.filter(graph=company, version=latest)
        .values_list("id", flat=True)
        .first()
    )
    return str(version_id or "")
