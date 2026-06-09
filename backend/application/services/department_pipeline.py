"""Backend-owned department pipeline helpers for service engagements.

The pipeline deliberately reuses existing ForgeGraph runtime primitives:

- ``CompanyProgram`` is the durable campaign/pipeline container.
- ``ProgramStageState`` is the durable state for each department stage.
- ``DepartmentRegistry`` remains the organization-owned department registry.
- ``ServiceDeliverable`` / ``Asset`` / ``AssetVersion`` keep customer-facing outputs.

No UI/event state is authoritative here; callers render snapshots from these backend
records.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.company_run_task_routing import (
    attach_deliverable_to_stage_task,
    bootstrap_task_routing_for_program,
    mark_task_blocked,
    mark_task_completed,
    mark_task_running,
)
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyProgram,
    DepartmentRegistry,
    ProgramStageState,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
)

DEFAULT_TEMPLATE_ID = "digital_marketing_pro.weekend_social_launch.v1"
PIPELINE_METADATA_KEY = "department_pipeline"

_STAGE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "stage_id": "strategy_research",
        "label": "Strategy & Research",
        "sequence": 1,
        "dependencies": [],
        "required": True,
    },
    {
        "stage_id": "brand_content",
        "label": "Brand & Content",
        "sequence": 2,
        "dependencies": ["strategy_research"],
        "required": True,
    },
    {
        "stage_id": "crm_lifecycle",
        "label": "CRM & Lifecycle",
        "sequence": 3,
        "dependencies": ["strategy_research"],
        "required": False,
        "skippable": True,
    },
    {
        "stage_id": "analytics_performance",
        "label": "Analytics & Performance",
        "sequence": 4,
        "dependencies": ["strategy_research"],
        "required": True,
    },
    {
        "stage_id": "channel_execution",
        "label": "Channel Execution",
        "sequence": 5,
        "dependencies": ["brand_content"],
        "required": True,
    },
    {
        "stage_id": "qa_compliance",
        "label": "QA & Compliance",
        "sequence": 6,
        "dependencies": [
            "channel_execution",
            "crm_lifecycle",
            "analytics_performance",
        ],
        "required": True,
    },
    {
        "stage_id": "client_approval_ops",
        "label": "Client / Approval Ops",
        "sequence": 7,
        "dependencies": ["qa_compliance"],
        "required": True,
    },
)
_STAGE_BY_ID = {str(item["stage_id"]): item for item in _STAGE_DEFINITIONS}


class DepartmentPipelineError(Exception):
    """Domain error for service engagement department pipelines."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


@transaction.atomic
def create_pipeline_for_engagement(
    engagement: ServiceEngagement,
    template_id: str = DEFAULT_TEMPLATE_ID,
    created_by: User | None = None,
    run_context: dict[str, Any] | None = None,
) -> CompanyProgram:
    """Create or reuse the seven-stage department pipeline for an engagement."""

    departments = _required_departments(engagement)
    external_key = _pipeline_external_key(engagement, template_id)
    program, created = CompanyProgram.objects.get_or_create(
        company=engagement.company,
        external_key=external_key,
        defaults={
            "organization": engagement.organization,
            "pack_id": "digital_marketing_pro.v1",
            "template_id": template_id,
            "display_label": "Department Pipeline",
            "title": f"{engagement.company.name} Department Pipeline",
            "objective": engagement.public_summary or engagement.catalog_item.title,
            "status": "active",
            "current_stage_id": "strategy_research",
            "metadata_json": {
                "service_engagement_id": str(engagement.id),
                "service_catalog_item_id": str(engagement.catalog_item_id),
                "created_via": "department_pipeline_service",
            },
            "created_by": created_by,
        },
    )
    if not created:
        metadata = dict(program.metadata_json or {})
        metadata.setdefault("service_engagement_id", str(engagement.id))
        metadata.setdefault("service_catalog_item_id", str(engagement.catalog_item_id))
        metadata.setdefault("created_via", "department_pipeline_service")
        if metadata != program.metadata_json:
            program.metadata_json = metadata
            program.save(update_fields=["metadata_json", "updated_at"])

    for definition in _STAGE_DEFINITIONS:
        stage_id = str(definition["stage_id"])
        _ensure_stage_state(
            program=program,
            engagement=engagement,
            definition=definition,
            department=departments[stage_id],
        )

    whiteboard = _whiteboard_for_engagement(engagement)
    bootstrap_task_routing_for_program(
        program,
        whiteboard=whiteboard,
        created_by=created_by,
        run_context={
            "source": "department_pipeline_service",
            "template_id": template_id,
            **(run_context or {}),
        },
    )
    return program


