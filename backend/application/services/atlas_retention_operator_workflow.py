"""Atlas retention operator workflow persistence.

The rows created here are backend-owned durable state. The whiteboard is
refreshed only as a projection of CompanyProgram, ProgramStageState, and
TaskRoutingRecord rows.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.company_run_task_routing import (
    TASK_METADATA_KEY,
    bootstrap_task_routing_for_program,
    refresh_whiteboard_task_snapshot,
)
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.routing import register_department
from infrastructure.orm.models import (
    CompanyProgram,
    DepartmentRegistry,
    ProgramStageState,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

TEMPLATE_ID = "atlas_retention_operator_workflow.v1"
WORKFLOW_METADATA_KEY = "atlas_retention_operator_workflow"
WORKFLOW_SCHEMA_VERSION = "atlas_retention_operator_workflow_v1"


@dataclass(frozen=True)
class AtlasRetentionStage:
    stage_id: str
    label: str
    department_slug: str
    task_title: str
    priority: str = "normal"


ATLAS_RETENTION_STAGES: tuple[AtlasRetentionStage, ...] = (
    AtlasRetentionStage(
        "intake",
        "Intake",
        "client_approval_ops",
        "Capture retention intake and source context",
        "high",
    ),
    AtlasRetentionStage(
        "audit",
        "Audit",
        "strategy_research",
        "Audit retention opportunity and receipts",
        "high",
    ),
    AtlasRetentionStage(
        "campaign_design",
        "Campaign Design",
        "crm_lifecycle",
        "Design retention campaign package",
        "high",
    ),
    AtlasRetentionStage(
        "asset_production",
        "Asset Production",
        "brand_content",
        "Produce retention campaign assets",
        "high",
    ),
    AtlasRetentionStage(
        "ready_to_launch",
        "Ready To Launch",
        "qa_compliance",
        "QA launch package and approvals",
        "high",
    ),
    AtlasRetentionStage(
        "live",
        "Live",
        "channel_execution",
        "Run live retention campaign",
        "high",
    ),
    AtlasRetentionStage(
        "follow_up_needed",
        "Follow Up Needed",
        "crm_lifecycle",
        "Work lead follow-up and commission signals",
        "urgent",
    ),
    AtlasRetentionStage(
        "review_report",
        "Review Report",
        "analytics_performance",
        "Prepare weekly proof report",
        "normal",
    ),
    AtlasRetentionStage(
        "scale_kill",
        "Scale Kill",
        "analytics_performance",
        "Decide scale, iterate, or stop",
        "normal",
    ),
    AtlasRetentionStage(
        "closed_commission",
        "Closed Commission",
        "client_approval_ops",
        "Close commission and retention ledger",
        "normal",
    ),
)

ATLAS_DEPARTMENT_SLUGS = tuple(sorted({stage.department_slug for stage in ATLAS_RETENTION_STAGES}))

_STAGE_BY_ID = {stage.stage_id: stage for stage in ATLAS_RETENTION_STAGES}
_STAGE_IDS = tuple(_STAGE_BY_ID)

_STAGE_SNAPSHOT_KEYS: dict[str, tuple[str, ...]] = {
    "intake": (
        "intake",
        "whatsapp_bridge",
        "whatsapp_connector",
        "source_thread",
    ),
    "audit": ("audit", "audit_report", "audit_findings"),
    "campaign_design": (
        "campaign",
        "campaign_design",
        "campaign_package",
        "strategy",
    ),
    "asset_production": (
        "assets",
        "asset",
        "asset_production",
        "asset_versions",
        "deliverables",
    ),
    "ready_to_launch": (
        "approval",
        "approval_packet",
        "launch_checklist",
        "ready_to_launch",
    ),
    "live": ("live", "launch", "campaign_launch"),
    "follow_up_needed": (
        "lead",
        "lead_tracker",
        "lead_tracking",
        "leads",
        "commission_tracker",
    ),
    "review_report": (
        "report",
        "reports",
        "weekly_report",
        "weekly_proof_report",
        "proof_report",
    ),
    "scale_kill": (
        "recommendation",
        "recommendations",
        "scale_kill",
        "optimization",
    ),
    "closed_commission": (
        "closed_commission",
        "commission",
        "commission_summary",
        "payouts",
    ),
}

_ARTIFACT_STAGE_BY_TYPE = {
    "campaign": "campaign_design",
    "campaign_package": "campaign_design",
    "strategy": "campaign_design",
    "asset": "asset_production",
    "asset_version": "asset_production",
    "deliverable": "asset_production",
    "approval": "ready_to_launch",
    "approval_packet": "ready_to_launch",
    "launch_checklist": "ready_to_launch",
    "lead": "follow_up_needed",
    "lead_tracker": "follow_up_needed",
    "commission": "closed_commission",
    "commission_summary": "closed_commission",
    "closed_commission": "closed_commission",
    "payouts": "closed_commission",
    "recommendation": "scale_kill",
    "recommendations": "scale_kill",
    "scale_kill": "scale_kill",
    "optimization": "scale_kill",
    "report": "review_report",
    "weekly_report": "review_report",
    "proof_report": "review_report",
}

_SENSITIVE_ARTIFACT_SOURCE_KEYS = {
    "intake",
    "source_thread",
    "whatsapp_bridge",
    "whatsapp_connector",
}
_PHONE_LIKE_RE = re.compile(r"(?<!\d)\+?[\d][\d\s().-]{7,}\d(?!\d)")


@transaction.atomic
def bootstrap_atlas_retention_operator_workflow(
    whiteboard: WorkWhiteboard,
    *,
    user: User | None = None,
    workflow_snapshot: Mapping[str, Any] | None = None,
    refresh_read_models: bool = True,
) -> dict[str, Any]:
    """Create or update durable Atlas retention workflow state.

    Re-running this function reuses the same program, stage states, and routing
    records. Artifact summaries are copied into durable stage and task metadata,
    and the whiteboard task snapshot is rebuilt from DB state.
    """

    locked_whiteboard = (
        WorkWhiteboard.objects.select_for_update()
        .select_related("organization", "company")
        .get(id=whiteboard.id)
    )
    departments = {
        slug: _ensure_department(locked_whiteboard, slug) for slug in ATLAS_DEPARTMENT_SLUGS
    }
    incoming_summaries = _artifact_summaries_by_stage(workflow_snapshot)

    program, program_created = _get_or_create_program(
        locked_whiteboard,
        user=user,
    )
    stages: list[ProgramStageState] = []
    stage_created_count = 0
    summaries_by_stage: dict[str, list[dict[str, Any]]] = {}
    for index, stage_spec in enumerate(ATLAS_RETENTION_STAGES, start=1):
        stage, stage_created = _get_or_create_stage(
            program,
            stage_spec=stage_spec,
            sequence=index,
        )
        if stage_created:
            stage_created_count += 1
        summaries = incoming_summaries.get(stage.stage_id)
        if summaries is None:
            summaries = _existing_stage_artifact_summaries(stage)
        summaries_by_stage[stage.stage_id] = summaries
        previous_stage_id = ATLAS_RETENTION_STAGES[index - 2].stage_id if index > 1 else ""
        _update_stage_state(
            stage,
            stage_spec=stage_spec,
            sequence=index,
            whiteboard=locked_whiteboard,
            department=departments[stage_spec.department_slug],
            artifact_summaries=summaries,
            previous_stage_id=previous_stage_id,
        )
        stage.refresh_from_db()
        stages.append(stage)

    _update_program_from_stages(
        program,
        whiteboard=locked_whiteboard,
        stages=stages,
        artifact_summaries=summaries_by_stage,
        user=user,
        workflow_snapshot=workflow_snapshot,
    )

    records = bootstrap_task_routing_for_program(
        program,
        whiteboard=locked_whiteboard,
        created_by=user,
        run_context={
            "source": "atlas_retention_operator_workflow",
            "runtime_provider": "forgegraph_backend",
            "template_id": TEMPLATE_ID,
        },
    )
    _sync_task_record_metadata(
        records,
        whiteboard=locked_whiteboard,
        artifact_summaries=summaries_by_stage,
    )
    refresh_whiteboard_task_snapshot(
        locked_whiteboard,
        program,
        refresh_read_models=refresh_read_models,
    )
    locked_whiteboard.refresh_from_db()

    return {
        "program": program,
        "program_created": program_created,
        "stages": stages,
        "stage_created_count": stage_created_count,
        "task_records": list(
            TaskRoutingRecord.objects.filter(
                organization=program.organization,
                company=program.company,
                metadata_json__company_run_task__program_id=str(program.id),
            ).select_related("to_department")
        ),
        "whiteboard": locked_whiteboard,
        "template_id": TEMPLATE_ID,
    }


def _ensure_department(whiteboard: WorkWhiteboard, slug: str) -> DepartmentRegistry:
    department = DepartmentRegistry.objects.filter(
        organization=whiteboard.organization,
        slug=slug,
    ).first()
    if department is not None:
        return department
    return register_department(
        organization=whiteboard.organization,
        slug=slug,
        name=_humanize_slug(slug),
        department_type="atlas_retention",
        service_tags=["atlas", "retention", "operator_workflow"],
        active=True,
        metadata={
            "system_managed": True,
            "created_via": WORKFLOW_METADATA_KEY,
            "template_id": TEMPLATE_ID,
        },
    )


def _get_or_create_program(
    whiteboard: WorkWhiteboard,
    *,
    user: User | None,
) -> tuple[CompanyProgram, bool]:
    external_key = _program_external_key(whiteboard)
    program, created = CompanyProgram.objects.get_or_create(
        company=whiteboard.company,
        external_key=external_key,
        defaults={
            "organization": whiteboard.organization,
            "template_id": TEMPLATE_ID,
            "display_label": "Atlas Retention",
            "title": _program_title(whiteboard),
            "objective": _program_objective(whiteboard),
            "status": "active",
            "current_stage_id": "intake",
            "pack_id": "atlas_retention",
            "metadata_json": {},
            "created_by": user,
        },
    )
    program = CompanyProgram.objects.select_for_update().get(id=program.id)
    return program, created


def _get_or_create_stage(
    program: CompanyProgram,
    *,
    stage_spec: AtlasRetentionStage,
    sequence: int,
) -> tuple[ProgramStageState, bool]:
    stage, created = ProgramStageState.objects.get_or_create(
        program=program,
        stage_id=stage_spec.stage_id,
        defaults={
            "organization": program.organization,
            "company": program.company,
            "label": stage_spec.label,
            "sequence": sequence,
            "status": "not_started",
            "state_json": {},
        },
    )
    stage = ProgramStageState.objects.select_for_update().get(id=stage.id)
    return stage, created


def _update_stage_state(
    stage: ProgramStageState,
    *,
    stage_spec: AtlasRetentionStage,
    sequence: int,
    whiteboard: WorkWhiteboard,
    department: DepartmentRegistry,
    artifact_summaries: list[dict[str, Any]],
    previous_stage_id: str,
) -> None:
    now = timezone.now().isoformat()
    state = dict(stage.state_json or {})
    template = dict(state.get("template") or {})
    template.update(
        {
            "id": TEMPLATE_ID,
            "stage_id": stage_spec.stage_id,
            "label": stage_spec.label,
            "task_title": stage_spec.task_title,
            "department_slug": stage_spec.department_slug,
            "priority": stage_spec.priority,
            "dependencies": [previous_stage_id] if previous_stage_id else [],
        }
    )
    workflow_metadata = dict(state.get(WORKFLOW_METADATA_KEY) or {})
    workflow_metadata.update(
        {
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "template_id": TEMPLATE_ID,
            "stage_id": stage_spec.stage_id,
            "whiteboard_id": str(whiteboard.id),
            "program_id": str(stage.program_id),
            "department_slug": stage_spec.department_slug,
            "artifact_summaries": artifact_summaries,
            "artifact_summary_count": len(artifact_summaries),
            "updated_at": now,
        }
    )
    task_metadata = dict(state.get(TASK_METADATA_KEY) or {})
    task_metadata.update(
        {
            "whiteboard_id": str(whiteboard.id),
            "program_id": str(stage.program_id),
            "template_id": TEMPLATE_ID,
            "department_slug": stage_spec.department_slug,
            "artifact_summaries": artifact_summaries,
            "outputs": _merge_atlas_outputs(
                task_metadata.get("outputs"),
                artifact_summaries,
            ),
        }
    )

    state.update(
        {
            "template": template,
            "task_title": stage_spec.task_title,
            "department_id": str(department.id),
            "department_slug": stage_spec.department_slug,
            "priority": stage_spec.priority,
            "dependencies": [previous_stage_id] if previous_stage_id else [],
            "artifact_summaries": artifact_summaries,
            WORKFLOW_METADATA_KEY: workflow_metadata,
            TASK_METADATA_KEY: task_metadata,
        }
    )
    stage.label = stage_spec.label
    stage.sequence = sequence
    stage.state_json = sanitize_outbox_payload(state)
    stage.save(
        update_fields=[
            "label",
            "sequence",
            "status",
            "state_json",
            "updated_at",
        ]
    )


def _update_program_from_stages(
    program: CompanyProgram,
    *,
    whiteboard: WorkWhiteboard,
    stages: list[ProgramStageState],
    artifact_summaries: dict[str, list[dict[str, Any]]],
    user: User | None,
    workflow_snapshot: Mapping[str, Any] | None,
) -> None:
    current_stage_id = _current_stage_id(stages)
    program.template_id = TEMPLATE_ID
    program.display_label = "Atlas Retention"
    program.title = _program_title(whiteboard)
    program.objective = _program_objective(whiteboard)
    program.pack_id = "atlas_retention"
    program.current_stage_id = current_stage_id
    program.status = (
        "completed" if all(stage.status == "completed" for stage in stages) else "active"
    )
    if program.created_by_id is None and user is not None:
        program.created_by = user
    metadata = dict(program.metadata_json or {})
    if whiteboard.service_engagement_id:
        metadata["service_engagement_id"] = str(whiteboard.service_engagement_id)
    metadata[WORKFLOW_METADATA_KEY] = sanitize_outbox_payload(
        {
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "template_id": TEMPLATE_ID,
            "whiteboard_id": str(whiteboard.id),
            "company_id": str(whiteboard.company_id),
            "stage_ids": list(_STAGE_IDS),
            "current_stage_id": current_stage_id,
            "artifact_summaries": artifact_summaries,
            "artifact_summary_count": sum(len(items) for items in artifact_summaries.values()),
            "snapshot_source": "backend_db",
            "updated_at": timezone.now().isoformat(),
        }
    )
    program.metadata_json = sanitize_outbox_payload(metadata)
    update_fields = [
        "template_id",
        "display_label",
        "title",
        "objective",
        "pack_id",
        "current_stage_id",
        "status",
        "metadata_json",
        "updated_at",
    ]
    if user is not None:
        update_fields.append("created_by")
    program.save(update_fields=update_fields)


def _sync_task_record_metadata(
    records: list[TaskRoutingRecord],
    *,
    whiteboard: WorkWhiteboard,
    artifact_summaries: dict[str, list[dict[str, Any]]],
) -> None:
    now = timezone.now().isoformat()
    for record in records:
        metadata = dict(record.metadata_json or {})
        task = dict(metadata.get(TASK_METADATA_KEY) or {})
        stage_id = str(task.get("stage_id") or "")
        summaries = artifact_summaries.get(stage_id, [])
        task.update(
            {
                "whiteboard_id": str(whiteboard.id),
                "template_id": TEMPLATE_ID,
                "artifact_summaries": summaries,
                "outputs": _merge_atlas_outputs(task.get("outputs"), summaries),
                "updated_at": now,
            }
        )
        metadata[TASK_METADATA_KEY] = task
        metadata[WORKFLOW_METADATA_KEY] = sanitize_outbox_payload(
            {
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "template_id": TEMPLATE_ID,
                "whiteboard_id": str(whiteboard.id),
                "program_id": task.get("program_id"),
                "stage_id": stage_id,
                "artifact_summaries": summaries,
                "artifact_summary_count": len(summaries),
                "snapshot_source": "backend_db",
                "updated_at": now,
            }
        )
        record.metadata_json = sanitize_outbox_payload(metadata)
        record.save(update_fields=["metadata_json", "updated_at"])


def _artifact_summaries_by_stage(
    workflow_snapshot: Mapping[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(workflow_snapshot, Mapping):
        return {}
    summaries: dict[str, list[dict[str, Any]]] = {stage_id: [] for stage_id in _STAGE_IDS}
    _collect_top_level_artifact_summaries(workflow_snapshot, summaries)
    _collect_explicit_artifact_summaries(workflow_snapshot, summaries)
    _collect_stage_artifact_summaries(workflow_snapshot.get("stages"), summaries)
    return {stage_id: _dedupe_summaries(items) for stage_id, items in summaries.items() if items}


def _collect_top_level_artifact_summaries(
    workflow_snapshot: Mapping[str, Any],
    summaries: dict[str, list[dict[str, Any]]],
) -> None:
    for stage_id, keys in _STAGE_SNAPSHOT_KEYS.items():
        for key in keys:
            if key not in workflow_snapshot:
                continue
            summaries[stage_id].extend(
                _artifact_summary_items(
                    workflow_snapshot[key],
                    stage_id=stage_id,
                    source_key=key,
                )
            )


def _collect_explicit_artifact_summaries(
    workflow_snapshot: Mapping[str, Any],
    summaries: dict[str, list[dict[str, Any]]],
) -> None:
    for item in _iter_artifact_collection(workflow_snapshot.get("artifacts")):
        stage_id = _stage_id_for_artifact(item)
        if not stage_id:
            continue
        summaries[stage_id].extend(
            _artifact_summary_items(
                item,
                stage_id=stage_id,
                source_key="artifacts",
            )
        )


def _collect_stage_artifact_summaries(
    stages: Any,
    summaries: dict[str, list[dict[str, Any]]],
) -> None:
    for stage_id, payload in _iter_stage_payloads(stages):
        summaries[stage_id].extend(
            _artifact_summary_items(
                payload.get("artifacts"),
                stage_id=stage_id,
                source_key=f"stages.{stage_id}.artifacts",
            )
        )


def _iter_stage_payloads(stages: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if isinstance(stages, Mapping):
        return [
            (stage_id, payload)
            for raw_stage_id, payload in stages.items()
            if (stage_id := str(raw_stage_id)) in _STAGE_BY_ID and isinstance(payload, Mapping)
        ]
    if not isinstance(stages, list):
        return []
    return [
        (stage_id, payload)
        for payload in stages
        if isinstance(payload, Mapping)
        and (stage_id := str(payload.get("stage_id") or payload.get("id") or "")) in _STAGE_BY_ID
    ]


def _artifact_summary_items(
    value: Any,
    *,
    stage_id: str,
    source_key: str,
) -> list[dict[str, Any]]:
    payloads = list(_iter_artifact_collection(value))
    if not payloads and value not in (None, "", [], {}):
        payloads = [value]
    return [
        _artifact_summary(item, stage_id=stage_id, source_key=source_key, index=index)
        for index, item in enumerate(payloads, start=1)
    ]


def _iter_artifact_collection(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        return []
    for key in (
        "artifacts",
        "deliverables",
        "asset_versions",
        "assets",
        "leads",
        "reports",
        "items",
        "records",
    ):
        nested = value.get(key)
        if isinstance(nested, list):
            return nested
    return [value]


def _artifact_summary(
    value: Any,
    *,
    stage_id: str,
    source_key: str,
    index: int,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        artifact_type = _bounded_text(
            value.get("artifact_type")
            or value.get("deliverable_type")
            or value.get("type")
            or source_key,
            80,
        )
        sensitive_source = source_key in _SENSITIVE_ARTIFACT_SOURCE_KEYS
        artifact_id = (
            f"{source_key}:{stage_id}:{index}"
            if sensitive_source
            else _first_text(
                value,
                (
                    "id",
                    "artifact_id",
                    "asset_id",
                    "asset_version_id",
                    "deliverable_id",
                    "report_run_id",
                    "lead_id",
                    "approval_task_id",
                ),
                default=f"{source_key}:{stage_id}:{index}",
                limit=160,
            )
        )
        title = (
            _humanize_slug(source_key)
            if sensitive_source
            else _first_text(
                value,
                ("title", "name", "label", "headline", "subject"),
                default=_humanize_slug(artifact_type or source_key),
                limit=160,
            )
        )
        summary = (
            "Source context captured. Raw message/session data is kept out of the operator projection."
            if sensitive_source
            else _first_text(
                value,
                ("summary", "description", "rationale", "status", "notes", "content"),
                default="",
                limit=500,
            )
        )
        refs = {
            key: value[key]
            for key in (
                "asset_id",
                "asset_version_id",
                "asset_version_ids",
                "deliverable_id",
                "report_run_id",
                "lead_id",
                "approval_task_id",
            )
            if key in value and value[key] not in (None, "", [], {})
        }
    else:
        artifact_type = source_key
        artifact_id = f"{source_key}:{stage_id}:{index}"
        title = _humanize_slug(source_key)
        summary = _safe_summary_text(value, 500)
        refs = {}
    return sanitize_outbox_payload(
        {
            "id": _safe_summary_text(artifact_id, 160),
            "stage_id": stage_id,
            "artifact_type": artifact_type,
            "title": _safe_summary_text(title, 160),
            "summary": _safe_summary_text(summary, 500),
            "source_key": source_key,
            "refs": refs,
            "created_via": WORKFLOW_METADATA_KEY,
        }
    )


def _existing_stage_artifact_summaries(stage: ProgramStageState) -> list[dict[str, Any]]:
    state = dict(stage.state_json or {})
    workflow_metadata = state.get(WORKFLOW_METADATA_KEY)
    if isinstance(workflow_metadata, Mapping):
        summaries = workflow_metadata.get("artifact_summaries")
        if isinstance(summaries, list):
            return _sanitize_workflow_list(summaries)
    summaries = state.get("artifact_summaries")
    if isinstance(summaries, list):
        return _sanitize_workflow_list(summaries)
    return []


def _merge_atlas_outputs(
    existing: Any,
    artifact_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    outputs = (
        [
            item
            for item in existing
            if isinstance(item, dict) and item.get("created_via") != WORKFLOW_METADATA_KEY
        ]
        if isinstance(existing, list)
        else []
    )
    outputs.extend(
        {
            "type": "atlas_retention_artifact",
            "id": summary["id"],
            "artifact_type": summary.get("artifact_type", ""),
            "title": summary.get("title", ""),
            "summary": summary.get("summary", ""),
            "source_key": summary.get("source_key", ""),
            "created_via": WORKFLOW_METADATA_KEY,
        }
        for summary in artifact_summaries
    )
    return _sanitize_workflow_list(outputs)


def _sanitize_workflow_list(value: Any) -> list[dict[str, Any]]:
    payload = sanitize_outbox_payload({"items": value if isinstance(value, list) else []})
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _stage_id_for_artifact(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    stage_id = str(value.get("stage_id") or value.get("stage") or "").strip()
    if stage_id in _STAGE_BY_ID:
        return stage_id
    artifact_type = str(
        value.get("artifact_type") or value.get("deliverable_type") or value.get("type") or ""
    ).strip()
    return _ARTIFACT_STAGE_BY_TYPE.get(artifact_type, "")


def _current_stage_id(stages: list[ProgramStageState]) -> str:
    for stage in sorted(stages, key=lambda item: item.sequence):
        if stage.status != "completed":
            return stage.stage_id
    return ATLAS_RETENTION_STAGES[-1].stage_id


def _program_external_key(whiteboard: WorkWhiteboard) -> str:
    return (f"{TEMPLATE_ID}:company:{whiteboard.company_id}:whiteboard:{whiteboard.id}")[:255]


def _program_title(whiteboard: WorkWhiteboard) -> str:
    base = (
        whiteboard.project_name
        or whiteboard.client_name
        or getattr(whiteboard.company, "name", "")
        or "Client"
    )
    return _bounded_text(f"Atlas retention operator workflow: {base}", 255)


def _program_objective(whiteboard: WorkWhiteboard) -> str:
    objective = whiteboard.objective or whiteboard.request_summary
    if objective:
        return _bounded_text(objective, 2000)
    return "Coordinate Atlas retention intake, launch, proof, and commission follow-up."


def _dedupe_summaries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("source_key") or ""), str(item.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _first_text(
    value: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    default: str,
    limit: int,
) -> str:
    for key in keys:
        text = _safe_summary_text(value.get(key), limit)
        if text:
            return text
    return _safe_summary_text(default, limit)


def _safe_summary_text(value: Any, limit: int) -> str:
    text = _bounded_text(value, limit)
    return _PHONE_LIKE_RE.sub("[REDACTED_PHONE]", text)[:limit]


def _bounded_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _humanize_slug(value: str) -> str:
    words = re.split(r"[_\-\s]+", str(value or "").strip())
    return " ".join(word.capitalize() for word in words if word) or "Atlas Retention"
