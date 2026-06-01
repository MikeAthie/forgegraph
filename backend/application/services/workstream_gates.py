"""Generic whiteboard-scoped workstream phase and gate orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.company_ops import create_company_signal
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.product_operations import contract_operation_metadata
from application.services.rbac import has_min_role
from application.services.routing import register_department, route_event_to_department
from application.services.task_lifecycle import (
    complete_backend_lifecycle_task,
    complete_backend_operation_run,
    create_backend_approval_task,
    get_or_create_backend_lifecycle_task,
    get_or_create_backend_operation_run,
)
from application.services.work_whiteboards import work_status_for_legacy_status
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    AssetVersion,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    DepartmentRegistry,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    GraphVersion,
    Run,
    StateProjection,
    TaskLifecycleRecord,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

PHASE_SCHEMA_VERSION = "workstream_phase_v1"
PHASE_CONFIG_KEY = "workstream_phases"
PHASE_PROJECTION_PREFIX = "workstream_phase"
SUPPORTED_OPERATORS = {">=", ">", "<=", "<", "==", "!=", "in"}
VALID_WHITEBOARD_STATUSES = {choice[0] for choice in WorkWhiteboard.STATUS_CHOICES}
VALID_DEPENDENCY_TYPES = {"hard", "soft", "external", "approval"}
BLOCKING_DEPENDENCY_TYPES = {"hard", "external", "approval"}
TERMINAL_WORKSTREAM_STATUSES = {"completed", "cancelled"}


class WorkstreamGateError(ValueError):
    """Domain error for generic workstream phase orchestration."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_phase_definition(
    *,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a pack-defined phase definition for a single whiteboard."""

    if definition is not None:
        return _normalize_definition(
            sanitize_outbox_payload(definition),
            phase_id=phase_id,
            source_policy_id=str(definition.get("source_policy_id") or "explicit_fixture"),
            pack_id=str(definition.get("pack_id") or "explicit_fixture"),
        )
    for candidate in _phase_definition_candidates(whiteboard):
        if str(candidate.get("phase_id") or "") == phase_id:
            return _normalize_definition(
                sanitize_outbox_payload(candidate),
                phase_id=phase_id,
                source_policy_id=str(
                    candidate.get("source_policy_id") or candidate.get("pack_id") or ""
                ),
                pack_id=str(candidate.get("pack_id") or ""),
            )
    raise WorkstreamGateError(
        "phase_definition_not_found",
        "No active pack-defined phase definition was found for this whiteboard.",
        details=[{"phase_id": phase_id}],
    )


def list_available_phase_definitions(*, whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in _phase_definition_candidates(whiteboard):
        phase_id = str(candidate.get("phase_id") or "")
        if not phase_id or phase_id in seen:
            continue
        try:
            definitions.append(
                _normalize_definition(
                    sanitize_outbox_payload(candidate),
                    phase_id=phase_id,
                    source_policy_id=str(
                        candidate.get("source_policy_id") or candidate.get("pack_id") or ""
                    ),
                    pack_id=str(candidate.get("pack_id") or ""),
                )
            )
            seen.add(phase_id)
        except WorkstreamGateError:
            continue
    for projection in _phase_projections_for_whiteboard(whiteboard):
        state = projection.json_state if isinstance(projection.json_state, dict) else {}
        definition = _dict_or_empty(state.get("definition"))
        phase_id = str(definition.get("phase_id") or state.get("phase_id") or "")
        if phase_id and phase_id not in seen:
            try:
                definitions.append(
                    _normalize_definition(
                        sanitize_outbox_payload(definition),
                        phase_id=phase_id,
                        source_policy_id=str(definition.get("source_policy_id") or ""),
                        pack_id=str(definition.get("pack_id") or ""),
                    )
                )
                seen.add(phase_id)
            except WorkstreamGateError:
                continue
    return definitions


def list_whiteboard_phase_contracts(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None = None,
    include_internal: bool = False,
) -> list[dict[str, Any]]:
    internal = include_internal or _can_manage_phase(user=user, whiteboard=whiteboard)
    contracts: list[dict[str, Any]] = []
    for definition in list_available_phase_definitions(whiteboard=whiteboard):
        contracts.append(
            _phase_contract(
                whiteboard=whiteboard, definition=definition, user=user, include_internal=internal
            )
        )
    return contracts


def get_phase_contract(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not has_company_access(user, whiteboard.company, "viewer"):
        raise WorkstreamGateError(
            "permission_denied", "You do not have access to this whiteboard phase."
        )
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    return _phase_contract(
        whiteboard=whiteboard,
        definition=resolved,
        user=user,
        include_internal=_can_manage_phase(user=user, whiteboard=whiteboard),
    )


def start_phase_for_whiteboard(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a pack-defined phase and create whiteboard-scoped workstreams."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    phase_id = str(resolved["phase_id"])
    existing_projection = _phase_projection(whiteboard=whiteboard, phase_id=phase_id)
    already_started = (
        existing_projection is not None
        or _workstream_records(
            whiteboard=whiteboard,
            phase_id=phase_id,
        ).exists()
    )
    if not already_started:
        _validate_required_status(whiteboard=whiteboard, definition=resolved)
    with transaction.atomic():
        start_status = str(resolved.get("set_status_on_start") or "")
        if (
            not already_started
            and start_status in VALID_WHITEBOARD_STATUSES
            and whiteboard.status != start_status
        ):
            whiteboard.status = start_status
            whiteboard.work_status = work_status_for_legacy_status(start_status)
            whiteboard.save(update_fields=["status", "work_status", "updated_at"])
        create_workstreams_from_definition(user=user, whiteboard=whiteboard, definition=resolved)
        _refresh_phase_dependency_states(whiteboard=whiteboard, definition=resolved)
        existing_state = (
            existing_projection.json_state
            if existing_projection is not None and isinstance(existing_projection.json_state, dict)
            else {}
        )
        _upsert_phase_projection(
            whiteboard=whiteboard,
            definition=resolved,
            state={
                "status": "started",
                "started_at": existing_state.get("started_at") or timezone.now().isoformat(),
                "workstreams": _workstream_state(
                    whiteboard=whiteboard, definition=resolved, include_internal=True
                ),
            },
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return _phase_contract(
        whiteboard=whiteboard, definition=resolved, user=user, include_internal=True
    )


def create_workstreams_from_definition(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
) -> list[TaskRoutingRecord]:
    """Create idempotent workstream records for a whiteboard phase definition."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    phase_id = str(definition["phase_id"])
    records: list[TaskRoutingRecord] = []
    graph_version = _phase_graph_version(company=whiteboard.company, phase_id=phase_id)
    for workstream in _workstreams(definition):
        workstream_id = str(workstream["id"])
        department = _ensure_phase_department(whiteboard=whiteboard, workstream=workstream)
        run = _phase_run(
            user=user,
            whiteboard=whiteboard,
            definition=definition,
            graph_version=graph_version,
            workstream=workstream,
        )
        lifecycle = _phase_lifecycle(
            whiteboard=whiteboard,
            definition=definition,
            run=run,
            department=department,
            workstream=workstream,
        )
        asset, version = _phase_asset_shell(
            whiteboard=whiteboard,
            definition=definition,
            operation=run,
            workstream=workstream,
        )
        dependency_state = _dependency_state_for_workstream(
            whiteboard=whiteboard,
            definition=definition,
            workstream=workstream,
        )
        initial_status = (
            "blocked" if str(dependency_state.get("status") or "") == "blocked" else "queued"
        )
        record = route_event_to_department(
            company=whiteboard.company,
            department=department,
            user=user,
            event_type="whiteboard.phase.workstream.created",
            trigger_type="whiteboard.phase.workstream.created",
            task_lifecycle=lifecycle,
            communication_thread=whiteboard.communication_thread,
            communication_message=whiteboard.source_message,
            service_engagement=whiteboard.service_engagement,
            operation=run,
            reason=str(
                workstream.get("reason")
                or f"Complete workstream: {workstream.get('name') or workstream_id}."
            ),
            status=initial_status,
            priority=str(workstream.get("priority") or "normal"),
            idempotency_key=_phase_key(
                whiteboard=whiteboard, phase_id=phase_id, suffix=f"workstream:{workstream_id}"
            ),
            metadata={
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "source_policy_id": definition.get("source_policy_id"),
                "pack_id": definition.get("pack_id"),
                "workstream_id": workstream_id,
                "workstream_name": workstream.get("name") or _label(workstream_id),
                "output_type": workstream.get("output_type") or "",
                "asset_id": str(asset.id),
                "asset_version_id": str(version.id),
                "run_id": str(run.id),
                "task_lifecycle_id": str(lifecycle.id),
                "dependencies": list(workstream.get("dependencies") or []),
                "dependency_state": dependency_state,
            },
        )
        _sync_workstream_dependency_record(
            record=record,
            workstream=workstream,
            dependency_state=dependency_state,
        )
        records.append(record)
    return records