def _ensure_stage_state(
    *,
    program: CompanyProgram,
    engagement: ServiceEngagement,
    definition: dict[str, Any],
    department: DepartmentRegistry,
) -> ProgramStageState:
    stage, stage_created = ProgramStageState.objects.get_or_create(
        program=program,
        stage_id=str(definition["stage_id"]),
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "label": str(definition["label"]),
            "sequence": int(definition["sequence"]),
            "status": "not_started",
            "state_json": _initial_stage_state(
                definition=definition,
                department=department,
                engagement=engagement,
            ),
        },
    )
    if stage_created:
        return stage
    state = _normalized_stage_state(stage, definition, department, engagement)
    updates = _stage_update_fields(stage, definition, engagement, state)
    if updates:
        updates.append("updated_at")
        stage.save(update_fields=updates)
    return stage


def _stage_update_fields(
    stage: ProgramStageState,
    definition: dict[str, Any],
    engagement: ServiceEngagement,
    state: dict[str, Any],
) -> list[str]:
    updates: list[str] = []
    if stage.organization_id != engagement.organization_id:
        stage.organization = engagement.organization
        updates.append("organization")
    if stage.company_id != engagement.company_id:
        stage.company = engagement.company
        updates.append("company")
    if stage.label != definition["label"]:
        stage.label = str(definition["label"])
        updates.append("label")
    if stage.sequence != int(definition["sequence"]):
        stage.sequence = int(definition["sequence"])
        updates.append("sequence")
    if state != stage.state_json:
        stage.state_json = state
        updates.append("state_json")
    return updates


def get_pipeline_snapshot(engagement: ServiceEngagement) -> dict[str, Any]:
    """Return a renderable backend snapshot of an engagement department pipeline."""

    program = _pipeline_for_engagement(engagement)
    if program is None:
        return {
            "engagement_id": str(engagement.id),
            "program": None,
            "stages": [],
            "created": False,
        }
    stages = list(program.stage_states.order_by("sequence", "stage_id"))
    return {
        "engagement_id": str(engagement.id),
        "created": True,
        "program": _program_payload(program),
        "stages": [_stage_payload(stage) for stage in stages],
    }


@transaction.atomic
def start_stage(stage_state: ProgramStageState, actor: User | None = None) -> ProgramStageState:
    stage_state = _locked_stage(stage_state)
    if stage_state.status == "completed":
        return stage_state
    if stage_state.status not in {"not_started", "blocked", "rerun_required"}:
        raise DepartmentPipelineError(
            "INVALID_STAGE_STATUS",
            f"Stage {stage_state.stage_id} cannot be started from {stage_state.status}.",
        )
    _assert_dependencies_satisfied(stage_state)
    state = dict(stage_state.state_json or {})
    state["started_by_id"] = str(actor.id) if actor else None
    stage_state.status = "in_progress"
    stage_state.started_at = stage_state.started_at or timezone.now()
    stage_state.state_json = state
    stage_state.save(update_fields=["status", "started_at", "state_json", "updated_at"])
    _set_program_current_stage(stage_state)
    mark_task_running(stage_state, actor=actor)
    return stage_state


@transaction.atomic
def complete_stage(
    stage_state: ProgramStageState,
    outputs: Iterable[dict[str, Any]] | None = None,
    actor: User | None = None,
) -> ProgramStageState:
    stage_state = _locked_stage(stage_state)
    if stage_state.status == "completed":
        return stage_state
    if stage_state.status not in {"in_progress", "awaiting_validation"}:
        raise DepartmentPipelineError(
            "INVALID_STAGE_STATUS",
            f"Stage {stage_state.stage_id} cannot be completed from {stage_state.status}.",
        )
    _assert_dependencies_satisfied(stage_state)
    if stage_state.stage_id == "client_approval_ops":
        _assert_qa_allows_approval(stage_state)
    state = dict(stage_state.state_json or {})
    current_outputs = _json_list(state.get("outputs"))
    for output in outputs or []:
        current_outputs.append(dict(output))
    state["outputs"] = current_outputs
    state["completed_by_id"] = str(actor.id) if actor else None
    state["skipped"] = False
    stage_state.status = "completed"
    stage_state.completed_at = timezone.now()
    stage_state.state_json = state
    stage_state.save(update_fields=["status", "completed_at", "state_json", "updated_at"])
    _advance_program_current_stage(stage_state.program)
    mark_task_completed(stage_state, actor=actor)
    return stage_state


