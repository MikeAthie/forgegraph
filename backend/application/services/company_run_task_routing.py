"""Business-agnostic task cards for backend-owned company programs.

The routing records created here are durable backend state. Whiteboard data is
refreshed as a denormalized read snapshot from those records and stage states.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.routing import record_routing_event, register_department
from infrastructure.orm.models import (
    AssetVersion,
    CompanyProgram,
    DepartmentRegistry,
    ProgramStageState,
    ServiceDeliverable,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

TASK_METADATA_KEY = "company_run_task"
TASK_ROUTING_PROVENANCE_KEY = "task_routing"
TASK_SNAPSHOT_METADATA_KEY = "company_run_task_snapshot"
TASK_EVENT_TYPE = "company_program.stage_task"
GENERIC_STATUSES = {"blocked", "ready", "running", "completed", "failed"}
ROUTING_STATUS_FOR_GENERIC = {
    "blocked": "blocked",
    "ready": "queued",
    "running": "in_progress",
    "completed": "completed",
    "failed": "blocked",
}


class CompanyRunTaskRoutingError(ValueError):
    """Domain error for company-run task routing."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@transaction.atomic
def bootstrap_task_routing_for_program(
    program: CompanyProgram,
    *,
    whiteboard: WorkWhiteboard | None = None,
    created_by: User | None = None,
    run_context: dict[str, Any] | None = None,
) -> list[TaskRoutingRecord]:
    """Create or update one visible routing record for every program stage."""

    program = (
        CompanyProgram.objects.select_for_update()
        .select_related(
            "organization",
            "company",
        )
        .get(id=program.id)
    )
    if whiteboard is not None:
        _assert_whiteboard_scope(whiteboard=whiteboard, program=program)
    stages = list(
        ProgramStageState.objects.select_for_update()
        .filter(program=program)
        .order_by("sequence", "stage_id")
    )
    dependency_map = _dependency_map(stages)
    records: list[TaskRoutingRecord] = []
    previous_department: DepartmentRegistry | None = None
    service_engagement = _service_engagement_for(program=program, whiteboard=whiteboard)
    runtime_provider = _runtime_provider(run_context)
    context = sanitize_outbox_payload(run_context or {})
    for stage in stages:
        dependencies = dependency_map[stage.stage_id]
        generic_status = _generic_status_for_stage(stage, dependencies=dependencies)
        department = _department_for_stage(stage)
        title = _stage_title(stage)
        key = _task_idempotency_key(stage)
        metadata = _record_metadata(
            program=program,
            stage=stage,
            department=department,
            title=title,
            generic_status=generic_status,
            dependencies=dependencies,
            whiteboard=whiteboard,
            run_context=context,
            runtime_provider=runtime_provider,
        )
        record, created = _upsert_routing_record(
            program=program,
            stage=stage,
            department=department,
            from_department=previous_department,
            service_engagement=service_engagement,
            title=title,
            generic_status=generic_status,
            idempotency_key=key,
            metadata=metadata,
        )
        if created:
            record_routing_event(record)
        _link_stage_to_task(
            stage,
            record=record,
            status=generic_status,
            dependencies=dependencies,
            actor=created_by,
            runtime_provider=runtime_provider,
        )
        records.append(record)
        previous_department = department
    if whiteboard is not None:
        refresh_whiteboard_task_snapshot(whiteboard, program)
    return records


def mark_task_running(
    stage_state: ProgramStageState, *, actor: User | None = None
) -> TaskRoutingRecord:
    """Mark the stage's routing task as running."""

    return _mark_task_status(stage_state, "running", actor=actor)


def mark_task_completed(
    stage_state: ProgramStageState,
    *,
    actor: User | None = None,
) -> TaskRoutingRecord:
    """Mark the stage's routing task as completed."""

    return _mark_task_status(stage_state, "completed", actor=actor)


def mark_task_blocked(
    stage_state: ProgramStageState,
    reason: str,
    *,
    actor: User | None = None,
) -> TaskRoutingRecord:
    """Mark the stage's routing task as blocked."""

    return _mark_task_status(
        stage_state,
        "blocked",
        actor=actor,
        error_message=_bounded_text(reason, 1200),
    )


