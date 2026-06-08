"""Generic company program services."""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.company_run_task_routing import bootstrap_task_routing_for_program
from application.services.operating_model_packs import load_pack_definition
from application.services.run_state_machine import create_backend_owned_run
from application.services.task_lifecycle import initialize_lifecycle_tasks_for_run
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    CompanyProgram,
    Graph,
    GraphVersion,
    ProgramStageState,
    Run,
    User,
)

PROGRAM_STAGE_STATUSES = {
    "not_started",
    "in_progress",
    "blocked",
    "awaiting_validation",
    "completed",
    "rerun_required",
}
DEFAULT_STAGE_TRANSITIONS: dict[str, set[str]] = {
    "not_started": {"not_started", "in_progress", "blocked"},
    "in_progress": {"in_progress", "blocked", "awaiting_validation", "completed"},
    "blocked": {"blocked", "in_progress", "awaiting_validation", "rerun_required"},
    "awaiting_validation": {
        "awaiting_validation",
        "in_progress",
        "completed",
        "rerun_required",
        "blocked",
    },
    "completed": {"completed", "rerun_required"},
    "rerun_required": {"rerun_required", "in_progress", "blocked", "completed"},
}


class CompanyProgramError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def create_program(
    *,
    company: Graph,
    user: User,
    template_id: str,
    title: str = "",
    objective: str = "",
    pack_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> CompanyProgram:
    installation = _resolve_installation(company=company, pack_id=pack_id, template_id=template_id)
    definition = load_pack_definition(installation.pack_id) if installation else None
    template = _program_template(definition.files if definition else {}, template_id)
    stages = _program_stages(definition.files if definition else {})
    first_stage_id = str(template.get("default_current_stage_id") or "")
    if not first_stage_id and stages:
        first_stage_id = str(stages[0].get("id") or "")
    display_label = str(template.get("display_label") or "Program")
    clean_title = _safe_text(title, 255) or str(template.get("title_template") or display_label)

    with transaction.atomic():
        program = CompanyProgram.objects.create(
            organization=cast(Any, company.organization),
            company=company,
            installation=installation,
            pack_id=installation.pack_id if installation else pack_id,
            template_id=template_id,
            display_label=display_label,
            title=clean_title,
            objective=_safe_text(objective, 4000) or str(template.get("objective_template") or ""),
            status="active",
            current_stage_id=first_stage_id,
            metadata_json=metadata or {},
            created_by=user,
        )
        for stage in stages:
            stage_id = str(stage.get("id") or "")
            if not stage_id:
                continue
            ProgramStageState.objects.create(
                organization=cast(Any, company.organization),
                company=company,
                program=program,
                stage_id=stage_id,
                label=str(stage.get("label") or stage_id),
                sequence=int(stage.get("sequence") or 1),
                status="in_progress" if stage_id == first_stage_id else "not_started",
                state_json={"template": stage},
                started_at=timezone.now() if stage_id == first_stage_id else None,
            )
        bootstrap_task_routing_for_program(
            program,
            created_by=user,
            run_context={
                "source": "company_programs.create_program",
                "template_id": template_id,
                "pack_id": program.pack_id,
            },
        )
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="company_program.created",
        resource_type="company_program",
        resource_id=str(program.id),
        metadata={"company_id": str(company.id), "template_id": template_id},
    )
    return program