@transaction.atomic
def block_stage(
    stage_state: ProgramStageState,
    reason: str,
    actor: User | None = None,
) -> ProgramStageState:
    reason = reason.strip()
    if not reason:
        raise DepartmentPipelineError("BLOCK_REASON_REQUIRED", "A block reason is required.")
    stage_state = _locked_stage(stage_state)
    if stage_state.status == "completed":
        raise DepartmentPipelineError(
            "COMPLETED_STAGE_IMMUTABLE",
            f"Stage {stage_state.stage_id} is already completed.",
        )
    state = dict(stage_state.state_json or {})
    blockers = _json_list(state.get("blockers"))
    blockers.append(
        {
            "reason": reason,
            "blocked_by_id": str(actor.id) if actor else None,
            "blocked_at": timezone.now().isoformat(),
        }
    )
    state["blockers"] = blockers
    stage_state.status = "blocked"
    stage_state.state_json = state
    stage_state.save(update_fields=["status", "state_json", "updated_at"])
    _set_program_current_stage(stage_state)
    mark_task_blocked(stage_state, reason=reason, actor=actor)
    return stage_state


@transaction.atomic
def skip_stage(
    stage_state: ProgramStageState,
    reason: str,
    actor: User | None = None,
) -> ProgramStageState:
    reason = reason.strip()
    if not reason:
        raise DepartmentPipelineError("SKIP_REASON_REQUIRED", "A skip reason is required.")
    stage_state = _locked_stage(stage_state)
    if stage_state.stage_id != "crm_lifecycle":
        raise DepartmentPipelineError(
            "STAGE_NOT_SKIPPABLE",
            f"Stage {stage_state.stage_id} cannot be skipped in the weekend MVP.",
        )
    _assert_dependencies_satisfied(stage_state)
    state = dict(stage_state.state_json or {})
    state["skipped"] = True
    state["skipped_reason"] = reason
    state["completed_by_id"] = str(actor.id) if actor else None
    stage_state.status = "completed"
    stage_state.completed_at = timezone.now()
    stage_state.state_json = state
    stage_state.save(update_fields=["status", "completed_at", "state_json", "updated_at"])
    _advance_program_current_stage(stage_state.program)
    mark_task_completed(stage_state, actor=actor)
    return stage_state


@transaction.atomic
def attach_deliverable_to_stage(
    deliverable: ServiceDeliverable,
    stage_state: ProgramStageState,
    output_kind: str = "deliverable",
) -> ServiceDeliverable:
    _assert_same_scope(deliverable, stage_state)
    department = _department_for_stage(stage_state)
    metadata = dict(deliverable.metadata_json or {})
    metadata[PIPELINE_METADATA_KEY] = _lineage_payload(stage_state, output_kind=output_kind)
    deliverable.department = department
    deliverable.metadata_json = metadata
    deliverable.save(update_fields=["department", "metadata_json", "updated_at"])
    _append_stage_output(
        stage_state,
        {
            "kind": output_kind,
            "type": "service_deliverable",
            "id": str(deliverable.id),
            "title": deliverable.title,
        },
    )
    attach_deliverable_to_stage_task(stage_state, deliverable)
    return deliverable


@transaction.atomic
def attach_asset_to_stage(
    asset: Asset,
    stage_state: ProgramStageState,
    output_kind: str = "asset",
) -> Asset:
    _assert_same_scope(asset, stage_state)
    metadata = dict(asset.metadata_json or {})
    metadata[PIPELINE_METADATA_KEY] = _lineage_payload(stage_state, output_kind=output_kind)
    asset.metadata_json = metadata
    asset.save(update_fields=["metadata_json", "updated_at"])
    AssetVersion.objects.filter(asset=asset).update(
        provenance_json=_with_pipeline_provenance(asset, stage_state, output_kind)
    )
    _append_stage_output(
        stage_state,
        {
            "kind": output_kind,
            "type": "asset",
            "id": str(asset.id),
            "title": asset.title,
        },
    )
    return asset


def stage_state_for_engagement(
    engagement: ServiceEngagement,
    stage_id: str,
) -> ProgramStageState:
    program = _pipeline_for_engagement(engagement)
    if program is None:
        raise DepartmentPipelineError(
            "PIPELINE_NOT_FOUND",
            "Create the department pipeline before mutating stages.",
        )
    stage = program.stage_states.filter(stage_id=stage_id).first()
    if stage is None:
        raise DepartmentPipelineError(
            "STAGE_NOT_FOUND",
            f"Department pipeline stage {stage_id} was not found.",
        )
    return stage


