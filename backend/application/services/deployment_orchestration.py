"""Generic whiteboard-scoped deployment orchestration."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.company_ops import create_company_signal
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.operating_model_packs import OperatingModelPackError, load_pack_definition
from application.services.pack_tool_executions import (
    CONNECTOR_EXECUTION_TOOL_IDS,
    PackToolExecutionError,
    execute_deployment_connector_tool,
    execute_pack_tool,
)
from application.services.product_operations import contract_operation_metadata
from application.services.rbac import has_min_role
from application.services.routing import register_department, route_event_to_department
from application.services.task_lifecycle import get_or_create_backend_operation_run
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    DepartmentRegistry,
    Graph,
    GraphVersion,
    Run,
    StateProjection,
    ToolExecution,
    User,
    WorkWhiteboard,
)

DEPLOYMENT_SCHEMA_VERSION = "whiteboard_deployment_v1"
DEPLOYMENT_CONFIG_KEY = "deployment_policies"
DEPLOYMENT_PROJECTION_PREFIX = "whiteboard_deployment"
VALID_DEPLOYMENT_STATUSES = {
    "not_started",
    "blocked",
    "ready",
    "prepared",
    "executed",
    "partial",
}


class DeploymentOrchestrationError(ValueError):
    """Domain error for generic deployment orchestration."""

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


def load_deployment_policy(
    *,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a deployment policy for one whiteboard from explicit data or installed packs."""

    requested = str(policy_id or "").strip()
    if definition is not None:
        normalized = _normalize_policy(
            sanitize_outbox_payload(definition),
            source_policy_id=str(definition.get("source_policy_id") or "explicit_fixture"),
            pack_id=str(definition.get("pack_id") or "explicit_fixture"),
        )
        if requested and normalized["policy_id"] != requested:
            raise DeploymentOrchestrationError(
                "deployment_policy_not_found",
                "The requested deployment policy was not found for this whiteboard.",
                details=[{"policy_id": requested}],
            )
        return normalized

    candidates = list_available_deployment_policies(whiteboard=whiteboard)
    for candidate in candidates:
        if requested and str(candidate.get("policy_id") or "") != requested:
            continue
        return _normalize_policy(
            sanitize_outbox_payload(candidate),
            source_policy_id=str(
                candidate.get("source_policy_id") or candidate.get("pack_id") or ""
            ),
            pack_id=str(candidate.get("pack_id") or ""),
        )
    if not requested and candidates:
        return _normalize_policy(
            sanitize_outbox_payload(candidates[0]),
            source_policy_id=str(
                candidates[0].get("source_policy_id") or candidates[0].get("pack_id") or ""
            ),
            pack_id=str(candidates[0].get("pack_id") or ""),
        )
    raise DeploymentOrchestrationError(
        "deployment_policy_not_found",
        "No active deployment policy was found for this whiteboard.",
        details=[{"policy_id": requested}],
    )