def update_program(
    *,
    program: CompanyProgram,
    user: User,
    status: str | None = None,
    title: str | None = None,
    objective: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CompanyProgram:
    changed: list[str] = []
    if status is not None:
        program.status = status
        changed.append("status")
    if title is not None:
        program.title = _safe_text(title, 255) or program.title
        changed.append("title")
    if objective is not None:
        program.objective = _safe_text(objective, 4000)
        changed.append("objective")
    if metadata is not None:
        program.metadata_json = metadata
        changed.append("metadata_json")
    if changed:
        program.save(update_fields=[*changed, "updated_at"])
        record_audit_log(
            actor=user,
            tenant_id=str(program.organization_id),
            action="company_program.updated",
            resource_type="company_program",
            resource_id=str(program.id),
            metadata={"changed_fields": changed},
        )
    return program


def advance_program_stage(
    *,
    program: CompanyProgram,
    user: User,
    stage_id: str,
    status: str = "completed",
) -> ProgramStageState:
    stage = ProgramStageState.objects.filter(program=program, stage_id=stage_id).first()
    if stage is None:
        raise CompanyProgramError("stage_not_found", "Program stage was not found.")
    clean_status = str(status or "").strip()
    if clean_status == "active":
        clean_status = "in_progress"
    if clean_status == "skipped":
        clean_status = "completed"
    if clean_status not in PROGRAM_STAGE_STATUSES:
        raise CompanyProgramError("invalid_stage_status", "Program stage status is not supported.")
    definition = load_pack_definition(program.pack_id) if program.pack_id else None
    transitions = _stage_transition_rules(definition.files if definition else {})
    current_status = "in_progress" if stage.status == "active" else stage.status
    if clean_status not in transitions.get(current_status, set()):
        raise CompanyProgramError(
            "invalid_stage_transition",
            f"Stage cannot transition from {current_status} to {clean_status}.",
        )
    stage.status = clean_status
    if clean_status == "completed":
        stage.completed_at = timezone.now()
        next_stage = (
            ProgramStageState.objects.filter(program=program, sequence__gt=stage.sequence)
            .order_by("sequence")
            .first()
        )
        if next_stage is not None:
            next_stage.status = "in_progress"
            next_stage.started_at = next_stage.started_at or timezone.now()
            next_stage.save(update_fields=["status", "started_at", "updated_at"])
            program.current_stage_id = next_stage.stage_id
        else:
            program.status = "completed"
            program.current_stage_id = stage.stage_id
    else:
        if clean_status == "in_progress":
            stage.started_at = stage.started_at or timezone.now()
        if clean_status != "completed":
            stage.completed_at = None
        program.current_stage_id = stage.stage_id
    with transaction.atomic():
        stage.save(update_fields=["status", "started_at", "completed_at", "updated_at"])
        program.save(update_fields=["status", "current_stage_id", "updated_at"])
    record_audit_log(
        actor=user,
        tenant_id=str(program.organization_id),
        action="company_program.stage_advanced",
        resource_type="program_stage",
        resource_id=str(stage.id),
        metadata={"program_id": str(program.id), "stage_id": stage_id, "status": clean_status},
    )
    return stage


def launch_program_stage_operation(
    *,
    program: CompanyProgram,
    user: User,
    stage_id: str,
    operation_template_id: str,
    context_note: str = "",
    run_goal: str = "",
) -> Run:
    """Launch pack-defined work as a normal backend-owned operation run."""

    stage = ProgramStageState.objects.filter(program=program, stage_id=stage_id).first()
    if stage is None:
        raise CompanyProgramError("stage_not_found", "Program stage was not found.")
    definition = load_pack_definition(program.pack_id) if program.pack_id else None
    files = definition.files if definition else {}
    operation = _operation_template(files, operation_template_id)
    if not operation:
        raise CompanyProgramError(
            "operation_template_not_found", "Operation template was not found."
        )
    allowed_templates = _stage_operation_template_ids(stage)
    if allowed_templates and operation_template_id not in allowed_templates:
        raise CompanyProgramError(
            "operation_not_allowed_for_stage",
            "Operation template is not available for this program stage.",
        )
    graph_version = GraphVersion.objects.filter(graph=program.company).order_by("-version").first()
    if graph_version is None:
        raise CompanyProgramError(
            "graph_version_missing", "Program operations require a company graph version."
        )

    dispatch_graph_json = copy.deepcopy(graph_version.graph_json or {})
    metadata = dict(dispatch_graph_json.get("metadata") or {})
    metadata["program_operation"] = {
        "program_id": str(program.id),
        "stage_id": stage.stage_id,
        "operation_template_id": operation_template_id,
        "pack_id": program.pack_id,
        "created_by": "backend",
    }
    dispatch_graph_json["metadata"] = metadata
    input_json = {
        "company_name": program.company.name,
        "program_id": str(program.id),
        "program_label": program.display_label,
        "stage_id": stage.stage_id,
        "stage_label": stage.label,
        "operation_type": operation_template_id,
        "operation_label": str(operation.get("label") or operation_template_id),
        "operation_brief": str(operation.get("description") or ""),
        "operation_outputs": operation.get("outputs")
        if isinstance(operation.get("outputs"), list)
        else [],
        "context_note": _safe_text(context_note, 2000),
        "run_goal": _safe_text(run_goal, 2000),
        "operating_model_pack_id": program.pack_id,
    }
    with transaction.atomic():
        run = create_backend_owned_run(
            owner=user,
            organization=cast(Any, program.organization),
            graph_version=graph_version,
            status="pending",
            started_at=timezone.now(),
            input_json=input_json,
            dispatch_graph_json=dispatch_graph_json,
            output_json=None,
            error_message="",
        )
        initialize_lifecycle_tasks_for_run(
            run,
            source="company_program",
            initial_status="created",
            reason="pack-defined program operation created",
        )
        if stage.status in {"not_started", "blocked", "rerun_required"}:
            stage.status = "in_progress"
            stage.started_at = stage.started_at or timezone.now()
            stage.save(update_fields=["status", "started_at", "updated_at"])
            program.current_stage_id = stage.stage_id
            program.status = "active"
            program.save(update_fields=["status", "current_stage_id", "updated_at"])
    record_audit_log(
        actor=user,
        tenant_id=str(program.organization_id),
        action="company_program.operation_launched",
        resource_type="run",
        resource_id=str(run.id),
        metadata={
            "program_id": str(program.id),
            "stage_id": stage.stage_id,
            "operation_template_id": operation_template_id,
        },
    )
    return run


def program_payload(program: CompanyProgram, *, include_stages: bool = True) -> dict[str, Any]:
    payload = {
        "id": str(program.id),
        "company_id": str(program.company_id),
        "pack_id": program.pack_id,
        "template_id": program.template_id,
        "display_label": program.display_label,
        "title": program.title,
        "objective": program.objective,
        "status": program.status,
        "current_stage_id": program.current_stage_id,
        "metadata": program.metadata_json,
        "created_at": program.created_at.isoformat(),
        "updated_at": program.updated_at.isoformat(),
    }
    if include_stages:
        payload["stages"] = [
            stage_payload(stage)
            for stage in ProgramStageState.objects.filter(program=program).order_by("sequence")
        ]
    return payload


def stage_payload(stage: ProgramStageState) -> dict[str, Any]:
    operation_template_ids = _stage_operation_template_ids(stage)
    return {
        "id": str(stage.id),
        "program_id": str(stage.program_id),
        "stage_id": stage.stage_id,
        "label": stage.label,
        "sequence": stage.sequence,
        "status": "in_progress" if stage.status == "active" else stage.status,
        "state": stage.state_json,
        "operation_template_ids": operation_template_ids,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "updated_at": stage.updated_at.isoformat(),
    }


def _resolve_installation(
    *,
    company: Graph,
    pack_id: str,
    template_id: str,
) -> CompanyOperatingModelInstallation | None:
    queryset = CompanyOperatingModelInstallation.objects.filter(company=company, status="active")
    if pack_id:
        return queryset.filter(pack_id=pack_id).select_related("pack_release").first()
    for installation in queryset.select_related("pack_release"):
        definition = load_pack_definition(installation.pack_id)
        if _program_template(definition.files, template_id):
            return installation
    return None


def _program_template(files: dict[str, Any], template_id: str) -> dict[str, Any]:
    programs = files.get("programs") if isinstance(files, dict) else {}
    templates = programs.get("program_templates") if isinstance(programs, dict) else []
    if not isinstance(templates, list):
        return {}
    for template in templates:
        if isinstance(template, dict) and template.get("id") == template_id:
            return template
    return {}


def _program_stages(files: dict[str, Any]) -> list[dict[str, Any]]:
    stages_file = files.get("stages") if isinstance(files, dict) else {}
    stages = stages_file.get("stages") if isinstance(stages_file, dict) else []
    if not isinstance(stages, list):
        return []
    return sorted(
        [stage for stage in stages if isinstance(stage, dict)],
        key=lambda item: int(item.get("sequence") or 0),
    )


def _operation_template(files: dict[str, Any], operation_template_id: str) -> dict[str, Any]:
    for template in _operation_templates(files):
        if template.get("id") == operation_template_id:
            return template
    return {}


def _operation_templates(files: dict[str, Any]) -> list[dict[str, Any]]:
    operations_file = files.get("operations") if isinstance(files, dict) else {}
    templates = (
        operations_file.get("operation_templates") if isinstance(operations_file, dict) else []
    )
    if not isinstance(templates, list):
        return []
    return [item for item in templates if isinstance(item, dict)]


def _stage_operation_template_ids(stage: ProgramStageState) -> list[str]:
    state = stage.state_json if isinstance(stage.state_json, dict) else {}
    raw_template = state.get("template")
    template = raw_template if isinstance(raw_template, dict) else {}
    values = template.get("operation_template_ids")
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]


def _stage_transition_rules(files: dict[str, Any]) -> dict[str, set[str]]:
    stages_file = files.get("stages") if isinstance(files, dict) else {}
    raw = stages_file.get("status_transitions") if isinstance(stages_file, dict) else None
    rules: dict[str, set[str]] = {
        key: set(value) for key, value in DEFAULT_STAGE_TRANSITIONS.items()
    }
    if not isinstance(raw, dict):
        return rules
    for source, targets in raw.items():
        clean_source = str(source or "").strip()
        if clean_source not in PROGRAM_STAGE_STATUSES or not isinstance(targets, list):
            continue
        clean_targets = {
            str(item).strip() for item in targets if str(item).strip() in PROGRAM_STAGE_STATUSES
        }
        if clean_targets:
            rules[clean_source] = clean_targets
    return rules


def _safe_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