def _required_departments(engagement: ServiceEngagement) -> dict[str, DepartmentRegistry]:
    slugs = [str(item["stage_id"]) for item in _STAGE_DEFINITIONS]
    departments = {
        item.slug: item
        for item in DepartmentRegistry.objects.filter(
            organization=engagement.organization,
            slug__in=slugs,
            active=True,
        )
    }
    missing = [slug for slug in slugs if slug not in departments]
    if missing:
        raise DepartmentPipelineError(
            "MISSING_DEPARTMENTS",
            "Create the Atlas agency departments before creating a department pipeline.",
            details=[{"missing_department_slugs": missing}],
        )
    return departments


def _pipeline_external_key(engagement: ServiceEngagement, template_id: str) -> str:
    return f"department-pipeline:{engagement.id}:{template_id}"[:255]


def _pipeline_for_engagement(engagement: ServiceEngagement) -> CompanyProgram | None:
    return (
        CompanyProgram.objects.filter(
            company=engagement.company,
            external_key=_pipeline_external_key(engagement, DEFAULT_TEMPLATE_ID),
        )
        .order_by("-updated_at")
        .first()
        or CompanyProgram.objects.filter(
            company=engagement.company,
            metadata_json__service_engagement_id=str(engagement.id),
        )
        .order_by("-updated_at")
        .first()
    )


def _whiteboard_for_engagement(engagement: ServiceEngagement) -> WorkWhiteboard | None:
    return (
        WorkWhiteboard.objects.filter(
            organization=engagement.organization,
            company=engagement.company,
            service_engagement=engagement,
        )
        .order_by("-updated_at")
        .first()
    )


def _initial_stage_state(
    *,
    definition: dict[str, Any],
    department: DepartmentRegistry,
    engagement: ServiceEngagement,
) -> dict[str, Any]:
    return {
        "service_engagement_id": str(engagement.id),
        "department_id": str(department.id),
        "department_slug": department.slug,
        "required": bool(definition.get("required", True)),
        "skippable": bool(definition.get("skippable", False)),
        "dependencies": list(definition.get("dependencies") or []),
        "inputs": [],
        "outputs": [],
        "blockers": [],
        "skipped": False,
        "skipped_reason": "",
    }


def _normalized_stage_state(
    stage: ProgramStageState,
    definition: dict[str, Any],
    department: DepartmentRegistry,
    engagement: ServiceEngagement,
) -> dict[str, Any]:
    state = dict(stage.state_json or {})
    defaults = _initial_stage_state(
        definition=definition,
        department=department,
        engagement=engagement,
    )
    for key, value in defaults.items():
        state.setdefault(key, value)
    state["service_engagement_id"] = str(engagement.id)
    state["department_id"] = str(department.id)
    state["department_slug"] = department.slug
    state["required"] = bool(definition.get("required", True))
    state["skippable"] = bool(definition.get("skippable", False))
    state["dependencies"] = list(definition.get("dependencies") or [])
    state["inputs"] = _json_list(state.get("inputs"))
    state["outputs"] = _json_list(state.get("outputs"))
    state["blockers"] = _json_list(state.get("blockers"))
    return state


def _locked_stage(stage_state: ProgramStageState) -> ProgramStageState:
    return ProgramStageState.objects.select_for_update().get(id=stage_state.id)


def _assert_dependencies_satisfied(stage_state: ProgramStageState) -> None:
    dependencies = list((stage_state.state_json or {}).get("dependencies") or [])
    if not dependencies:
        return
    stages = {
        stage.stage_id: stage
        for stage in stage_state.program.stage_states.filter(stage_id__in=dependencies)
    }
    unsatisfied: list[str] = []
    for dependency_id in dependencies:
        dependency = stages.get(dependency_id)
        if dependency is None or dependency.status != "completed":
            unsatisfied.append(dependency_id)
    if unsatisfied:
        raise DepartmentPipelineError(
            "DEPENDENCY_NOT_SATISFIED",
            f"Stage {stage_state.stage_id} depends on unfinished stages.",
            details=[{"unsatisfied_dependencies": unsatisfied}],
        )


def _assert_qa_allows_approval(stage_state: ProgramStageState) -> None:
    qa = stage_state.program.stage_states.filter(stage_id="qa_compliance").first()
    if qa is None:
        raise DepartmentPipelineError("QA_STAGE_MISSING", "QA stage was not found.")
    if qa.status == "completed":
        return
    if bool((qa.state_json or {}).get("qa_waiver")):
        return
    raise DepartmentPipelineError(
        "QA_REQUIRED",
        "Client approval cannot complete until QA is completed or explicitly waived.",
    )