def mark_task_failed(
    stage_state: ProgramStageState,
    error: Exception | str,
    *,
    actor: User | None = None,
) -> TaskRoutingRecord:
    """Mark the stage's routing task as failed and persist the backend error summary."""

    return _mark_task_status(
        stage_state,
        "failed",
        actor=actor,
        error_message=_bounded_text(str(error), 1200),
    )


@transaction.atomic
def attach_deliverable_to_stage_task(
    stage_state: ProgramStageState,
    deliverable: ServiceDeliverable,
    *,
    asset_versions: Sequence[AssetVersion] | None = None,
    runtime_provider: str | None = None,
) -> ServiceDeliverable:
    """Attach task routing provenance to a produced deliverable and its asset versions."""

    stage = (
        ProgramStageState.objects.select_for_update()
        .select_related("program")
        .get(id=stage_state.id)
    )
    if (
        deliverable.organization_id != stage.organization_id
        or deliverable.company_id != stage.company_id
    ):
        raise CompanyRunTaskRoutingError(
            "scope_mismatch",
            "Deliverable must belong to the same organization and company as the stage.",
        )
    record = _routing_record_for_stage(stage)
    if record is None:
        return deliverable
    provenance = _task_provenance(stage=stage, record=record, runtime_provider=runtime_provider)
    metadata = dict(deliverable.metadata_json or {})
    metadata[TASK_ROUTING_PROVENANCE_KEY] = provenance
    deliverable.metadata_json = sanitize_outbox_payload(metadata)
    deliverable.save(update_fields=["metadata_json", "updated_at"])

    versions = list(asset_versions or [])
    if not versions and deliverable.artifact_id:
        versions = list(AssetVersion.objects.filter(asset=deliverable.artifact))
    for version in versions:
        version_provenance = dict(version.provenance_json or {})
        version_provenance[TASK_ROUTING_PROVENANCE_KEY] = provenance
        version.provenance_json = sanitize_outbox_payload(version_provenance)
        version.save(update_fields=["provenance_json"])

    _append_task_evidence(
        record,
        evidence={
            "type": "service_deliverable",
            "id": str(deliverable.id),
            "title": deliverable.title,
            "asset_id": str(deliverable.artifact_id) if deliverable.artifact_id else None,
            "asset_version_ids": [str(version.id) for version in versions],
            "runtime_provider": runtime_provider or "",
        },
    )
    _append_stage_task_output(
        stage,
        output={
            "type": "service_deliverable",
            "id": str(deliverable.id),
            "routing_record_id": str(record.id),
            "asset_version_ids": [str(version.id) for version in versions],
        },
    )
    _refresh_linked_whiteboard(stage.program)
    return deliverable


def refresh_whiteboard_task_snapshot(
    whiteboard: WorkWhiteboard,
    program: CompanyProgram,
    *,
    refresh_read_models: bool = True,
) -> WorkWhiteboard:
    """Refresh the backend-owned task trail snapshot stored on the whiteboard."""

    _assert_whiteboard_scope(whiteboard=whiteboard, program=program)
    stages = list(
        ProgramStageState.objects.filter(program=program).order_by("sequence", "stage_id")
    )
    records = {
        str(record.id): record
        for record in TaskRoutingRecord.objects.filter(
            organization=program.organization,
            company=program.company,
            metadata_json__company_run_task__program_id=str(program.id),
        ).select_related("to_department")
    }
    snapshot = _whiteboard_snapshot_payload(
        whiteboard=whiteboard,
        program=program,
        stages=stages,
        records=records,
    )
    metadata = dict(whiteboard.metadata_json or {})
    metadata[TASK_SNAPSHOT_METADATA_KEY] = snapshot
    whiteboard.metadata_json = sanitize_outbox_payload(metadata)
    whiteboard.save(update_fields=["metadata_json", "updated_at"])
    if refresh_read_models:
        _refresh_whiteboard_read_models(whiteboard)
    return whiteboard