def list_available_deployment_policies(*, whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in _policy_candidates(whiteboard):
        policy_id = str(candidate.get("policy_id") or "")
        if not policy_id or policy_id in seen:
            continue
        policies.append(candidate)
        seen.add(policy_id)
    projection = _deployment_projection(whiteboard)
    if projection is not None and isinstance(projection.json_state, dict):
        definition = _dict_or_empty(projection.json_state.get("policy"))
        policy_id = str(definition.get("policy_id") or "")
        if policy_id and policy_id not in seen:
            policies.append(definition)
    return policies


def deployment_contract_for_whiteboard(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None = None,
    include_internal: bool = False,
) -> dict[str, Any] | None:
    """Return the sanitized deployment contract for the whiteboard, if a policy exists."""

    try:
        policy = load_deployment_policy(whiteboard=whiteboard)
    except DeploymentOrchestrationError:
        projection = _deployment_projection(whiteboard)
        if projection is None or not isinstance(projection.json_state, dict):
            return None
        policy = _dict_or_empty(projection.json_state.get("policy"))
        if not policy or not str(policy.get("policy_id") or "").strip():
            return None
    internal = include_internal or _can_manage_deployment(user=user, whiteboard=whiteboard)
    return _deployment_contract(
        whiteboard=whiteboard, policy=policy, user=user, include_internal=internal
    )


def list_deployment_state(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not has_company_access(user, whiteboard.company, "viewer"):
        raise DeploymentOrchestrationError(
            "permission_denied",
            "You do not have access to this whiteboard deployment state.",
        )
    policy = load_deployment_policy(
        whiteboard=whiteboard, policy_id=policy_id, definition=definition
    )
    return _deployment_contract(
        whiteboard=whiteboard,
        policy=policy,
        user=user,
        include_internal=_can_manage_deployment(user=user, whiteboard=whiteboard),
    )


def prepare_deployment_for_whiteboard(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deployment items from config, creating receipts or honest blockers."""

    _ensure_can_manage_deployment(user=user, whiteboard=whiteboard)
    policy = load_deployment_policy(
        whiteboard=whiteboard, policy_id=policy_id, definition=definition
    )
    with transaction.atomic():
        state_channels = create_deployment_items(
            user=user, whiteboard=whiteboard, policy=policy, execute_ready=True
        )
        status = _overall_status(state_channels)
        _upsert_deployment_projection(
            whiteboard=whiteboard,
            policy=policy,
            state={
                "status": status,
                "channels": state_channels,
                "prepared_at": timezone.now().isoformat(),
            },
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return _deployment_contract(
        whiteboard=whiteboard, policy=policy, user=user, include_internal=True
    )


def create_deployment_items(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    execute_ready: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate each configured channel and create durable generic records."""

    _ensure_can_manage_deployment(user=user, whiteboard=whiteboard)
    existing = _deployment_state(whiteboard)
    existing_channels = {
        str(item.get("id") or ""): item
        for item in list(existing.get("channels") or [])
        if isinstance(item, dict)
    }
    result: list[dict[str, Any]] = []
    for channel in _channels(policy):
        channel_id = str(channel["id"])
        previous = existing_channels.get(channel_id, {})
        readiness = _readiness_for_channel(whiteboard=whiteboard, policy=policy, channel=channel)
        if readiness["status"] == "blocked":
            blocked = mark_channel_blocked(
                user=user,
                whiteboard=whiteboard,
                policy=policy,
                channel=channel,
                reason_code=str(readiness.get("reason_code") or "blocked"),
                reason=str(readiness.get("reason") or "Deployment channel is blocked."),
                operation=None,
            )
            result.append({**previous, **blocked, "status": "blocked"})
            continue

        if execute_ready and bool(channel.get("allow_dry_run", True)):
            item = request_tool_execution_for_channel(
                user=user,
                whiteboard=whiteboard,
                channel_id=channel_id,
                dry_run=True,
                inputs={},
                policy_id=str(policy["policy_id"]),
                definition=policy,
            )
            result.append({**previous, **item})
            continue

        result.append(
            {
                **previous,
                **_channel_payload(
                    whiteboard=whiteboard,
                    policy=policy,
                    channel=channel,
                    status="ready",
                    include_internal=True,
                ),
            }
        )
    return result


def evaluate_deployment_readiness(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
    include_internal: bool = True,
) -> dict[str, Any]:
    if not has_company_access(user, whiteboard.company, "viewer"):
        raise DeploymentOrchestrationError(
            "permission_denied",
            "You do not have access to this whiteboard deployment readiness.",
        )
    policy = load_deployment_policy(
        whiteboard=whiteboard, policy_id=policy_id, definition=definition
    )
    channels = []
    for channel in _channels(policy):
        readiness = _readiness_for_channel(whiteboard=whiteboard, policy=policy, channel=channel)
        channels.append(
            _channel_payload(
                whiteboard=whiteboard,
                policy=policy,
                channel=channel,
                status=str(readiness["status"]),
                blocked_reason=str(readiness.get("reason") or ""),
                blocked_reason_code=str(readiness.get("reason_code") or ""),
                include_internal=include_internal,
            )
        )
    return sanitize_outbox_payload(
        {
            "whiteboard_id": str(whiteboard.id),
            "policy_id": str(policy["policy_id"]),
            "status": _overall_status(channels),
            "channels": channels,
        }
    )


def request_tool_execution_for_channel(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    channel_id: str,
    dry_run: bool = True,
    inputs: dict[str, Any] | None = None,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Request a policy-declared tool execution for one deployment channel."""

    _ensure_can_manage_deployment(user=user, whiteboard=whiteboard)
    policy = load_deployment_policy(
        whiteboard=whiteboard, policy_id=policy_id, definition=definition
    )
    channel = _channel(policy, channel_id)
    if channel is None:
        raise DeploymentOrchestrationError(
            "deployment_channel_not_found",
            "Deployment channel is not defined by the policy.",
            details=[{"channel_id": channel_id}],
        )
    if not dry_run and not bool(channel.get("allow_live_execution", False)):
        blocked = mark_channel_blocked(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            reason_code="live_execution_not_allowed",
            reason="Policy does not allow live external execution in this phase.",
            operation=None,
        )
        _merge_channel_state(whiteboard=whiteboard, policy=policy, item=blocked)
        _refresh_whiteboard_snapshot(whiteboard)
        return blocked
    readiness = _readiness_for_channel(whiteboard=whiteboard, policy=policy, channel=channel)
    if readiness["status"] == "blocked":
        blocked = mark_channel_blocked(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            reason_code=str(readiness.get("reason_code") or "blocked"),
            reason=str(readiness.get("reason") or "Deployment channel is blocked."),
            operation=None,
        )
        _merge_channel_state(whiteboard=whiteboard, policy=policy, item=blocked)
        _refresh_whiteboard_snapshot(whiteboard)
        return blocked
    tool_id = str(channel.get("tool_id") or "").strip()
    if not tool_id:
        blocked = mark_channel_blocked(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            reason_code="tool_required",
            reason="Deployment channel does not define an executable tool.",
            operation=None,
        )
        _merge_channel_state(whiteboard=whiteboard, policy=policy, item=blocked)
        _refresh_whiteboard_snapshot(whiteboard)
        return blocked

    operation = _deployment_run(user=user, whiteboard=whiteboard, policy=policy, channel=channel)
    payload = _tool_inputs(
        whiteboard=whiteboard, policy=policy, channel=channel, inputs=inputs or {}
    )
    approval = _approved_approval_task(whiteboard=whiteboard, policy=policy, channel=channel)
    try:
        if _is_managed_connector_tool(tool_id):
            receipt = execute_deployment_connector_tool(
                company=whiteboard.company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                inputs=payload,
                dry_run=dry_run,
                idempotency_key=_deployment_key(
                    whiteboard=whiteboard,
                    policy=policy,
                    suffix=f"tool:{channel_id}:{dry_run}",
                ),
                approved=approval is not None,
                approval_id=str(approval.id) if approval is not None else "",
                policy_allows_live=bool(channel.get("allow_live_execution", False)),
                requires_unsubscribe_footer=bool(channel.get("requires_unsubscribe_footer", False)),
                operator_confirmed=bool(
                    payload.get("operator_confirmed") or channel.get("operator_confirmed")
                ),
                policy_allows_web_automation_evidence=bool(
                    channel.get("allow_web_automation_evidence", False)
                ),
                policy_allows_manual_publish_evidence=bool(
                    channel.get("allow_manual_publish_evidence", False)
                ),
                policy_allows_provider_publish=bool(channel.get("allow_provider_publish", False)),
                requires_compliance_gate=bool(channel.get("requires_compliance_gate", False)),
                requires_originality_check=bool(channel.get("requires_originality_check", False)),
            )
        else:
            receipt = execute_pack_tool(
                company=whiteboard.company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                inputs=payload,
                dry_run=dry_run,
                idempotency_key=_deployment_key(
                    whiteboard=whiteboard,
                    policy=policy,
                    suffix=f"tool:{channel_id}:{dry_run}",
                ),
            )
    except PackToolExecutionError as exc:
        blocked = mark_channel_blocked(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            reason_code=exc.code,
            reason=exc.message,
            operation=operation,
        )
        _merge_channel_state(whiteboard=whiteboard, policy=policy, item=blocked)
        _refresh_whiteboard_snapshot(whiteboard)
        return blocked
    tool_execution_id = str(receipt.get("tool_execution_id") or "")
    if str(receipt.get("status") or "") == "failed":
        error = _dict_or_empty(receipt.get("error"))
        blocked = mark_channel_blocked(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            reason_code=str(error.get("error_code") or "provider_call_failed"),
            reason=str(error.get("error_message") or "Connector provider call failed."),
            operation=operation,
        )
        blocked = {
            **blocked,
            "tool_execution_id": tool_execution_id,
            "receipt": _receipt_payload(receipt),
        }
        _merge_channel_state(whiteboard=whiteboard, policy=policy, item=blocked)
        _refresh_whiteboard_snapshot(whiteboard)
        return blocked
    item = _channel_payload(
        whiteboard=whiteboard,
        policy=policy,
        channel=channel,
        status="executed" if tool_execution_id else "prepared",
        operation=operation,
        tool_execution_id=tool_execution_id,
        receipt=receipt,
        include_internal=True,
    )
    _merge_channel_state(whiteboard=whiteboard, policy=policy, item=item)
    _refresh_whiteboard_snapshot(whiteboard)
    return item


def mark_channel_blocked(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
    reason_code: str,
    reason: str,
    operation: Run | None = None,
) -> dict[str, Any]:
    """Create idempotent signal and routing records for a blocked channel."""

    signal = create_company_signal(
        company=whiteboard.company,
        actor=user,
        signal_type="manual",
        signal_kind="capability_gap",
        domain_context="deployment",
        source="deployment_orchestration",
        external_key=_deployment_key(
            whiteboard=whiteboard,
            policy=policy,
            suffix=f"signal:{channel['id']}:{reason_code}",
        ),
        title=f"{channel['display_name']} deployment blocked",
        summary=reason,
        channel=str(channel.get("id") or "")[:64],
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "channel_id": channel.get("id"),
            "reason_code": reason_code,
        },
    )
    department = _blocked_department(whiteboard=whiteboard, policy=policy, channel=channel)
    record = route_event_to_department(
        company=whiteboard.company,
        department=department,
        user=user,
        event_type="whiteboard.deployment.blocked",
        trigger_type="whiteboard.deployment.blocked",
        communication_thread=whiteboard.communication_thread,
        communication_message=whiteboard.source_message,
        service_engagement=whiteboard.service_engagement,
        operation=operation,
        company_signal=signal,
        reason=reason,
        status="blocked",
        priority=str(channel.get("priority") or "normal"),
        idempotency_key=_deployment_key(
            whiteboard=whiteboard,
            policy=policy,
            suffix=f"route:{channel['id']}:{reason_code}",
        ),
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "channel_id": channel.get("id"),
            "blocked_reason_code": reason_code,
        },
    )
    return _channel_payload(
        whiteboard=whiteboard,
        policy=policy,
        channel=channel,
        status="blocked",
        blocked_reason=reason,
        blocked_reason_code=reason_code,
        operation=operation,
        company_signal_id=str(signal.id),
        routing_record_id=str(record.id),
        include_internal=True,
    )


def apply_deployment_result(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
    tool_execution: ToolExecution | None = None,
    status: str = "",
) -> dict[str, Any]:
    _ensure_can_manage_deployment(user=user, whiteboard=whiteboard)
    next_status = status if status in VALID_DEPLOYMENT_STATUSES else "prepared"
    item = _channel_payload(
        whiteboard=whiteboard,
        policy=policy,
        channel=channel,
        status=next_status,
        tool_execution_id=str(tool_execution.id) if tool_execution is not None else "",
        include_internal=True,
    )
    _merge_channel_state(whiteboard=whiteboard, policy=policy, item=item)
    _refresh_whiteboard_snapshot(whiteboard)
    return item


def _deployment_contract(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    user: User | None,
    include_internal: bool,
) -> dict[str, Any]:
    manage = _can_manage_deployment(user=user, whiteboard=whiteboard)
    state = _deployment_state(whiteboard)
    state_channels = {
        str(item.get("id") or ""): item
        for item in list(state.get("channels") or [])
        if isinstance(item, dict)
    }
    channels: list[dict[str, Any]] = []
    for channel in _channels(policy):
        channel_id = str(channel["id"])
        item = _channel_payload(
            whiteboard=whiteboard,
            policy=policy,
            channel=channel,
            status=str(state_channels.get(channel_id, {}).get("status") or "not_started"),
            blocked_reason=str(state_channels.get(channel_id, {}).get("blocked_reason") or ""),
            blocked_reason_code=str(
                state_channels.get(channel_id, {}).get("blocked_reason_code") or ""
            ),
            operation_id=str(state_channels.get(channel_id, {}).get("operation_id") or ""),
            tool_execution_id=str(
                state_channels.get(channel_id, {}).get("tool_execution_id") or ""
            ),
            company_signal_id=str(
                state_channels.get(channel_id, {}).get("company_signal_id") or ""
            ),
            routing_record_id=str(
                state_channels.get(channel_id, {}).get("routing_record_id") or ""
            ),
            approval_task_id=str(state_channels.get(channel_id, {}).get("approval_task_id") or ""),
            asset_id=str(state_channels.get(channel_id, {}).get("asset_id") or ""),
            asset_version_id=str(state_channels.get(channel_id, {}).get("asset_version_id") or ""),
            receipt=state_channels.get(channel_id, {}).get("receipt")
            if isinstance(state_channels.get(channel_id, {}).get("receipt"), dict)
            else None,
            include_internal=include_internal,
        )
        channels.append(item)
    operation_state = contract_operation_metadata(
        whiteboard=whiteboard,
        target_type="deployment_contract",
        target_id=str(policy["policy_id"]),
    )
    current_state = _current_state_payload(state=state, include_internal=include_internal)
    current_state.update(operation_state)
    contract = {
        "whiteboard_id": str(whiteboard.id),
        "policy_id": str(policy["policy_id"]),
        "source_policy_id": str(policy.get("source_policy_id") or ""),
        "pack_id": str(policy.get("pack_id") or ""),
        "status": str(state.get("status") or _overall_status(channels)),
        "channels": channels,
        "current_state": current_state,
        "allowed_actions": _allowed_actions(whiteboard=whiteboard, policy=policy) if manage else [],
        **operation_state,
    }
    return sanitize_outbox_payload(contract)


def _normalize_policy(
    policy: dict[str, Any], *, source_policy_id: str, pack_id: str
) -> dict[str, Any]:
    policy_id = str(policy.get("policy_id") or policy.get("id") or "").strip()
    if not policy_id:
        raise DeploymentOrchestrationError(
            "deployment_policy_id_required", "Deployment policy requires an id."
        )
    channels = [
        _normalize_channel(item)
        for item in list(policy.get("channels") or [])
        if isinstance(item, dict)
    ]
    if not channels:
        raise DeploymentOrchestrationError(
            "deployment_channels_required",
            "Deployment policy must include at least one channel.",
        )
    return {
        "policy_id": policy_id[:160],
        "source_policy_id": str(policy.get("source_policy_id") or source_policy_id or policy_id)[
            :200
        ],
        "pack_id": str(policy.get("pack_id") or pack_id or "")[:160],
        "required_whiteboard_status": policy.get("required_whiteboard_status") or "",
        "required_approval_status": str(policy.get("required_approval_status") or "approved")[:32],
        "channels": channels,
        "on_ready": sanitize_outbox_payload(policy.get("on_ready") or {}),
        "on_blocked": sanitize_outbox_payload(policy.get("on_blocked") or {}),
        "on_success": sanitize_outbox_payload(policy.get("on_success") or {}),
        "on_failure": sanitize_outbox_payload(policy.get("on_failure") or {}),
        "metadata": sanitize_outbox_payload(policy.get("metadata") or {}),
    }


def _normalize_channel(item: dict[str, Any]) -> dict[str, Any]:
    channel_id = str(item.get("id") or "").strip()
    if not channel_id:
        raise DeploymentOrchestrationError(
            "deployment_channel_id_required", "Deployment channel requires an id."
        )
    return {
        "id": channel_id[:120],
        "display_name": str(item.get("display_name") or item.get("name") or _label(channel_id))[
            :160
        ],
        "department": str(
            item.get("department") or item.get("department_slug") or "deployment-ops"
        )[:160],
        "department_name": str(
            item.get("department_name") or _label(str(item.get("department") or "deployment-ops"))
        )[:255],
        "department_type": str(
            item.get("department_type") or item.get("department") or "deployment_ops"
        )[:64],
        "required_connector": str(item.get("required_connector") or "")[:160],
        "tool_id": str(item.get("tool_id") or "")[:160],
        "asset_types": [str(value)[:80] for value in list(item.get("asset_types") or [])],
        "approval_required": bool(item.get("approval_required", True)),
        "allow_dry_run": bool(item.get("allow_dry_run", True)),
        "allow_live_execution": bool(item.get("allow_live_execution", False)),
        "allow_sandbox_evidence": bool(item.get("allow_sandbox_evidence", False)),
        "allow_web_automation_evidence": bool(item.get("allow_web_automation_evidence", False)),
        "allow_manual_publish_evidence": bool(item.get("allow_manual_publish_evidence", False)),
        "allow_provider_publish": bool(item.get("allow_provider_publish", False)),
        "requires_unsubscribe_footer": bool(item.get("requires_unsubscribe_footer", False)),
        "requires_compliance_gate": bool(item.get("requires_compliance_gate", False)),
        "requires_originality_check": bool(item.get("requires_originality_check", False)),
        "operator_confirmed": bool(item.get("operator_confirmed", False)),
        "operator_confirmation_required": bool(item.get("operator_confirmation_required", False)),
        "platform": str(item.get("platform") or "")[:80],
        "risk_level": str(item.get("risk_level") or "")[:64],
        "priority": str(item.get("priority") or "normal")[:16],
        "metadata": sanitize_outbox_payload(item.get("metadata") or {}),
    }


def _policy_candidates(whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    program = _program_for_whiteboard(whiteboard)
    if program is not None and program.installation_id:
        candidates.extend(_policies_from_installation(program.installation))
    installations = CompanyOperatingModelInstallation.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        status="active",
    ).select_related("pack_release")
    for installation in installations:
        candidates.extend(_policies_from_installation(installation))
    return candidates


def _program_for_whiteboard(whiteboard: WorkWhiteboard) -> CompanyProgram | None:
    metadata = whiteboard.metadata_json if isinstance(whiteboard.metadata_json, dict) else {}
    candidates = [metadata.get("company_program_id"), metadata.get("program_id")]
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


def _policies_from_installation(
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
    policies: list[dict[str, Any]] = []
    for source in sources:
        policies.extend(_extract_policies(source, pack_id=installation.pack_id))
    return policies


def _extract_policies(source: Any, *, pack_id: str) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        return []
    policies: list[dict[str, Any]] = []
    for config in _nested_config_sources(source):
        raw = config.get(DEPLOYMENT_CONFIG_KEY) or config.get("deployments")
        if isinstance(raw, dict):
            if DEPLOYMENT_CONFIG_KEY in raw:
                raw = raw.get(DEPLOYMENT_CONFIG_KEY)
            else:
                raw = list(raw.values())
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            policy_id = str(item.get("policy_id") or item.get("id") or "")
            policies.append(
                {
                    **item,
                    "pack_id": str(item.get("pack_id") or pack_id),
                    "source_policy_id": str(
                        item.get("source_policy_id") or f"{pack_id}:{policy_id}"
                    ),
                }
            )
    return policies


def _nested_config_sources(source: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [source]
    for value in source.values():
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _readiness_for_channel(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
) -> dict[str, Any]:
    required_status = policy.get("required_whiteboard_status")
    if required_status:
        statuses = set(required_status if isinstance(required_status, list) else [required_status])
        if whiteboard.status not in statuses:
            return {
                "status": "blocked",
                "reason_code": "whiteboard_status_mismatch",
                "reason": "Whiteboard status does not satisfy this deployment policy.",
            }
    approval = _approved_approval_task(whiteboard=whiteboard, policy=policy, channel=channel)
    if bool(channel.get("approval_required", True)) and approval is None:
        return {
            "status": "blocked",
            "reason_code": "approval_required",
            "reason": "Approved human gate is required before deployment preparation.",
        }
    connector = str(channel.get("required_connector") or "").strip()
    if connector and connector not in _available_connectors(whiteboard):
        return {
            "status": "blocked",
            "reason_code": "connector_missing",
            "reason": "Required connector is not available for this company.",
        }
    tool_id = str(channel.get("tool_id") or "").strip()
    if tool_id and not _tool_available(company=whiteboard.company, tool_id=tool_id):
        return {
            "status": "blocked",
            "reason_code": "tool_missing",
            "reason": "Required tool is not declared by an active installed pack.",
        }
    asset = _asset_for_channel(whiteboard=whiteboard, channel=channel)
    if channel.get("asset_types") and asset is None:
        return {
            "status": "blocked",
            "reason_code": "asset_missing",
            "reason": "Required content artifact or draft is not available for this channel.",
        }
    return {"status": "ready", "reason_code": "", "reason": ""}


def _approved_approval_task(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
) -> ApprovalTask | None:
    required_status = str(policy.get("required_approval_status") or "approved")
    return (
        ApprovalTask.objects.filter(
            run__organization=whiteboard.organization,
            run__graph_version__graph=whiteboard.company,
            payload__whiteboard_id=str(whiteboard.id),
            status=required_status,
        )
        .order_by("-created_at")
        .first()
    )


def _available_connectors(whiteboard: WorkWhiteboard) -> set[str]:
    values: set[str] = set()
    for installation in CompanyOperatingModelInstallation.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        status="active",
    ).select_related("pack_release"):
        sources = [
            installation.public_config_json or {},
            installation.config_json or {},
            installation.pack_release.manifest_json if installation.pack_release_id else {},
            installation.pack_release.files_json if installation.pack_release_id else {},
        ]
        for source in sources:
            values.update(_connector_values(source))
    return values


def _connector_values(source: Any) -> set[str]:
    if not isinstance(source, dict):
        return set()
    raw = source.get("available_connectors") or source.get("connector_inventory") or {}
    if isinstance(raw, dict):
        return _connector_values_from_dict(raw)
    if isinstance(raw, list):
        return _connector_values_from_list(raw)
    return set()


def _connector_values_from_dict(raw: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key, item in raw.items():
        if item is False:
            continue
        if isinstance(item, dict) and not _connector_status_available(item):
            continue
        values.add(str(key))
    return values


def _connector_values_from_list(raw: list[Any]) -> set[str]:
    values: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            values.add(item)
            continue
        if not isinstance(item, dict):
            continue
        connector_id = str(item.get("id") or item.get("connector") or "").strip()
        if connector_id and bool(item.get("active", True)) and _connector_status_available(item):
            values.add(connector_id)
    return values


def _connector_status_available(item: dict[str, Any]) -> bool:
    return str(item.get("status") or "available").lower() in {
        "available",
        "active",
        "configured",
        "ready",
        "true",
    }


def _tool_available(*, company: Graph, tool_id: str) -> bool:
    if not tool_id:
        return False
    if tool_id in CONNECTOR_EXECUTION_TOOL_IDS:
        return True
    for installation in CompanyOperatingModelInstallation.objects.filter(
        company=company, status="active"
    ):
        try:
            definition = load_pack_definition(installation.pack_id)
        except OperatingModelPackError:
            continue
        tools_file = definition.files.get("tools") if isinstance(definition.files, dict) else {}
        for key in ("tool_packages", "department_tools"):
            values = tools_file.get(key) if isinstance(tools_file, dict) else []
            if not isinstance(values, list):
                continue
            for tool in values:
                if isinstance(tool, dict) and str(tool.get("id") or "") == tool_id:
                    return True
    return False


def _asset_for_channel(*, whiteboard: WorkWhiteboard, channel: dict[str, Any]) -> Asset | None:
    asset_types = [str(item) for item in list(channel.get("asset_types") or [])]
    queryset = Asset.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        metadata_json__whiteboard_id=str(whiteboard.id),
    ).exclude(status="deleted")
    if not asset_types:
        return queryset.order_by("-created_at").first()
    asset = (
        queryset.filter(metadata_json__output_type__in=asset_types).order_by("-created_at").first()
    )
    if asset is not None:
        return asset
    return (
        queryset.filter(metadata_json__artifact_type__in=asset_types)
        .order_by("-created_at")
        .first()
    )


def _blocked_department(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
) -> DepartmentRegistry:
    blocked = _dict_or_empty(policy.get("on_blocked"))
    slug = str(
        blocked.get("route_to_department")
        or blocked.get("route_to")
        or channel.get("department")
        or "deployment-ops"
    )
    name = str(channel.get("department_name") or _label(slug))
    return register_department(
        organization=whiteboard.organization,
        slug=slug,
        name=name,
        department_type=str(channel.get("department_type") or slug),
        service_tags=["deployment"],
        metadata={"system_managed": True, "source": "deployment_orchestration"},
    )


def _deployment_graph_version(*, company: Graph, policy_id: str) -> GraphVersion:
    key = f"deployment:{policy_id}"[:255]
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
                    "source": "deployment_orchestration",
                    "policy_id": policy_id,
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


def _deployment_run(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
) -> Run:
    policy_id = str(policy["policy_id"])
    channel_id = str(channel["id"])
    graph_version = _deployment_graph_version(company=whiteboard.company, policy_id=policy_id)
    key = _deployment_key(whiteboard=whiteboard, policy=policy, suffix=f"run:{channel_id}")
    now = timezone.now()
    return get_or_create_backend_operation_run(
        owner=user,
        organization=whiteboard.organization,
        thread_id=whiteboard.communication_thread_id,
        graph_version=graph_version,
        idempotency_key=key,
        status="succeeded",
        started_at=now,
        ended_at=now,
        input_json={
            "idempotency_key": key,
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy_id,
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "channel_id": channel_id,
        },
        output_json={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy_id,
            "channel_id": channel_id,
        },
        dispatch_graph_json=graph_version.graph_json,
    )


def _tool_inputs(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        **sanitize_outbox_payload(inputs),
        "whiteboard_id": str(whiteboard.id),
        "policy_id": policy.get("policy_id"),
        "channel_id": channel.get("id"),
    }
    payload.setdefault(
        "subject", whiteboard.request_summary or whiteboard.objective or "Deployment dry run"
    )
    payload.setdefault(
        "title", whiteboard.request_summary or whiteboard.objective or "Deployment dry run"
    )
    payload.setdefault("recipients", [])
    metadata = _dict_or_empty(channel.get("metadata"))
    platform = str(
        channel.get("platform") or metadata.get("platform") or channel.get("id") or ""
    ).strip()
    if platform:
        payload.setdefault("platform", platform)
    asset = _asset_for_channel(whiteboard=whiteboard, channel=channel)
    if asset is not None:
        payload.setdefault("asset_id", str(asset.id))
        payload.setdefault("asset_ids", [str(asset.id)])
        payload.setdefault("asset_approved", asset.status == "active")
        payload.setdefault("content_approved", asset.status == "active")
    payload.setdefault("deployment_channel_id", channel.get("id"))
    payload.setdefault(
        "requires_compliance_gate", bool(channel.get("requires_compliance_gate", False))
    )
    payload.setdefault(
        "requires_originality_check", bool(channel.get("requires_originality_check", False))
    )
    return payload


def _channel_payload(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    channel: dict[str, Any],
    status: str,
    blocked_reason: str = "",
    blocked_reason_code: str = "",
    operation: Run | None = None,
    operation_id: str = "",
    tool_execution_id: str = "",
    company_signal_id: str = "",
    routing_record_id: str = "",
    approval_task_id: str = "",
    asset_id: str = "",
    asset_version_id: str = "",
    receipt: dict[str, Any] | None = None,
    include_internal: bool = True,
) -> dict[str, Any]:
    approval = _approved_approval_task(whiteboard=whiteboard, policy=policy, channel=channel)
    asset = _asset_for_channel(whiteboard=whiteboard, channel=channel)
    version_id = _asset_version_id(asset)
    item: dict[str, Any] = {
        "id": str(channel["id"]),
        "display_name": str(channel.get("display_name") or _label(str(channel["id"]))),
        "status": status if status in VALID_DEPLOYMENT_STATUSES else "not_started",
        "blocked_reason": blocked_reason,
        "blocked_reason_code": blocked_reason_code,
        "tool_execution_id": tool_execution_id,
        "company_signal_id": company_signal_id,
        "routing_record_id": routing_record_id,
        "approval_task_id": approval_task_id or (str(approval.id) if approval is not None else ""),
        "asset_id": asset_id or (str(asset.id) if asset is not None else ""),
        "asset_version_id": asset_version_id or version_id,
        "allowed_actions": _channel_allowed_actions(channel=channel, status=status),
    }
    if operation is not None or operation_id:
        item["operation_id"] = str(operation.id) if operation is not None else operation_id
    if receipt:
        item["receipt"] = _receipt_payload(receipt)
    if include_internal:
        item.update(
            {
                "department": str(channel.get("department") or ""),
                "department_name": str(channel.get("department_name") or ""),
                "required_connector": str(channel.get("required_connector") or ""),
                "tool_id": str(channel.get("tool_id") or ""),
                "asset_types": list(channel.get("asset_types") or []),
                "allow_sandbox_evidence": bool(channel.get("allow_sandbox_evidence", False)),
                "allow_web_automation_evidence": bool(
                    channel.get("allow_web_automation_evidence", False)
                ),
                "allow_manual_publish_evidence": bool(
                    channel.get("allow_manual_publish_evidence", False)
                ),
                "allow_provider_publish": bool(channel.get("allow_provider_publish", False)),
                "requires_unsubscribe_footer": bool(
                    channel.get("requires_unsubscribe_footer", False)
                ),
                "requires_compliance_gate": bool(channel.get("requires_compliance_gate", False)),
                "requires_originality_check": bool(
                    channel.get("requires_originality_check", False)
                ),
                "operator_confirmation_required": bool(
                    channel.get("operator_confirmation_required", False)
                ),
                "platform": str(channel.get("platform") or ""),
                "risk_level": str(channel.get("risk_level") or ""),
                "metadata": sanitize_outbox_payload(channel.get("metadata") or {}),
            }
        )
    return sanitize_outbox_payload(item)


def _receipt_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    result = _dict_or_empty(receipt.get("result"))
    return sanitize_outbox_payload(
        {
            "tool_execution_id": receipt.get("tool_execution_id"),
            "tool_id": receipt.get("tool_id"),
            "dry_run": receipt.get("dry_run"),
            "status": receipt.get("status"),
            "completed_at": receipt.get("completed_at"),
            "result": {
                "provider": result.get("provider"),
                "platform": result.get("platform"),
                "mode": result.get("mode"),
                "status": result.get("status"),
                "message_id": result.get("message_id"),
                "provider_message_id": result.get("provider_message_id"),
                "provider_post_id": result.get("provider_post_id"),
                "provider_container_id": result.get("provider_container_id"),
                "evidence_mode": result.get("evidence_mode"),
                "sanitized": result.get("sanitized") is not False,
                "recipient_count": result.get("recipient_count"),
                "recipient_domains": result.get("recipient_domains"),
                "recipient_hashes": result.get("recipient_hashes"),
                "allowlist_matched": result.get("allowlist_matched"),
                "session_required": result.get("session_required"),
                "session_status": result.get("session_status"),
                "asset_count": result.get("asset_count"),
                "media_asset_ids": result.get("media_asset_ids"),
                "caption_hash": result.get("caption_hash"),
                "account_id_hash": result.get("account_id_hash"),
                "page_id_hash": result.get("page_id_hash"),
                "profile_id_hash": result.get("profile_id_hash"),
                "external_post_url_hash": result.get("external_post_url_hash"),
                "external_post_id_hash": result.get("external_post_id_hash"),
            },
        }
    )


def _channel_allowed_actions(*, channel: dict[str, Any], status: str) -> list[str]:
    if status == "ready":
        return ["execute_dry_run"] if bool(channel.get("allow_dry_run", True)) else []
    if status in {"prepared", "not_started"}:
        return ["prepare"]
    return []


def _asset_version_id(asset: Asset | None) -> str:
    if asset is None:
        return ""
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    version_id = str(
        metadata.get("canonical_asset_version_id") or metadata.get("asset_version_id") or ""
    )
    if version_id:
        return version_id
    version = asset.versions.order_by("-version_number").first()
    return str(version.id) if version is not None else ""


def _merge_channel_state(
    *, whiteboard: WorkWhiteboard, policy: dict[str, Any], item: dict[str, Any]
) -> None:
    state = _deployment_state(whiteboard)
    existing = {
        str(channel.get("id") or ""): channel
        for channel in list(state.get("channels") or [])
        if isinstance(channel, dict)
    }
    existing[str(item["id"])] = sanitize_outbox_payload(item)
    channels = [
        existing.get(
            str(channel["id"]),
            _channel_payload(
                whiteboard=whiteboard, policy=policy, channel=channel, status="not_started"
            ),
        )
        for channel in _channels(policy)
    ]
    _upsert_deployment_projection(
        whiteboard=whiteboard,
        policy=policy,
        state={"status": _overall_status(channels), "channels": channels},
    )


def _upsert_deployment_projection(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    state: dict[str, Any],
) -> StateProjection:
    existing = _deployment_projection(whiteboard)
    merged = {
        **(
            (
                existing.json_state
                if existing is not None and isinstance(existing.json_state, dict)
                else {}
            )
            or {}
        ),
        **sanitize_outbox_payload(state),
        "schema_version": DEPLOYMENT_SCHEMA_VERSION,
        "whiteboard_id": str(whiteboard.id),
        "policy_id": str(policy["policy_id"]),
        "policy": _policy_snapshot(policy),
        "updated_at": timezone.now().isoformat(),
    }
    projection, _created = StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_deployment_projection_type(whiteboard),
        defaults={
            "display_label": "Whiteboard deployment",
            "source_refs_json": [
                {"whiteboard_id": str(whiteboard.id), "policy_id": str(policy["policy_id"])}
            ],
            "json_state": merged,
            "markdown_summary": "Whiteboard deployment state from configured policy.",
            "generated_by": "system",
        },
    )
    return projection


def _deployment_projection(whiteboard: WorkWhiteboard) -> StateProjection | None:
    return StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_deployment_projection_type(whiteboard),
    ).first()


def _deployment_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    projection = _deployment_projection(whiteboard)
    if projection is None or not isinstance(projection.json_state, dict):
        return {}
    return dict(projection.json_state)


def _deployment_projection_type(whiteboard: WorkWhiteboard) -> str:
    return f"{DEPLOYMENT_PROJECTION_PREFIX}:{whiteboard.id}"


def _policy_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    return sanitize_outbox_payload(
        {
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "required_whiteboard_status": policy.get("required_whiteboard_status"),
            "required_approval_status": policy.get("required_approval_status"),
            "channels": list(policy.get("channels") or []),
        }
    )


def _current_state_payload(*, state: dict[str, Any], include_internal: bool) -> dict[str, Any]:
    payload = {
        "status": str(state.get("status") or "not_started"),
        "updated_at": state.get("updated_at"),
        "prepared_at": state.get("prepared_at"),
    }
    if include_internal:
        payload["schema_version"] = state.get("schema_version")
    return sanitize_outbox_payload(payload)


def _allowed_actions(*, whiteboard: WorkWhiteboard, policy: dict[str, Any]) -> list[str]:
    actions = ["prepare"]
    state = _deployment_state(whiteboard)
    if state.get("status") in {"ready", "prepared", "partial"}:
        actions.append("execute_dry_run")
    return actions


def _overall_status(channels: list[dict[str, Any]]) -> str:
    if not channels:
        return "not_started"
    statuses = {str(item.get("status") or "") for item in channels}
    if statuses == {"not_started"}:
        return "not_started"
    if "blocked" in statuses and len(statuses) == 1:
        return "blocked"
    if "blocked" in statuses:
        return "partial"
    if statuses <= {"executed", "prepared"}:
        return "prepared"
    if statuses <= {"ready", "prepared", "executed"}:
        return "ready"
    return "partial"


def _channels(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(policy.get("channels") or []) if isinstance(item, dict)]


def _is_managed_connector_tool(tool_id: str) -> bool:
    return str(tool_id or "").strip() in CONNECTOR_EXECUTION_TOOL_IDS


def _channel(policy: dict[str, Any], channel_id: str) -> dict[str, Any] | None:
    for item in _channels(policy):
        if str(item.get("id") or "") == channel_id:
            return item
    return None


def _ensure_can_manage_deployment(*, user: User, whiteboard: WorkWhiteboard) -> None:
    if not _can_manage_deployment(user=user, whiteboard=whiteboard):
        raise DeploymentOrchestrationError(
            "permission_denied",
            "Managing this whiteboard deployment requires company member access and organization member role.",
        )


def _can_manage_deployment(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _deployment_key(*, whiteboard: WorkWhiteboard, policy: dict[str, Any], suffix: str) -> str:
    raw = f"whiteboard:{whiteboard.id}:deployment:{policy['policy_id']}:{suffix}"
    if len(raw) <= 255:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"whiteboard:{whiteboard.id}:deployment:{digest}"


def _label(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").title()


def _refresh_whiteboard_snapshot(whiteboard: WorkWhiteboard) -> None:
    from application.services.work_whiteboards import refresh_whiteboard_redis_snapshot

    refresh_whiteboard_redis_snapshot(whiteboard)