def _department_for_stage(stage_state: ProgramStageState) -> DepartmentRegistry:
    department_id = (stage_state.state_json or {}).get("department_id")
    department = DepartmentRegistry.objects.filter(
        id=department_id,
        organization=stage_state.organization,
        active=True,
    ).first()
    if department is None:
        raise DepartmentPipelineError(
            "DEPARTMENT_NOT_FOUND",
            f"Department for stage {stage_state.stage_id} was not found.",
        )
    return department


def _append_stage_output(stage_state: ProgramStageState, output: dict[str, Any]) -> None:
    stage_state = _locked_stage(stage_state)
    state = dict(stage_state.state_json or {})
    outputs = _json_list(state.get("outputs"))
    if not any(
        item.get("id") == output.get("id") and item.get("type") == output.get("type")
        for item in outputs
    ):
        outputs.append(output)
    state["outputs"] = outputs
    stage_state.state_json = state
    stage_state.save(update_fields=["state_json", "updated_at"])


def _assert_same_scope(value: Any, stage_state: ProgramStageState) -> None:
    if (
        value.organization_id != stage_state.organization_id
        or value.company_id != stage_state.company_id
    ):
        raise DepartmentPipelineError(
            "SCOPE_MISMATCH",
            "Pipeline artifacts must belong to the same organization and company as the stage.",
        )


def _lineage_payload(stage_state: ProgramStageState, *, output_kind: str) -> dict[str, Any]:
    state = stage_state.state_json or {}
    return {
        "program_id": str(stage_state.program_id),
        "stage_state_id": str(stage_state.id),
        "stage_id": stage_state.stage_id,
        "department_id": state.get("department_id"),
        "department_slug": state.get("department_slug"),
        "output_kind": output_kind,
        "created_via_department_pipeline": True,
    }


def _with_pipeline_provenance(
    asset: Asset,
    stage_state: ProgramStageState,
    output_kind: str,
) -> dict[str, Any]:
    latest = asset.versions.order_by("-version_number").first()
    provenance = dict(latest.provenance_json or {}) if latest else {}
    provenance[PIPELINE_METADATA_KEY] = _lineage_payload(stage_state, output_kind=output_kind)
    return provenance


def _program_payload(program: CompanyProgram) -> dict[str, Any]:
    return {
        "id": str(program.id),
        "company_id": str(program.company_id),
        "template_id": program.template_id,
        "title": program.title,
        "objective": program.objective,
        "status": program.status,
        "current_stage_id": program.current_stage_id,
        "external_key": program.external_key,
        "metadata": dict(program.metadata_json or {}),
        "created_at": program.created_at.isoformat(),
        "updated_at": program.updated_at.isoformat(),
    }


def _stage_payload(stage: ProgramStageState) -> dict[str, Any]:
    state = dict(stage.state_json or {})
    return {
        "id": str(stage.id),
        "program_id": str(stage.program_id),
        "stage_id": stage.stage_id,
        "label": stage.label,
        "sequence": stage.sequence,
        "status": stage.status,
        "department_id": state.get("department_id"),
        "department_slug": state.get("department_slug"),
        "required": bool(state.get("required", True)),
        "skippable": bool(state.get("skippable", False)),
        "dependencies": list(state.get("dependencies") or []),
        "inputs": _json_list(state.get("inputs")),
        "outputs": _json_list(state.get("outputs")),
        "blockers": _json_list(state.get("blockers")),
        "skipped": bool(state.get("skipped", False)),
        "skipped_reason": str(state.get("skipped_reason") or ""),
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "updated_at": stage.updated_at.isoformat(),
    }


def _advance_program_current_stage(program: CompanyProgram) -> None:
    next_stage = program.stage_states.exclude(status="completed").order_by("sequence").first()
    current_stage_id = next_stage.stage_id if next_stage else ""
    if program.current_stage_id != current_stage_id:
        program.current_stage_id = current_stage_id
        program.save(update_fields=["current_stage_id", "updated_at"])


def _set_program_current_stage(stage_state: ProgramStageState) -> None:
    program = stage_state.program
    if program.current_stage_id != stage_state.stage_id:
        program.current_stage_id = stage_state.stage_id
        program.save(update_fields=["current_stage_id", "updated_at"])


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