def task_routing_provenance_for_stage(
    stage_state: ProgramStageState,
    *,
    runtime_provider: str | None = None,
) -> dict[str, Any] | None:
    """Return routing provenance for callers that create assets directly."""

    record = _routing_record_for_stage(stage_state)
    if record is None:
        return None
    return _task_provenance(stage=stage_state, record=record, runtime_provider=runtime_provider)


@transaction.atomic
def _mark_task_status(
    stage_state: ProgramStageState,
    status: str,
    *,
    actor: User | None = None,
    error_message: str = "",
) -> TaskRoutingRecord:
    if status not in GENERIC_STATUSES:
        raise CompanyRunTaskRoutingError("invalid_status", "Company-run task status is invalid.")
    stage = (
        ProgramStageState.objects.select_for_update()
        .select_related("program")
        .get(id=stage_state.id)
    )
    record = _routing_record_for_stage(stage)
    if record is None:
        records = bootstrap_task_routing_for_program(
            stage.program,
            whiteboard=_whiteboard_for_program(stage.program),
            created_by=actor,
        )
        record = next(item for item in records if _record_stage_state_id(item) == str(stage.id))
    metadata = dict(record.metadata_json or {})
    task_metadata = dict(metadata.get(TASK_METADATA_KEY) or {})
    task_metadata["status"] = status
    task_metadata["updated_at"] = timezone.now().isoformat()
    if actor is not None:
        task_metadata["updated_by_id"] = str(actor.id)
    if error_message:
        task_metadata["error_message"] = error_message
    metadata[TASK_METADATA_KEY] = task_metadata
    record.status = ROUTING_STATUS_FOR_GENERIC[status]
    record.metadata_json = sanitize_outbox_payload(metadata)
    if error_message:
        resolution = dict(record.resolution_json or {})
        resolution["error_message"] = error_message
        record.resolution_json = sanitize_outbox_payload(resolution)
        record.save(update_fields=["status", "metadata_json", "resolution_json", "updated_at"])
    else:
        record.save(update_fields=["status", "metadata_json", "updated_at"])

    dependencies = _stage_dependencies(stage)
    _link_stage_to_task(stage, record=record, status=status, dependencies=dependencies, actor=actor)
    if _generic_status_for_stage(stage, dependencies=dependencies) == status:
        _sync_program_task_statuses(stage.program, actor=actor)
    else:
        _refresh_linked_whiteboard(stage.program)
    return record


def _sync_program_task_statuses(program: CompanyProgram, *, actor: User | None = None) -> None:
    stages = list(
        ProgramStageState.objects.select_for_update()
        .filter(program=program)
        .order_by("sequence", "stage_id")
    )
    dependencies_by_stage = _dependency_map(stages)
    for stage in stages:
        record = _routing_record_for_stage(stage)
        if record is None:
            continue
        dependencies = dependencies_by_stage[stage.stage_id]
        status = _generic_status_for_stage(stage, dependencies=dependencies)
        metadata = dict(record.metadata_json or {})
        task = dict(metadata.get(TASK_METADATA_KEY) or {})
        task["status"] = status
        task["dependencies"] = dependencies
        task["updated_at"] = timezone.now().isoformat()
        if actor is not None:
            task["updated_by_id"] = str(actor.id)
        metadata[TASK_METADATA_KEY] = task
        record.status = ROUTING_STATUS_FOR_GENERIC[status]
        record.metadata_json = sanitize_outbox_payload(metadata)
        record.save(update_fields=["status", "metadata_json", "updated_at"])
        _link_stage_to_task(
            stage,
            record=record,
            status=status,
            dependencies=dependencies,
            actor=actor,
        )
    _refresh_linked_whiteboard(program)