def list_phase_workstreams(
    *,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
    include_internal: bool = True,
) -> list[dict[str, Any]]:
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    return _workstream_state(
        whiteboard=whiteboard, definition=resolved, include_internal=include_internal
    )


def complete_workstream(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    workstream_id: str,
    result: dict[str, Any] | None = None,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark one whiteboard-scoped phase workstream complete."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    workstream = _workstream_definition(resolved, workstream_id)
    if workstream is None:
        raise WorkstreamGateError(
            "unknown_workstream", "Phase workstream is not defined by the source policy."
        )
    record = _workstream_record(
        whiteboard=whiteboard, phase_id=phase_id, workstream_id=workstream_id
    )
    if record is None:
        raise WorkstreamGateError(
            "workstream_not_found", "Phase workstream has not been started for this whiteboard."
        )
    dependency_state = _dependency_state_for_workstream(
        whiteboard=whiteboard,
        definition=resolved,
        workstream=workstream,
    )
    if str(dependency_state.get("status") or "") == "blocked":
        _sync_workstream_dependency_record(
            record=record,
            workstream=workstream,
            dependency_state=dependency_state,
        )
        raise WorkstreamGateError(
            "workstream_dependencies_blocked",
            "Workstream has unsatisfied blocking dependencies.",
            details=list(dependency_state.get("blockers") or []),
        )
    with transaction.atomic():
        asset = _asset_for_record(record=record, whiteboard=whiteboard)
        if asset is None:
            asset, _version = _phase_asset_shell(
                whiteboard=whiteboard,
                definition=resolved,
                operation=record.operation,
                workstream=workstream,
            )
        version = _create_asset_version(
            asset=asset,
            label="result",
            content={
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "workstream_id": workstream_id,
                "result": sanitize_outbox_payload(result or {}),
            },
            metadata={"phase_id": phase_id, "workstream_id": workstream_id, "status": "completed"},
        )
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "workstream_status": "completed",
            "canonical_asset_version_id": str(version.id),
        }
        asset.save(update_fields=["metadata_json", "updated_at"])
        completed_at = timezone.now()
        record.status = "completed"
        record.metadata_json = {
            **(record.metadata_json or {}),
            "asset_id": str(asset.id),
            "asset_version_id": str(version.id),
            "completed_at": completed_at.isoformat(),
        }
        record.full_clean()
        record.save(update_fields=["status", "metadata_json", "updated_at"])
        if record.task_lifecycle is not None:
            complete_backend_lifecycle_task(
                lifecycle_task=record.task_lifecycle,
                ended_at=completed_at,
            )
        if record.operation is not None:
            complete_backend_operation_run(
                run=record.operation,
                ended_at=completed_at,
                output_json={
                    "whiteboard_id": str(whiteboard.id),
                    "phase_id": phase_id,
                    "workstream_id": workstream_id,
                    "asset_version_id": str(version.id),
                },
            )
        _refresh_phase_dependency_states(whiteboard=whiteboard, definition=resolved)
        _upsert_phase_projection(
            whiteboard=whiteboard,
            definition=resolved,
            state={
                "status": "in_progress",
                "workstreams": _workstream_state(
                    whiteboard=whiteboard, definition=resolved, include_internal=True
                ),
            },
        )
    _refresh_whiteboard_snapshot(whiteboard)
    refreshed = _workstream_record(
        whiteboard=whiteboard, phase_id=phase_id, workstream_id=workstream_id
    )
    if refreshed is None:
        raise WorkstreamGateError(
            "workstream_not_found", "Completed workstream could not be reloaded."
        )
    return _workstream_payload(refreshed, include_internal=True)