def _upsert_routing_record(
    *,
    program: CompanyProgram,
    stage: ProgramStageState,
    department: DepartmentRegistry,
    from_department: DepartmentRegistry | None,
    service_engagement: Any | None,
    title: str,
    generic_status: str,
    idempotency_key: str,
    metadata: dict[str, Any],
) -> tuple[TaskRoutingRecord, bool]:
    record = TaskRoutingRecord.objects.filter(
        organization=program.organization,
        idempotency_key=idempotency_key,
    ).first()
    created = False
    if record is None:
        record = TaskRoutingRecord(
            organization=program.organization,
            company=program.company,
            idempotency_key=idempotency_key,
        )
        created = True
    record.company = program.company
    record.service_engagement = service_engagement
    record.from_department = from_department
    record.to_department = department
    record.reason = _bounded_text(f"{title}: planned stage work for {program.title}.", 4000)
    record.status = ROUTING_STATUS_FOR_GENERIC[generic_status]
    record.priority = _priority_for_stage(stage)
    record.metadata_json = sanitize_outbox_payload(metadata)
    record.full_clean()
    try:
        record.save()
    except IntegrityError:
        existing = TaskRoutingRecord.objects.get(
            organization=program.organization,
            idempotency_key=idempotency_key,
        )
        return existing, False
    return record, created


def _record_metadata(
    *,
    program: CompanyProgram,
    stage: ProgramStageState,
    department: DepartmentRegistry,
    title: str,
    generic_status: str,
    dependencies: list[str],
    whiteboard: WorkWhiteboard | None,
    run_context: dict[str, Any],
    runtime_provider: str,
) -> dict[str, Any]:
    task_metadata: dict[str, Any] = {
        "program_id": str(program.id),
        "program_title": program.title,
        "program_template_id": program.template_id,
        "stage_state_id": str(stage.id),
        "stage_id": stage.stage_id,
        "stage_label": stage.label,
        "sequence": stage.sequence,
        "status": generic_status,
        "dependencies": dependencies,
        "department_id": str(department.id),
        "department_slug": department.slug,
        "runtime_provider": runtime_provider,
        "created_via": "company_run_task_routing",
    }
    metadata: dict[str, Any] = {
        "title": title,
        "customer_visible": False,
        "board_card": True,
        "whiteboard_id": str(whiteboard.id) if whiteboard is not None else None,
        "links": {
            "program_id": str(program.id),
            "stage_state_id": str(stage.id),
            "service_engagement_id": _service_engagement_id_for(
                program=program, whiteboard=whiteboard
            ),
        },
        TASK_METADATA_KEY: task_metadata,
        "event_type": TASK_EVENT_TYPE,
        "trigger_type": TASK_EVENT_TYPE,
    }
    if run_context:
        task_metadata["run_context"] = run_context
    return metadata


def _link_stage_to_task(
    stage: ProgramStageState,
    *,
    record: TaskRoutingRecord,
    status: str,
    dependencies: list[str],
    actor: User | None,
    runtime_provider: str = "",
) -> None:
    state = dict(stage.state_json or {})
    current = dict(state.get(TASK_METADATA_KEY) or {})
    current.update(
        {
            "routing_record_id": str(record.id),
            "idempotency_key": record.idempotency_key,
            "status": status,
            "db_status": record.status,
            "department_id": str(record.to_department_id),
            "department_slug": record.to_department.slug,
            "dependencies": dependencies,
            "updated_at": timezone.now().isoformat(),
        }
    )
    if actor is not None:
        current["updated_by_id"] = str(actor.id)
    if runtime_provider:
        current["runtime_provider"] = runtime_provider
    state[TASK_METADATA_KEY] = current
    if state != stage.state_json:
        stage.state_json = sanitize_outbox_payload(state)
        stage.save(update_fields=["state_json", "updated_at"])


def _append_stage_task_output(stage: ProgramStageState, *, output: dict[str, Any]) -> None:
    stage = ProgramStageState.objects.select_for_update().get(id=stage.id)
    state = dict(stage.state_json or {})
    task = dict(state.get(TASK_METADATA_KEY) or {})
    outputs = _json_list(task.get("outputs"))
    if not any(
        item.get("type") == output.get("type") and item.get("id") == output.get("id")
        for item in outputs
    ):
        outputs.append(output)
    task["outputs"] = outputs
    task["updated_at"] = timezone.now().isoformat()
    state[TASK_METADATA_KEY] = task
    stage.state_json = sanitize_outbox_payload(state)
    stage.save(update_fields=["state_json", "updated_at"])


def _append_task_evidence(record: TaskRoutingRecord, *, evidence: dict[str, Any]) -> None:
    record = TaskRoutingRecord.objects.select_for_update().get(id=record.id)
    resolution = dict(record.resolution_json or {})
    evidence_items = _json_list(resolution.get("evidence"))
    if not any(
        item.get("type") == evidence.get("type") and item.get("id") == evidence.get("id")
        for item in evidence_items
    ):
        evidence_items.append(sanitize_outbox_payload(evidence))
    resolution["evidence"] = evidence_items
    record.resolution_json = sanitize_outbox_payload(resolution)
    record.save(update_fields=["resolution_json", "updated_at"])


def _whiteboard_snapshot_payload(
    *,
    whiteboard: WorkWhiteboard,
    program: CompanyProgram,
    stages: list[ProgramStageState],
    records: dict[str, TaskRoutingRecord],
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for stage in stages:
        task = dict((stage.state_json or {}).get(TASK_METADATA_KEY) or {})
        record = records.get(str(task.get("routing_record_id") or ""))
        tasks.append(
            {
                "program_id": str(program.id),
                "stage_state_id": str(stage.id),
                "stage_id": stage.stage_id,
                "title": _stage_title(stage),
                "sequence": stage.sequence,
                "status": str(task.get("status") or _generic_status_for_stage(stage)),
                "stage_status": stage.status,
                "routing_record_id": str(record.id) if record is not None else "",
                "routing_record_status": record.status if record is not None else "",
                "department_id": str(record.to_department_id) if record is not None else "",
                "department_slug": record.to_department.slug if record is not None else "",
                "dependencies": list(task.get("dependencies") or _stage_dependencies(stage)),
                "outputs": _json_list(task.get("outputs")),
                "updated_at": stage.updated_at.isoformat(),
            }
        )
    return sanitize_outbox_payload(
        {
            "snapshot_source": "backend_db",
            "schema_version": "company_run_task_snapshot_v1",
            "whiteboard_id": str(whiteboard.id),
            "program_id": str(program.id),
            "program_title": program.title,
            "program_status": program.status,
            "current_stage_id": program.current_stage_id,
            "tasks": tasks,
            "refreshed_at": timezone.now().isoformat(),
        }
    )


def _dependency_map(stages: list[ProgramStageState]) -> dict[str, list[str]]:
    explicit_found = any(_explicit_dependencies(stage) is not None for stage in stages)
    dependencies: dict[str, list[str]] = {}
    previous_stage_id = ""
    for stage in stages:
        explicit = _explicit_dependencies(stage)
        if explicit is not None:
            dependencies[stage.stage_id] = explicit
        elif explicit_found:
            dependencies[stage.stage_id] = []
        elif previous_stage_id:
            dependencies[stage.stage_id] = [previous_stage_id]
        else:
            dependencies[stage.stage_id] = []
        previous_stage_id = stage.stage_id
    return dependencies


def _explicit_dependencies(stage: ProgramStageState) -> list[str] | None:
    state = dict(stage.state_json or {})
    for key in ("dependencies", "depends_on", "dependency_stage_ids"):
        if key in state:
            return _stage_id_list(state.get(key))
    raw_template = state.get("template")
    template: dict[str, Any] = raw_template if isinstance(raw_template, dict) else {}
    for key in ("dependencies", "depends_on", "dependency_stage_ids"):
        if key in template:
            return _stage_id_list(template.get(key))
    raw_metadata = state.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    for key in ("dependencies", "depends_on", "dependency_stage_ids"):
        if key in metadata:
            return _stage_id_list(metadata.get(key))
    return None


def _stage_dependencies(stage: ProgramStageState) -> list[str]:
    explicit = _explicit_dependencies(stage)
    if explicit is not None:
        return explicit
    previous_stage = (
        ProgramStageState.objects.filter(program=stage.program, sequence__lt=stage.sequence)
        .order_by("-sequence", "-stage_id")
        .first()
    )
    return [previous_stage.stage_id] if previous_stage is not None else []


def _stage_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        if isinstance(item, dict):
            raw = item.get("stage_id") or item.get("id")
        else:
            raw = item
        stage_id = str(raw or "").strip()
        if stage_id and stage_id not in results:
            results.append(stage_id)
    return results


def _generic_status_for_stage(
    stage: ProgramStageState,
    *,
    dependencies: Sequence[str] | None = None,
) -> str:
    if stage.status == "completed":
        return "completed"
    if stage.status in {"in_progress", "awaiting_validation"}:
        return "running"
    if stage.status == "blocked":
        return "blocked"
    if stage.status == "rerun_required":
        return "failed"
    dependency_ids = list(dependencies if dependencies is not None else _stage_dependencies(stage))
    if not dependency_ids:
        return "ready"
    completed = set(
        ProgramStageState.objects.filter(
            program=stage.program,
            stage_id__in=dependency_ids,
            status="completed",
        ).values_list("stage_id", flat=True)
    )
    return "ready" if set(dependency_ids).issubset(completed) else "blocked"


def _department_for_stage(stage: ProgramStageState) -> DepartmentRegistry:
    organization = stage.organization
    state = dict(stage.state_json or {})
    department_id = _department_id_from_state(state)
    if department_id:
        department = DepartmentRegistry.objects.filter(
            organization=organization,
            id=department_id,
        ).first()
        if department is not None:
            return department
    slug = _department_slug_from_state_or_stage(stage)
    department = DepartmentRegistry.objects.filter(
        organization=organization,
        slug=slug,
    ).first()
    if department is not None:
        return department
    return register_department(
        organization=organization,
        slug=slug,
        name=_stage_title(stage),
        department_type="program_stage",
        service_tags=["company_run", "program_stage"],
        active=True,
        metadata={
            "system_managed": True,
            "created_via": "company_run_task_routing",
            "fallback_for_stage_id": stage.stage_id,
        },
    )


def _department_id_from_state(state: dict[str, Any]) -> Any:
    if state.get("department_id"):
        return state.get("department_id")
    raw_template = state.get("template")
    template: dict[str, Any] = raw_template if isinstance(raw_template, dict) else {}
    return template.get("department_id")


def _department_slug_from_state_or_stage(stage: ProgramStageState) -> str:
    state = dict(stage.state_json or {})
    candidates = [
        state.get("department_slug"),
        state.get("department"),
    ]
    raw_template = state.get("template")
    template: dict[str, Any] = raw_template if isinstance(raw_template, dict) else {}
    candidates.extend([template.get("department_slug"), template.get("department")])
    for candidate in candidates:
        slug = _safe_slug(candidate)
        if slug:
            return slug
    return _safe_slug(stage.stage_id) or "program-stage"


def _stage_title(stage: ProgramStageState) -> str:
    state = dict(stage.state_json or {})
    raw_template = state.get("template")
    template: dict[str, Any] = raw_template if isinstance(raw_template, dict) else {}
    raw_metadata = state.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    for value in (
        state.get("task_title"),
        state.get("title"),
        state.get("label"),
        metadata.get("task_title"),
        metadata.get("title"),
        template.get("task_title"),
        template.get("title"),
        template.get("label"),
        stage.label,
    ):
        text = _bounded_text(value, 240)
        if text:
            return text
    return _humanize_stage_id(stage.stage_id)


def _priority_for_stage(stage: ProgramStageState) -> str:
    state = dict(stage.state_json or {})
    raw = state.get("priority")
    if not raw and isinstance(state.get("template"), dict):
        raw = state["template"].get("priority")
    priority = str(raw or "normal").strip().lower()
    return priority if priority in {"low", "normal", "high", "urgent"} else "normal"


def _task_provenance(
    *,
    stage: ProgramStageState,
    record: TaskRoutingRecord,
    runtime_provider: str | None,
) -> dict[str, Any]:
    state = dict(stage.state_json or {})
    return sanitize_outbox_payload(
        {
            "routing_record_id": str(record.id),
            "routing_idempotency_key": record.idempotency_key,
            "program_id": str(stage.program_id),
            "stage_state_id": str(stage.id),
            "stage_id": stage.stage_id,
            "stage_label": stage.label,
            "department_id": str(record.to_department_id),
            "department_slug": record.to_department.slug,
            "task_status": dict(state.get(TASK_METADATA_KEY) or {}).get("status"),
            "runtime_provider": runtime_provider or "",
            "created_via": "company_run_task_routing",
        }
    )


def _routing_record_for_stage(stage: ProgramStageState) -> TaskRoutingRecord | None:
    state = dict(stage.state_json or {})
    task = dict(state.get(TASK_METADATA_KEY) or {})
    record_id = str(task.get("routing_record_id") or "")
    queryset = TaskRoutingRecord.objects.select_related("to_department")
    if record_id:
        record = queryset.filter(id=record_id, organization=stage.organization).first()
        if record is not None:
            return record
    return queryset.filter(
        organization=stage.organization,
        idempotency_key=_task_idempotency_key(stage),
    ).first()


def _service_engagement_for(
    *,
    program: CompanyProgram,
    whiteboard: WorkWhiteboard | None,
) -> Any | None:
    if whiteboard is not None and whiteboard.service_engagement_id:
        return whiteboard.service_engagement
    engagement_id = _service_engagement_id_for(program=program, whiteboard=whiteboard)
    if not engagement_id:
        return None
    from infrastructure.orm.models import ServiceEngagement

    return ServiceEngagement.objects.filter(
        organization=program.organization,
        company=program.company,
        id=engagement_id,
    ).first()


def _service_engagement_id_for(
    *,
    program: CompanyProgram,
    whiteboard: WorkWhiteboard | None,
) -> str:
    if whiteboard is not None and whiteboard.service_engagement_id:
        return str(whiteboard.service_engagement_id)
    metadata = dict(program.metadata_json or {})
    return str(metadata.get("service_engagement_id") or "")


def _whiteboard_for_program(program: CompanyProgram) -> WorkWhiteboard | None:
    service_engagement_id = _service_engagement_id_for(program=program, whiteboard=None)
    queryset = WorkWhiteboard.objects.filter(
        organization=program.organization,
        company=program.company,
    )
    if service_engagement_id:
        try:
            service_engagement_uuid = UUID(service_engagement_id)
        except ValueError:
            service_engagement_uuid = None
        whiteboard = (
            queryset.filter(service_engagement_id=service_engagement_uuid).first()
            if service_engagement_uuid is not None
            else None
        )
        if whiteboard is not None:
            return whiteboard
    return queryset.filter(
        metadata_json__company_run_task_snapshot__program_id=str(program.id)
    ).first()


def _refresh_linked_whiteboard(program: CompanyProgram) -> None:
    whiteboard = _whiteboard_for_program(program)
    if whiteboard is not None:
        refresh_whiteboard_task_snapshot(whiteboard, program, refresh_read_models=False)


def _refresh_whiteboard_read_models(whiteboard: WorkWhiteboard) -> None:
    from application.services.whiteboard_boards import refresh_whiteboard_board_redis_snapshot
    from application.services.work_whiteboards import refresh_whiteboard_redis_snapshot

    refresh_whiteboard_redis_snapshot(whiteboard)
    refresh_whiteboard_board_redis_snapshot(whiteboard.id)


def _assert_whiteboard_scope(*, whiteboard: WorkWhiteboard, program: CompanyProgram) -> None:
    if (
        whiteboard.organization_id != program.organization_id
        or whiteboard.company_id != program.company_id
    ):
        raise CompanyRunTaskRoutingError(
            "scope_mismatch",
            "Whiteboard must belong to the same organization and company as the program.",
        )


def _task_idempotency_key(stage: ProgramStageState) -> str:
    return f"company-program:{stage.program_id}:stage:{stage.stage_id}:task-routing"[:255]


def _record_stage_state_id(record: TaskRoutingRecord) -> str:
    return str(
        dict(record.metadata_json or {}).get(TASK_METADATA_KEY, {}).get("stage_state_id") or ""
    )


def _runtime_provider(run_context: dict[str, Any] | None) -> str:
    if not isinstance(run_context, dict):
        return ""
    return str(run_context.get("runtime_provider") or run_context.get("provider") or "").strip()[
        :80
    ]


def _safe_slug(value: Any) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-_")
    return slug[:160]


def _humanize_stage_id(stage_id: str) -> str:
    words = re.split(r"[_\-\s]+", str(stage_id or "").strip())
    return " ".join(word.capitalize() for word in words if word) or "Program Stage"


def _bounded_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