def synthesize_phase_outputs(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
) -> tuple[Asset, AssetVersion]:
    """Create a whiteboard-scoped synthesis artifact from completed required workstreams."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    incomplete = [
        item
        for item in _workstream_state(
            whiteboard=whiteboard, definition=resolved, include_internal=True
        )
        if item.get("required") and item.get("status") != "completed"
    ]
    if incomplete:
        raise WorkstreamGateError(
            "workstreams_incomplete",
            "Phase synthesis requires all required workstreams to be completed.",
            details=[
                {"workstream_id": item.get("id"), "status": item.get("status")}
                for item in incomplete
            ],
        )
    with transaction.atomic():
        asset = _get_or_create_asset(
            company=whiteboard.company,
            title=f"{resolved['phase_name']} synthesis",
            source_key=_phase_key(whiteboard=whiteboard, phase_id=phase_id, suffix="synthesis"),
            origin_operation=None,
            metadata={
                "artifact_type": "phase_synthesis",
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "source_policy_id": resolved.get("source_policy_id"),
                "pack_id": resolved.get("pack_id"),
            },
        )
        content = _synthesis_content(whiteboard=whiteboard, definition=resolved)
        version = _create_asset_version(
            asset=asset,
            label="synthesis",
            content=content,
            metadata={
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "artifact_type": "phase_synthesis",
            },
        )
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "canonical_asset_version_id": str(version.id),
            "phase_synthesis_version_id": str(version.id),
        }
        asset.save(update_fields=["metadata_json", "updated_at"])
        _upsert_phase_projection(
            whiteboard=whiteboard,
            definition=resolved,
            state={
                "status": "synthesized",
                "synthesis": {
                    "asset_id": str(asset.id),
                    "asset_version_id": str(version.id),
                    "created_at": version.created_at.isoformat(),
                },
                "workstreams": _workstream_state(
                    whiteboard=whiteboard, definition=resolved, include_internal=True
                ),
            },
            source_refs=[{"asset_id": str(asset.id), "asset_version_id": str(version.id)}],
            summary="Phase synthesis generated from completed workstreams.",
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return asset, version


def evaluate_gate(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    scorecard: dict[str, Any] | None = None,
    definition: dict[str, Any] | None = None,
) -> EvaluationRun:
    """Evaluate a pack-defined gate without hardcoding criterion names."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    gate = _gate(resolved)
    if not gate:
        raise WorkstreamGateError("gate_not_defined", "Phase definition does not define a gate.")
    synthesis = _synthesis_asset(whiteboard=whiteboard, phase_id=phase_id)
    if synthesis is None:
        raise WorkstreamGateError(
            "synthesis_required", "Gate evaluation requires a phase synthesis artifact."
        )
    asset, version = synthesis
    submitted = sanitize_outbox_payload(scorecard or {})
    criteria_results = [_criterion_result(criterion, submitted) for criterion in _criteria(gate)]
    gate_result = _gate_result(criteria_results)
    composite_score = _composite_score(criteria_results)
    with transaction.atomic():
        evaluation = EvaluationRun.objects.create(
            organization=whiteboard.organization,
            company=whiteboard.company,
            operation=_gate_run(user=user, whiteboard=whiteboard, definition=resolved),
            asset=asset,
            asset_version=version,
            profile_key=str(gate.get("gate_id") or phase_id)[:160],
            status="PASS" if gate_result == "pass" else "BLOCK",
            score=composite_score,
            grade=_grade(composite_score),
            input_refs_json=[
                {"asset_id": str(asset.id), "asset_version_id": str(version.id)},
                {"whiteboard_id": str(whiteboard.id), "phase_id": phase_id},
            ],
            result_json=sanitize_outbox_payload(
                {
                    "schema_version": PHASE_SCHEMA_VERSION,
                    "whiteboard_id": str(whiteboard.id),
                    "phase_id": phase_id,
                    "source_policy_id": resolved.get("source_policy_id"),
                    "pack_id": resolved.get("pack_id"),
                    "gate_id": gate.get("gate_id"),
                    "gate_result": gate_result,
                    "criteria_results": criteria_results,
                    "submitted_scorecard": submitted,
                }
            ),
            created_by=user,
            evaluated_at=timezone.now(),
        )
        EvaluationScorecard.objects.create(
            evaluation=evaluation,
            organization=whiteboard.organization,
            company=whiteboard.company,
            dimensions_json=sanitize_outbox_payload(
                {"criteria": criteria_results, "submitted_scorecard": submitted}
            ),
            composite_score=composite_score,
            grade=_grade(composite_score),
        )
        _upsert_phase_projection(
            whiteboard=whiteboard,
            definition=resolved,
            state={
                "status": "evaluated",
                "gate": _gate_payload(evaluation=evaluation, include_internal=True),
                "workstreams": _workstream_state(
                    whiteboard=whiteboard, definition=resolved, include_internal=True
                ),
                "synthesis": _synthesis_payload(whiteboard=whiteboard, phase_id=phase_id),
            },
        )
        apply_gate_result(
            user=user,
            whiteboard=whiteboard,
            phase_id=phase_id,
            evaluation=evaluation,
            definition=resolved,
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return evaluation


def apply_gate_result(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    evaluation: EvaluationRun,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply generic gate pass/fail actions from the policy definition."""

    _ensure_can_manage_phase(user=user, whiteboard=whiteboard)
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    result = _result_json(evaluation).get("gate_result")
    gate = _gate(resolved)
    action = (
        dict(gate.get("on_pass") or {}) if result == "pass" else dict(gate.get("on_fail") or {})
    )
    artifacts: dict[str, Any] = {}
    status = str(action.get("set_whiteboard_status") or "")
    if status in VALID_WHITEBOARD_STATUSES and whiteboard.status != status:
        whiteboard.status = status
        whiteboard.work_status = work_status_for_legacy_status(status)
        whiteboard.save(update_fields=["status", "work_status", "updated_at"])
    route_slug = str(action.get("route_to_department") or action.get("route_to") or "").strip()
    if route_slug:
        routing_record = _route_gate_outcome(
            user=user,
            whiteboard=whiteboard,
            definition=resolved,
            evaluation=evaluation,
            department_slug=route_slug,
            result=str(result or "unknown"),
        )
        artifacts["routing_record_id"] = str(routing_record.id)
    if result == "pass" and bool(action.get("approval_required") or gate.get("approval_required")):
        approval = _approval_for_gate(
            user=user, whiteboard=whiteboard, definition=resolved, evaluation=evaluation
        )
        artifacts["approval_task_id"] = str(approval.id)
    if result != "pass" and bool(action.get("create_signal") or gate.get("signal_on_fail")):
        signal = _gate_failure_signal(
            user=user, whiteboard=whiteboard, definition=resolved, evaluation=evaluation
        )
        artifacts["company_signal_id"] = str(signal.id)
    _upsert_phase_projection(
        whiteboard=whiteboard,
        definition=resolved,
        state={
            "status": "passed" if result == "pass" else "revision_required",
            "gate": _gate_payload(evaluation=evaluation, include_internal=True),
            "applied_actions": artifacts,
            "workstreams": _workstream_state(
                whiteboard=whiteboard, definition=resolved, include_internal=True
            ),
            "synthesis": _synthesis_payload(whiteboard=whiteboard, phase_id=phase_id),
        },
    )
    _refresh_whiteboard_snapshot(whiteboard)
    return artifacts


def phase_state_payload(
    *,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    definition: dict[str, Any] | None = None,
    include_internal: bool = True,
) -> dict[str, Any]:
    resolved = load_phase_definition(
        whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    return _current_state(
        whiteboard=whiteboard, definition=resolved, include_internal=include_internal
    )


def _phase_contract(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    user: User | None,
    include_internal: bool,
) -> dict[str, Any]:
    manage = _can_manage_phase(user=user, whiteboard=whiteboard)
    phase_id = str(definition["phase_id"])
    operation_state = contract_operation_metadata(
        whiteboard=whiteboard,
        target_type="phase_contract",
        target_id=phase_id,
    )
    current_state = _current_state(
        whiteboard=whiteboard, definition=definition, include_internal=include_internal
    )
    current_state.update(operation_state)
    contract = {
        "whiteboard_id": str(whiteboard.id),
        "phase_id": phase_id,
        "source_policy_id": str(definition.get("source_policy_id") or ""),
        "pack_id": str(definition.get("pack_id") or ""),
        "phase_name": str(definition.get("phase_name") or _label(phase_id)),
        "workstreams": _workstream_state(
            whiteboard=whiteboard, definition=definition, include_internal=include_internal
        ),
        "gate": _definition_gate_payload(
            definition=definition, whiteboard=whiteboard, include_internal=include_internal
        ),
        "current_state": current_state,
        "allowed_actions": _allowed_actions(whiteboard=whiteboard, definition=definition)
        if manage
        else [],
        **operation_state,
    }
    return sanitize_outbox_payload(contract)


def _normalize_definition(
    definition: dict[str, Any],
    *,
    phase_id: str,
    source_policy_id: str,
    pack_id: str,
) -> dict[str, Any]:
    if str(definition.get("phase_id") or "") != phase_id:
        raise WorkstreamGateError(
            "phase_id_mismatch", "Phase definition does not match the requested phase."
        )
    workstreams = list(definition.get("workstreams") or [])
    if not workstreams:
        raise WorkstreamGateError(
            "workstreams_required", "Phase definition must include at least one workstream."
        )
    normalized_workstreams = [_normalize_workstream(item) for item in workstreams]
    gate = _dict_or_empty(definition.get("gate"))
    return {
        "phase_id": phase_id,
        "source_policy_id": str(definition.get("source_policy_id") or source_policy_id or phase_id),
        "pack_id": str(definition.get("pack_id") or pack_id or ""),
        "phase_name": str(
            definition.get("phase_name") or definition.get("name") or _label(phase_id)
        )[:160],
        "whiteboard_required_status": definition.get("whiteboard_required_status") or "",
        "set_status_on_start": str(definition.get("set_status_on_start") or ""),
        "workstreams": normalized_workstreams,
        "gate": _normalize_gate(gate),
        "metadata": sanitize_outbox_payload(definition.get("metadata") or {}),
    }


def _normalize_workstream(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {"id": str(value)}
    workstream_id = str(item.get("id") or "").strip()
    if not workstream_id:
        raise WorkstreamGateError("workstream_id_required", "Every workstream requires an id.")
    return {
        "id": workstream_id[:120],
        "name": str(item.get("name") or _label(workstream_id))[:160],
        "department": str(item.get("department") or item.get("department_slug") or "operations")[
            :160
        ],
        "department_name": str(
            item.get("department_name") or _label(str(item.get("department") or "operations"))
        )[:255],
        "department_type": str(
            item.get("department_type") or item.get("department") or "operations"
        )[:64],
        "output_type": str(item.get("output_type") or "")[:80],
        "required": bool(item.get("required", True)),
        "dependencies": _normalize_dependencies(item.get("dependencies") or []),
        "metadata": sanitize_outbox_payload(item.get("metadata") or {}),
    }


def _normalize_dependencies(value: Any) -> list[dict[str, Any]]:
    raw_values = value if isinstance(value, list) else [value]
    dependencies: list[dict[str, Any]] = []
    for raw in raw_values:
        dependency = _normalize_dependency(raw)
        if dependency is not None:
            dependencies.append(dependency)
    return dependencies


def _normalize_dependency(value: Any) -> dict[str, Any] | None:
    item = value if isinstance(value, dict) else {"workstream_id": str(value)}
    dependency_type = str(item.get("type") or "hard").strip().lower()
    if dependency_type not in VALID_DEPENDENCY_TYPES:
        dependency_type = "hard"
    workstream_id = str(
        item.get("workstream_id") or item.get("workstream") or item.get("id") or ""
    ).strip()
    if not workstream_id and dependency_type not in {"external", "approval"}:
        return None
    default_status = "approved" if dependency_type == "approval" else "completed"
    dependency: dict[str, Any] = {
        "workstream_id": workstream_id[:120],
        "type": dependency_type,
        "required_status": str(item.get("required_status") or default_status)[:32],
    }
    for key in ("label", "reason", "evidence_key", "approval_task_id"):
        if item.get(key):
            dependency[key] = str(item.get(key))[:255]
    return sanitize_outbox_payload(dependency)


def _normalize_gate(gate: dict[str, Any]) -> dict[str, Any]:
    criteria = []
    for criterion in list(gate.get("criteria") or []):
        if not isinstance(criterion, dict):
            continue
        key = str(criterion.get("key") or "").strip()
        operator = str(criterion.get("operator") or "==").strip()
        if not key or operator not in SUPPORTED_OPERATORS:
            continue
        criteria.append(
            {
                "key": key[:160],
                "value_type": str(criterion.get("value_type") or criterion.get("type") or "number")[
                    :24
                ],
                "operator": operator,
                "threshold": criterion.get("threshold"),
                "expected": criterion.get("expected"),
                "required": bool(criterion.get("required", True)),
                "hard_fail": bool(criterion.get("hard_fail", False)),
                "label": str(criterion.get("label") or _label(key))[:160],
            }
        )
    return {
        "gate_id": str(gate.get("gate_id") or gate.get("id") or "")[:160],
        "criteria": criteria,
        "pass_condition": str(gate.get("pass_condition") or "all_required")[:80],
        "approval_required": bool(gate.get("approval_required", False)),
        "signal_on_fail": bool(gate.get("signal_on_fail", False)),
        "on_pass": sanitize_outbox_payload(gate.get("on_pass") or {}),
        "on_fail": sanitize_outbox_payload(gate.get("on_fail") or {}),
    }


def _phase_definition_candidates(whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    program = _program_for_whiteboard(whiteboard)
    if program is not None and program.installation_id:
        candidates.extend(_definitions_from_installation(program.installation))
    installations = CompanyOperatingModelInstallation.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        status="active",
    ).select_related("pack_release")
    for installation in installations:
        candidates.extend(_definitions_from_installation(installation))
    return candidates


def _program_for_whiteboard(whiteboard: WorkWhiteboard) -> CompanyProgram | None:
    metadata = whiteboard.metadata_json if isinstance(whiteboard.metadata_json, dict) else {}
    candidates = [
        metadata.get("company_program_id"),
        metadata.get("program_id"),
    ]
    if whiteboard.service_engagement is not None:
        svc_metadata = (
            whiteboard.service_engagement.metadata_json
            if isinstance(whiteboard.service_engagement.metadata_json, dict)
            else {}
        )
        candidates.extend([svc_metadata.get("company_program_id"), svc_metadata.get("program_id")])
    for program_id in candidates:
        if not program_id:
            continue
        program = (
            CompanyProgram.objects.filter(
                organization=whiteboard.organization,
                company=whiteboard.company,
                id=program_id,
            )
            .select_related("installation", "installation__pack_release")
            .first()
        )
        if program is not None:
            return program
    return None


def _definitions_from_installation(
    installation: CompanyOperatingModelInstallation | None,
) -> list[dict[str, Any]]:
    if installation is None:
        return []
    sources = [
        installation.public_config_json or {},
        installation.config_json or {},
        installation.pack_release.manifest_json if installation.pack_release_id else {},
        installation.pack_release.files_json if installation.pack_release_id else {},
    ]
    definitions: list[dict[str, Any]] = []
    for source in sources:
        definitions.extend(_extract_definitions(source, pack_id=installation.pack_id))
    return definitions


def _extract_definitions(source: Any, *, pack_id: str) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        return []
    definitions: list[dict[str, Any]] = []
    for config in _nested_config_sources(source):
        raw = config.get(PHASE_CONFIG_KEY) or config.get("phases")
        if isinstance(raw, dict):
            if PHASE_CONFIG_KEY in raw:
                raw = raw.get(PHASE_CONFIG_KEY)
            else:
                raw = list(raw.values())
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            definitions.append(
                {
                    **item,
                    "pack_id": str(item.get("pack_id") or pack_id),
                    "source_policy_id": str(
                        item.get("source_policy_id") or f"{pack_id}:{item.get('phase_id', '')}"
                    ),
                }
            )
    return definitions


def _nested_config_sources(source: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [source]
    for value in source.values():
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _ensure_can_manage_phase(*, user: User, whiteboard: WorkWhiteboard) -> None:
    if not _can_manage_phase(user=user, whiteboard=whiteboard):
        raise WorkstreamGateError(
            "permission_denied",
            "Managing this whiteboard phase requires company member access and organization member role.",
        )


def _can_manage_phase(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _validate_required_status(*, whiteboard: WorkWhiteboard, definition: dict[str, Any]) -> None:
    required = definition.get("whiteboard_required_status")
    if not required:
        return
    statuses = set(required if isinstance(required, list) else [required])
    if whiteboard.status not in statuses:
        raise WorkstreamGateError(
            "whiteboard_status_mismatch",
            "Whiteboard status does not satisfy this phase definition.",
            details=[
                {"status": whiteboard.status, "required": sorted(str(item) for item in statuses)}
            ],
        )


def _workstreams(definition: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(definition.get("workstreams") or []) if isinstance(item, dict)]


def _gate(definition: dict[str, Any]) -> dict[str, Any]:
    return _dict_or_empty(definition.get("gate"))


def _criteria(gate: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(gate.get("criteria") or []) if isinstance(item, dict)]


def _workstream_definition(definition: dict[str, Any], workstream_id: str) -> dict[str, Any] | None:
    for item in _workstreams(definition):
        if str(item.get("id") or "") == workstream_id:
            return item
    return None


def _ensure_phase_department(
    *, whiteboard: WorkWhiteboard, workstream: dict[str, Any]
) -> DepartmentRegistry:
    slug = str(workstream.get("department") or "operations").strip()
    return register_department(
        organization=whiteboard.organization,
        slug=slug,
        name=str(workstream.get("department_name") or _label(slug)),
        department_type=str(workstream.get("department_type") or slug),
        service_tags=["workstream_phase"],
        metadata={"system_managed": True, "source": "workstream_gates"},
    )


def _phase_graph_version(*, company: Graph, phase_id: str) -> GraphVersion:
    key = f"workstream-phase:{phase_id}"[:255]
    existing = cast(
        GraphVersion | None,
        GraphVersion.objects.filter(graph=company, external_idempotency_key=key).first(),
    )
    if existing is not None:
        return existing
    version = (
        GraphVersion.objects.filter(graph=company).aggregate(max_version=Max("version"))[
            "max_version"
        ]
        or 0
    ) + 1
    try:
        return cast(
            GraphVersion,
            GraphVersion.objects.create(
                graph=company,
                version=version,
                external_idempotency_key=key,
                graph_json={
                    "nodes": [],
                    "edges": [],
                    "source": "workstream_gates",
                    "phase_id": phase_id,
                },
            ),
        )
    except IntegrityError:
        existing = cast(
            GraphVersion | None,
            GraphVersion.objects.filter(graph=company, external_idempotency_key=key).first(),
        )
        if existing is not None:
            return existing
        raise


def _phase_run(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    graph_version: GraphVersion,
    workstream: dict[str, Any],
) -> Run:
    phase_id = str(definition["phase_id"])
    workstream_id = str(workstream["id"])
    key = _phase_key(whiteboard=whiteboard, phase_id=phase_id, suffix=f"run:{workstream_id}")
    return get_or_create_backend_operation_run(
        owner=user,
        organization=whiteboard.organization,
        thread_id=whiteboard.communication_thread_id,
        graph_version=graph_version,
        idempotency_key=key,
        status="pending",
        input_json={
            "idempotency_key": key,
            "whiteboard_id": str(whiteboard.id),
            "phase_id": phase_id,
            "source_policy_id": definition.get("source_policy_id"),
            "pack_id": definition.get("pack_id"),
            "workstream_id": workstream_id,
            "workstream_name": workstream.get("name"),
        },
        dispatch_graph_json=graph_version.graph_json,
    )


def _gate_run(*, user: User, whiteboard: WorkWhiteboard, definition: dict[str, Any]) -> Run:
    phase_id = str(definition["phase_id"])
    gate_id = str(_gate(definition).get("gate_id") or phase_id)
    graph_version = _phase_graph_version(company=whiteboard.company, phase_id=phase_id)
    key = _phase_key(whiteboard=whiteboard, phase_id=phase_id, suffix=f"gate-run:{gate_id}")
    return get_or_create_backend_operation_run(
        owner=user,
        organization=whiteboard.organization,
        thread_id=whiteboard.communication_thread_id,
        graph_version=graph_version,
        idempotency_key=key,
        status="succeeded",
        input_json={
            "idempotency_key": key,
            "whiteboard_id": str(whiteboard.id),
            "phase_id": phase_id,
            "gate_id": gate_id,
        },
        output_json={"whiteboard_id": str(whiteboard.id), "phase_id": phase_id, "gate_id": gate_id},
        dispatch_graph_json=graph_version.graph_json,
        ended_at=timezone.now(),
    )


def _phase_lifecycle(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    run: Run,
    department: DepartmentRegistry,
    workstream: dict[str, Any],
) -> TaskLifecycleRecord:
    phase_id = str(definition["phase_id"])
    workstream_id = str(workstream["id"])
    return get_or_create_backend_lifecycle_task(
        organization=whiteboard.organization,
        external_key=_phase_key(
            whiteboard=whiteboard, phase_id=phase_id, suffix=f"lifecycle:{workstream_id}"
        ),
        run=run,
        source_node_id=workstream_id,
        node_type="workstream_phase",
        title=str(workstream.get("name") or _label(workstream_id))[:255],
        status="queued",
        priority="normal",
        summary=f"Workstream for phase {definition['phase_name']}.",
        current_department=department,
        last_transition_at=timezone.now(),
    )


def _phase_asset_shell(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    operation: Run | None,
    workstream: dict[str, Any],
) -> tuple[Asset, AssetVersion]:
    phase_id = str(definition["phase_id"])
    workstream_id = str(workstream["id"])
    asset = _get_or_create_asset(
        company=whiteboard.company,
        title=f"{definition['phase_name']}: {workstream.get('name') or _label(workstream_id)}",
        source_key=_phase_key(
            whiteboard=whiteboard, phase_id=phase_id, suffix=f"workstream:{workstream_id}"
        ),
        origin_operation=operation,
        metadata={
            "artifact_type": "phase_workstream",
            "whiteboard_id": str(whiteboard.id),
            "phase_id": phase_id,
            "workstream_id": workstream_id,
            "output_type": workstream.get("output_type") or "",
            "workstream_status": "queued",
        },
    )
    version = AssetVersion.objects.filter(asset=asset).order_by("version_number").first()
    if version is None:
        version = _create_asset_version(
            asset=asset,
            label="shell",
            content={
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "workstream_id": workstream_id,
                "status": "queued",
            },
            metadata={"phase_id": phase_id, "workstream_id": workstream_id, "status": "queued"},
        )
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "canonical_asset_version_id": str(version.id),
        }
        asset.save(update_fields=["metadata_json", "updated_at"])
    return asset, version


def _get_or_create_asset(
    *,
    company: Graph,
    title: str,
    source_key: str,
    origin_operation: Run | None,
    metadata: dict[str, Any],
) -> Asset:
    asset, _created = Asset.objects.get_or_create(
        company=company,
        source_key=source_key,
        defaults={
            "organization": company.organization,
            "title": title[:255],
            "asset_type": "memo",
            "origin_operation": origin_operation,
            "created_by_type": "system",
            "metadata_json": sanitize_outbox_payload(metadata),
        },
    )
    return asset


def _create_asset_version(
    *,
    asset: Asset,
    label: str,
    content: dict[str, Any],
    metadata: dict[str, Any],
) -> AssetVersion:
    payload = sanitize_outbox_payload(content)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    existing = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if existing is not None:
        return existing
    version_number = (
        AssetVersion.objects.filter(asset=asset).aggregate(max_version=Max("version_number"))[
            "max_version"
        ]
        or 0
    ) + 1
    return AssetVersion.objects.create(
        asset=asset,
        version_number=version_number,
        content_uri=f"forgegraph://assets/{asset.id}/phase/{version_number}",
        content_hash=digest,
        mime_type="application/json",
        size_bytes=len(encoded),
        provenance_json={
            "source": "workstream_gates",
            "label": label,
            "inline_content": payload,
            "metadata": sanitize_outbox_payload(metadata),
        },
    )


def _workstream_records(
    *, whiteboard: WorkWhiteboard, phase_id: str
) -> QuerySet[TaskRoutingRecord]:
    return (
        TaskRoutingRecord.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            metadata_json__whiteboard_id=str(whiteboard.id),
            metadata_json__phase_id=phase_id,
            metadata_json__workstream_id__isnull=False,
        )
        .select_related("to_department", "operation", "task_lifecycle")
        .order_by("created_at")
    )


def _workstream_record(
    *,
    whiteboard: WorkWhiteboard,
    phase_id: str,
    workstream_id: str,
) -> TaskRoutingRecord | None:
    return (
        _workstream_records(whiteboard=whiteboard, phase_id=phase_id)
        .filter(
            metadata_json__workstream_id=workstream_id,
        )
        .first()
    )


def _dependency_state_for_workstream(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    workstream: dict[str, Any],
) -> dict[str, Any]:
    dependencies = [
        item for item in list(workstream.get("dependencies") or []) if isinstance(item, dict)
    ]
    if not dependencies:
        return {
            "status": "ready",
            "dependencies": [],
            "blockers": [],
            "provisional": [],
            "blocker_reason": "",
        }
    phase_id = str(definition["phase_id"])
    records = {
        str((record.metadata_json or {}).get("workstream_id") or ""): record
        for record in _workstream_records(whiteboard=whiteboard, phase_id=phase_id)
    }
    dependency_items = [
        _dependency_status_item(whiteboard=whiteboard, records=records, dependency=dependency)
        for dependency in dependencies
    ]
    blockers = [
        item
        for item in dependency_items
        if not bool(item.get("satisfied"))
        and str(item.get("type") or "") in BLOCKING_DEPENDENCY_TYPES
    ]
    provisional = [
        item
        for item in dependency_items
        if not bool(item.get("satisfied")) and str(item.get("type") or "") == "soft"
    ]
    status = "blocked" if blockers else "provisional" if provisional else "ready"
    blocker_reason = _dependency_blocker_reason(blockers)
    return sanitize_outbox_payload(
        {
            "status": status,
            "dependencies": dependency_items,
            "blockers": blockers,
            "provisional": provisional,
            "blocker_reason": blocker_reason,
        }
    )


def _dependency_status_item(
    *,
    whiteboard: WorkWhiteboard,
    records: dict[str, TaskRoutingRecord],
    dependency: dict[str, Any],
) -> dict[str, Any]:
    dependency_type = str(dependency.get("type") or "hard")
    required_status = str(
        dependency.get("required_status")
        or ("approved" if dependency_type == "approval" else "completed")
    )
    workstream_id = str(dependency.get("workstream_id") or "")
    current_status = "not_started"
    source_ref = workstream_id
    if dependency_type == "approval":
        current_status = _approval_dependency_status(whiteboard=whiteboard, dependency=dependency)
        source_ref = str(dependency.get("approval_task_id") or workstream_id or "approval")
    elif dependency_type == "external" and not workstream_id:
        current_status = _external_dependency_status(whiteboard=whiteboard, dependency=dependency)
        source_ref = str(dependency.get("evidence_key") or "external")
    else:
        record = records.get(workstream_id)
        current_status = record.status if record is not None else "not_started"
    return sanitize_outbox_payload(
        {
            "workstream_id": workstream_id,
            "type": dependency_type,
            "required_status": required_status,
            "current_status": current_status,
            "satisfied": _dependency_status_satisfied(
                current_status=current_status, required_status=required_status
            ),
            "source_ref": source_ref,
            "label": str(dependency.get("label") or _label(source_ref or dependency_type)),
        }
    )


def _dependency_status_satisfied(*, current_status: str, required_status: str) -> bool:
    if required_status == "started":
        return current_status not in {"not_started", "blocked"}
    return current_status == required_status


def _approval_dependency_status(*, whiteboard: WorkWhiteboard, dependency: dict[str, Any]) -> str:
    approval_task_id = str(dependency.get("approval_task_id") or "").strip()
    queryset = ApprovalTask.objects.filter(
        run__organization=whiteboard.organization,
        run__graph_version__graph=whiteboard.company,
        payload__whiteboard_id=str(whiteboard.id),
    )
    if approval_task_id:
        queryset = queryset.filter(id=approval_task_id)
    approval = queryset.order_by("-created_at").first()
    return str(approval.status) if approval is not None else "not_started"


def _external_dependency_status(*, whiteboard: WorkWhiteboard, dependency: dict[str, Any]) -> str:
    evidence_key = str(dependency.get("evidence_key") or "").strip()
    if not evidence_key:
        return "blocked"
    required_status = str(dependency.get("required_status") or "completed")
    asset_queryset = Asset.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        metadata_json__whiteboard_id=str(whiteboard.id),
        metadata_json__evidence_key=evidence_key,
    )
    if asset_queryset.filter(metadata_json__status=required_status).exists():
        return required_status
    if asset_queryset.filter(metadata_json__evidence_status=required_status).exists():
        return required_status
    record = (
        TaskRoutingRecord.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            metadata_json__whiteboard_id=str(whiteboard.id),
            metadata_json__evidence_key=evidence_key,
        )
        .order_by("-created_at")
        .first()
    )
    return str(record.status) if record is not None else "not_started"


def _dependency_blocker_reason(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return ""
    labels = [str(item.get("label") or item.get("source_ref") or "dependency") for item in blockers]
    if len(labels) == 1:
        return f"Waiting for {labels[0]}."
    return f"Waiting for {len(labels)} dependencies: {', '.join(labels[:3])}."


def _sync_workstream_dependency_record(
    *,
    record: TaskRoutingRecord,
    workstream: dict[str, Any],
    dependency_state: dict[str, Any],
) -> None:
    metadata = dict(record.metadata_json or {})
    previous_state = _dict_or_empty(metadata.get("dependency_state"))
    was_dependency_blocked = (
        str(previous_state.get("status") or "") == "blocked"
        or metadata.get("blocked_reason_code") == "workstream_dependency_blocked"
    )
    dependency_status = str(dependency_state.get("status") or "ready")
    metadata["dependencies"] = list(workstream.get("dependencies") or [])
    metadata["dependency_state"] = sanitize_outbox_payload(dependency_state)
    metadata["dependency_status"] = dependency_status
    metadata["provisional"] = dependency_status == "provisional"
    resolution = dict(record.resolution_json or {})
    next_status = record.status
    if dependency_status == "blocked":
        reason = str(dependency_state.get("blocker_reason") or "Workstream dependency blocked.")
        metadata["blocker_reason"] = reason
        metadata["blocked_reason_code"] = "workstream_dependency_blocked"
        resolution["blocker_reason"] = reason
        resolution["reason_code"] = "workstream_dependency_blocked"
        resolution["dependency_state"] = sanitize_outbox_payload(dependency_state)
        if record.status not in TERMINAL_WORKSTREAM_STATUSES:
            next_status = "blocked"
    else:
        if metadata.get("blocked_reason_code") == "workstream_dependency_blocked":
            metadata.pop("blocker_reason", None)
            metadata.pop("blocked_reason_code", None)
        if resolution.get("reason_code") == "workstream_dependency_blocked":
            resolution.pop("blocker_reason", None)
            resolution.pop("reason_code", None)
        resolution["dependency_state"] = sanitize_outbox_payload(dependency_state)
        if record.status == "blocked" and was_dependency_blocked:
            next_status = "queued"
    changed = (
        record.status != next_status
        or record.metadata_json != metadata
        or record.resolution_json != resolution
    )
    if not changed:
        return
    record.status = next_status
    record.metadata_json = sanitize_outbox_payload(metadata)
    record.resolution_json = sanitize_outbox_payload(resolution)
    record.full_clean()
    record.save(update_fields=["status", "metadata_json", "resolution_json", "updated_at"])


def _refresh_phase_dependency_states(
    *, whiteboard: WorkWhiteboard, definition: dict[str, Any]
) -> None:
    phase_id = str(definition["phase_id"])
    for workstream in _workstreams(definition):
        record = _workstream_record(
            whiteboard=whiteboard,
            phase_id=phase_id,
            workstream_id=str(workstream["id"]),
        )
        if record is None:
            continue
        dependency_state = _dependency_state_for_workstream(
            whiteboard=whiteboard,
            definition=definition,
            workstream=workstream,
        )
        _sync_workstream_dependency_record(
            record=record,
            workstream=workstream,
            dependency_state=dependency_state,
        )


def _workstream_state(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    include_internal: bool,
) -> list[dict[str, Any]]:
    phase_id = str(definition["phase_id"])
    records = {
        str((record.metadata_json or {}).get("workstream_id") or ""): record
        for record in _workstream_records(whiteboard=whiteboard, phase_id=phase_id)
    }
    payload: list[dict[str, Any]] = []
    for workstream in _workstreams(definition):
        workstream_id = str(workstream["id"])
        record = records.get(workstream_id)
        if record is None:
            item = {
                "id": workstream_id,
                "name": str(workstream.get("name") or _label(workstream_id)),
                "status": "not_started",
                "required": bool(workstream.get("required", True)),
                "output_type": str(workstream.get("output_type") or ""),
            }
        else:
            item = _workstream_payload(record, include_internal=include_internal)
            item["name"] = str(workstream.get("name") or item.get("name") or _label(workstream_id))
            item["required"] = bool(workstream.get("required", True))
            item["output_type"] = str(
                workstream.get("output_type") or item.get("output_type") or ""
            )
        if include_internal:
            item["dependencies"] = list(workstream.get("dependencies") or [])
            item["dependency_state"] = _dependency_state_for_workstream(
                whiteboard=whiteboard,
                definition=definition,
                workstream=workstream,
            )
            item["metadata"] = sanitize_outbox_payload(workstream.get("metadata") or {})
        payload.append(item)
    return payload


def _workstream_payload(record: TaskRoutingRecord, *, include_internal: bool) -> dict[str, Any]:
    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    payload = {
        "id": str(metadata.get("workstream_id") or record.id),
        "routing_record_id": str(record.id) if include_internal else "",
        "name": str(
            metadata.get("workstream_name") or _label(str(metadata.get("workstream_id") or ""))
        ),
        "status": record.status,
        "required": True,
        "output_type": str(metadata.get("output_type") or ""),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    if include_internal:
        payload.update(
            {
                "department_id": str(record.to_department_id),
                "department_name": record.to_department.name,
                "run_id": str(record.operation_id)
                if record.operation_id
                else str(metadata.get("run_id") or ""),
                "task_lifecycle_id": str(record.task_lifecycle_id)
                if record.task_lifecycle_id
                else str(metadata.get("task_lifecycle_id") or ""),
                "asset_id": str(metadata.get("asset_id") or ""),
                "asset_version_id": str(metadata.get("asset_version_id") or ""),
                "reason": record.reason,
            }
        )
    return payload


def _asset_for_record(*, record: TaskRoutingRecord, whiteboard: WorkWhiteboard) -> Asset | None:
    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    asset_id = str(metadata.get("asset_id") or "").strip()
    if not asset_id:
        return None
    return Asset.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        id=asset_id,
        metadata_json__whiteboard_id=str(whiteboard.id),
    ).first()


def _synthesis_content(*, whiteboard: WorkWhiteboard, definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "whiteboard_id": str(whiteboard.id),
        "phase_id": definition["phase_id"],
        "source_policy_id": definition.get("source_policy_id"),
        "pack_id": definition.get("pack_id"),
        "request_summary": whiteboard.request_summary,
        "objective": whiteboard.objective,
        "workstreams": _workstream_state(
            whiteboard=whiteboard, definition=definition, include_internal=True
        ),
    }


def _synthesis_asset(
    *, whiteboard: WorkWhiteboard, phase_id: str
) -> tuple[Asset, AssetVersion] | None:
    asset = Asset.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        source_key=_phase_key(whiteboard=whiteboard, phase_id=phase_id, suffix="synthesis"),
        metadata_json__whiteboard_id=str(whiteboard.id),
    ).first()
    if asset is None:
        return None
    version_id = (asset.metadata_json or {}).get("phase_synthesis_version_id") or (
        asset.metadata_json or {}
    ).get("canonical_asset_version_id")
    version = (
        AssetVersion.objects.filter(asset=asset, id=version_id).first() if version_id else None
    )
    if version is None:
        version = AssetVersion.objects.filter(asset=asset).order_by("-version_number").first()
    return (asset, version) if version is not None else None


def _synthesis_payload(*, whiteboard: WorkWhiteboard, phase_id: str) -> dict[str, Any] | None:
    pair = _synthesis_asset(whiteboard=whiteboard, phase_id=phase_id)
    if pair is None:
        return None
    asset, version = pair
    return {
        "asset_id": str(asset.id),
        "asset_version_id": str(version.id),
        "created_at": version.created_at.isoformat(),
    }


def _criterion_result(criterion: dict[str, Any], submitted: dict[str, Any]) -> dict[str, Any]:
    key = str(criterion.get("key") or "")
    value_present = key in submitted
    value = submitted.get(key)
    expected = criterion.get("expected")
    threshold = criterion.get("threshold")
    comparator = expected if expected is not None else threshold
    passed = False
    if value_present:
        passed = _compare_values(
            value=value,
            comparator=comparator,
            operator=str(criterion.get("operator") or "=="),
            value_type=str(criterion.get("value_type") or "number"),
        )
    elif not bool(criterion.get("required", True)):
        passed = True
    return {
        "key": key,
        "label": criterion.get("label") or _label(key),
        "operator": criterion.get("operator"),
        "value_type": criterion.get("value_type"),
        "expected": comparator,
        "actual": sanitize_outbox_payload(value),
        "required": bool(criterion.get("required", True)),
        "hard_fail": bool(criterion.get("hard_fail", False)),
        "passed": passed,
        "missing": not value_present,
    }


def _compare_values(*, value: Any, comparator: Any, operator: str, value_type: str) -> bool:
    if operator == "in":
        return value in (comparator if isinstance(comparator, list) else [comparator])
    resolved = _comparison_pair(value=value, comparator=comparator, value_type=value_type)
    if resolved is None:
        return False
    actual, expected = resolved
    return _apply_operator(actual=actual, expected=expected, operator=operator)


def _comparison_pair(*, value: Any, comparator: Any, value_type: str) -> tuple[Any, Any] | None:
    if value_type == "number":
        try:
            return float(value), float(comparator)
        except (TypeError, ValueError):
            return None
    if value_type == "boolean":
        return _bool_value(value), _bool_value(comparator)
    if value_type == "enum":
        return str(value).lower(), str(comparator).lower()
    return str(value), str(comparator)


def _apply_operator(*, actual: Any, expected: Any, operator: str) -> bool:
    if operator == ">=":
        return bool(actual >= expected)
    if operator == ">":
        return bool(actual > expected)
    if operator == "<=":
        return bool(actual <= expected)
    if operator == "<":
        return bool(actual < expected)
    if operator == "==":
        return bool(actual == expected)
    if operator == "!=":
        return bool(actual != expected)
    return False


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "pass", "passed"}


def _gate_result(criteria_results: list[dict[str, Any]]) -> str:
    failed = [item for item in criteria_results if not bool(item.get("passed"))]
    if not failed:
        return "pass"
    if any(bool(item.get("hard_fail")) for item in failed):
        return "fail"
    return "revision_required"


def _composite_score(criteria_results: list[dict[str, Any]]) -> float:
    if not criteria_results:
        return 0.0
    passed = sum(1 for item in criteria_results if bool(item.get("passed")))
    return round((passed / len(criteria_results)) * 100, 2)


def _latest_gate_evaluation(*, whiteboard: WorkWhiteboard, phase_id: str) -> EvaluationRun | None:
    return (
        EvaluationRun.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            result_json__whiteboard_id=str(whiteboard.id),
            result_json__phase_id=phase_id,
        )
        .order_by("-created_at")
        .first()
    )


def _gate_payload(
    *, evaluation: EvaluationRun | None, include_internal: bool
) -> dict[str, Any] | None:
    if evaluation is None:
        return None
    result = _result_json(evaluation)
    payload = {
        "evaluation_id": str(evaluation.id),
        "status": evaluation.status,
        "result": result.get("gate_result"),
        "score": evaluation.score,
        "grade": evaluation.grade,
        "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
    }
    if include_internal:
        payload["criteria_results"] = (
            result.get("criteria_results")
            if isinstance(result.get("criteria_results"), list)
            else []
        )
        payload["submitted_scorecard"] = (
            result.get("submitted_scorecard")
            if isinstance(result.get("submitted_scorecard"), dict)
            else {}
        )
    return payload


def _definition_gate_payload(
    *,
    definition: dict[str, Any],
    whiteboard: WorkWhiteboard,
    include_internal: bool,
) -> dict[str, Any] | None:
    gate = _gate(definition)
    if not gate:
        return None
    evaluation = _latest_gate_evaluation(
        whiteboard=whiteboard, phase_id=str(definition["phase_id"])
    )
    payload: dict[str, Any] = {
        "gate_id": str(gate.get("gate_id") or ""),
        "result": _result_json(evaluation).get("gate_result")
        if evaluation is not None
        else "pending",
    }
    if include_internal:
        payload.update(
            {
                "criteria": list(gate.get("criteria") or []),
                "pass_condition": gate.get("pass_condition"),
                "approval_required": bool(gate.get("approval_required")),
                "on_pass": dict(gate.get("on_pass") or {}),
                "on_fail": dict(gate.get("on_fail") or {}),
                "latest_evaluation": _gate_payload(evaluation=evaluation, include_internal=True),
            }
        )
    return payload


def _current_state(
    *, whiteboard: WorkWhiteboard, definition: dict[str, Any], include_internal: bool
) -> dict[str, Any]:
    phase_id = str(definition["phase_id"])
    projection = _phase_projection(whiteboard=whiteboard, phase_id=phase_id)
    state = (
        projection.json_state
        if projection is not None and isinstance(projection.json_state, dict)
        else {}
    )
    workstreams = _workstream_state(
        whiteboard=whiteboard, definition=definition, include_internal=include_internal
    )
    all_completed = all(
        item.get("status") == "completed" for item in workstreams if item.get("required", True)
    )
    latest_gate = _latest_gate_evaluation(whiteboard=whiteboard, phase_id=phase_id)
    payload: dict[str, Any] = {
        "status": str(
            state.get("status")
            or (
                "started"
                if any(item["status"] != "not_started" for item in workstreams)
                else "not_started"
            )
        ),
        "all_workstreams_completed": all_completed,
        "synthesis": _synthesis_payload(whiteboard=whiteboard, phase_id=phase_id),
        "gate": _gate_payload(evaluation=latest_gate, include_internal=include_internal),
    }
    if include_internal:
        payload["projection_id"] = str(projection.id) if projection is not None else ""
        payload["applied_actions"] = dict(state.get("applied_actions") or {})
    return payload


def _allowed_actions(*, whiteboard: WorkWhiteboard, definition: dict[str, Any]) -> list[str]:
    phase_id = str(definition["phase_id"])
    actions: list[str] = []
    if any(
        item["status"] != "not_started"
        for item in _workstream_state(
            whiteboard=whiteboard, definition=definition, include_internal=False
        )
    ):
        actions.extend(["synthesize", "evaluate"])
    else:
        actions.append("start")
    if _synthesis_asset(whiteboard=whiteboard, phase_id=phase_id) is not None:
        actions.append("evaluate")
    return sorted(set(actions))


def _route_gate_outcome(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    evaluation: EvaluationRun,
    department_slug: str,
    result: str,
) -> TaskRoutingRecord:
    department = register_department(
        organization=whiteboard.organization,
        slug=department_slug,
        name=_label(department_slug),
        department_type=department_slug[:64],
        service_tags=["workstream_gate"],
        metadata={"system_managed": True, "source": "workstream_gates"},
    )
    phase_id = str(definition["phase_id"])
    return route_event_to_department(
        company=whiteboard.company,
        department=department,
        user=user,
        event_type=f"whiteboard.phase.gate.{result}",
        trigger_type=f"whiteboard.phase.gate.{result}",
        communication_thread=whiteboard.communication_thread,
        communication_message=whiteboard.source_message,
        service_engagement=whiteboard.service_engagement,
        operation=evaluation.operation,
        reason=f"Gate {result} for phase {definition['phase_name']}.",
        status="queued" if result == "pass" else "blocked",
        priority="normal",
        idempotency_key=_phase_key(
            whiteboard=whiteboard, phase_id=phase_id, suffix=f"gate:{result}:{department_slug}"
        ),
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "phase_id": phase_id,
            "source_policy_id": definition.get("source_policy_id"),
            "pack_id": definition.get("pack_id"),
            "gate_id": _gate(definition).get("gate_id"),
            "gate_result": result,
            "evaluation_id": str(evaluation.id),
        },
    )


def _approval_for_gate(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    evaluation: EvaluationRun,
) -> ApprovalTask:
    phase_id = str(definition["phase_id"])
    run = evaluation.operation or _gate_run(user=user, whiteboard=whiteboard, definition=definition)
    node_id = _safe_node_id(f"{phase_id}:approval")
    existing = ApprovalTask.objects.filter(run=run, node_id=node_id, status="pending").first()
    if existing is not None:
        return existing
    return create_backend_approval_task(
        run=run,
        node_id=node_id,
        assignee=None,
        status="pending",
        payload=sanitize_outbox_payload(
            {
                "prompt_message": f"Review {definition['phase_name']} gate result before the next phase continues.",
                "required_fields": [],
                "whiteboard_id": str(whiteboard.id),
                "phase_id": phase_id,
                "source_policy_id": definition.get("source_policy_id"),
                "gate_evaluation_id": str(evaluation.id),
            }
        ),
    )


def _gate_failure_signal(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    evaluation: EvaluationRun,
) -> Any:
    result = _result_json(evaluation)
    weak_areas = [
        str(item.get("key"))
        for item in list(result.get("criteria_results") or [])
        if isinstance(item, dict) and not bool(item.get("passed"))
    ]
    phase_id = str(definition["phase_id"])
    return create_company_signal(
        company=whiteboard.company,
        actor=user,
        signal_type="manual",
        signal_kind="risk",
        domain_context="workstream",
        source="workstream_gates",
        external_key=_phase_key(
            whiteboard=whiteboard, phase_id=phase_id, suffix=f"gate-signal:{evaluation.id}"
        ),
        title=f"{definition['phase_name']} gate revision required",
        summary="A pack-defined phase gate did not pass.",
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "phase_id": phase_id,
            "evaluation_id": str(evaluation.id),
            "weak_areas": weak_areas,
        },
    )


def _upsert_phase_projection(
    *,
    whiteboard: WorkWhiteboard,
    definition: dict[str, Any],
    state: dict[str, Any],
    source_refs: list[dict[str, Any]] | None = None,
    summary: str = "",
) -> StateProjection:
    phase_id = str(definition["phase_id"])
    existing = _phase_projection(whiteboard=whiteboard, phase_id=phase_id)
    merged_state = {
        **(
            (
                existing.json_state
                if existing is not None and isinstance(existing.json_state, dict)
                else {}
            )
            or {}
        ),
        **sanitize_outbox_payload(state),
        "schema_version": PHASE_SCHEMA_VERSION,
        "whiteboard_id": str(whiteboard.id),
        "phase_id": phase_id,
        "definition": _definition_snapshot(definition),
    }
    projection, _created = StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_phase_projection_type(whiteboard=whiteboard, phase_id=phase_id),
        defaults={
            "display_label": str(definition.get("phase_name") or _label(phase_id))[:160],
            "source_refs_json": sanitize_outbox_payload(source_refs or []),
            "json_state": merged_state,
            "markdown_summary": summary
            or f"Current state for phase {definition.get('phase_name') or phase_id}.",
            "generated_by": "workstream_gates",
        },
    )
    return projection


def _phase_projection(*, whiteboard: WorkWhiteboard, phase_id: str) -> StateProjection | None:
    return StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_phase_projection_type(whiteboard=whiteboard, phase_id=phase_id),
    ).first()


def _phase_projections_for_whiteboard(whiteboard: WorkWhiteboard) -> QuerySet[StateProjection]:
    return StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type__startswith=f"{PHASE_PROJECTION_PREFIX}:",
        json_state__whiteboard_id=str(whiteboard.id),
    )


def _phase_projection_type(*, whiteboard: WorkWhiteboard, phase_id: str) -> str:
    slug = _safe_key(phase_id)[:56]
    return f"{PHASE_PROJECTION_PREFIX}:{slug}:{str(whiteboard.id).replace('-', '')}"[:120]


def _definition_snapshot(definition: dict[str, Any]) -> dict[str, Any]:
    return sanitize_outbox_payload(
        {
            "phase_id": definition.get("phase_id"),
            "source_policy_id": definition.get("source_policy_id"),
            "pack_id": definition.get("pack_id"),
            "phase_name": definition.get("phase_name"),
            "workstreams": definition.get("workstreams"),
            "gate": definition.get("gate"),
        }
    )


def _result_json(evaluation: EvaluationRun | None) -> dict[str, Any]:
    if evaluation is None:
        return {}
    return evaluation.result_json if isinstance(evaluation.result_json, dict) else {}


def _phase_key(*, whiteboard: WorkWhiteboard, phase_id: str, suffix: str) -> str:
    return f"whiteboard:{whiteboard.id}:phase:{phase_id}:{suffix}"[:255]


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "")).strip("_") or "phase"


def _safe_node_id(value: str) -> str:
    return _safe_key(value)[:64]


def _label(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").replace(".", " ").title()


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _refresh_whiteboard_snapshot(whiteboard: WorkWhiteboard) -> None:
    from application.services.work_whiteboards import refresh_whiteboard_redis_snapshot

    refresh_whiteboard_redis_snapshot(whiteboard)
