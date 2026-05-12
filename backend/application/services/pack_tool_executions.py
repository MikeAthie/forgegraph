"""Generic pack-declared tool execution gates and dry-run receipts."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from django.db import transaction

from application.services.audit_log import record_audit_log
from application.services.operating_model_packs import load_pack_definition
from application.services.policy_evaluations import evaluate_policy, policy_evaluation_payload
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    Graph,
    PolicyEvaluation,
    Run,
    ToolExecution,
    User,
)


class PackToolExecutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def execute_pack_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    policy_evaluation_id: UUID | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    effect = str(tool.get("side_effects") or "none").lower()
    side_effecting = effect not in {"", "none", "read", "false"}
    action_type = str(tool.get("policy_action_type") or tool.get("category") or tool_id)
    payload = dict(inputs or {})
    policy_evaluation = None
    if side_effecting:
        policy_evaluation = _policy_evaluation(
            company=company,
            user=user,
            operation=operation,
            action_type=action_type,
            inputs={**payload, "external_write_side_effect": True},
            policy_evaluation_id=policy_evaluation_id,
        )
        if policy_evaluation.status == "blocked":
            raise PackToolExecutionError(
                "policy_blocked", "Policy evaluation blocked this side-effecting tool."
            )
        if not dry_run and policy_evaluation.status == "approval_required":
            approval = policy_evaluation.approval_task
            if approval is None or approval.status != "approved":
                raise PackToolExecutionError(
                    "approval_required",
                    "This side-effecting tool requires an approved policy gate.",
                )

    attempt_id = _attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload)
    side_effect_class = _side_effect_class(effect=effect, dry_run=dry_run)
    with transaction.atomic():
        tool_execution, _ = ToolExecution.objects.get_or_create(
            run=operation,
            node_id=f"pack_tool:{tool_id}"[:255],
            attempt_id=attempt_id,
            defaults={
                "tool_name": tool_id[:128],
                "tool_version": str(tool.get("pack_id") or "")[:64],
                "idempotency_key": (idempotency_key or attempt_id)[:128],
                "side_effect_class": side_effect_class,
                "status": "succeeded",
            },
        )
        if tool_execution.status != "succeeded":
            tool_execution.status = "succeeded"
            tool_execution.save(update_fields=["status", "updated_at"])
    receipt = {
        "tool_execution_id": str(tool_execution.id),
        "company_id": str(company.id),
        "operation_id": str(operation.id),
        "tool_id": tool_id,
        "label": str(tool.get("label") or tool.get("name") or tool_id),
        "dry_run": dry_run,
        "side_effects": effect,
        "status": tool_execution.status,
        "policy_evaluation": policy_evaluation_payload(policy_evaluation)
        if policy_evaluation is not None
        else None,
    }
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="pack_tool.execution_receipt",
        resource_type="tool_execution",
        resource_id=str(tool_execution.id),
        metadata=receipt,
    )
    return receipt


def _policy_evaluation(
    *,
    company: Graph,
    user: User,
    operation: Run,
    action_type: str,
    inputs: dict[str, Any],
    policy_evaluation_id: UUID | None,
) -> PolicyEvaluation:
    if policy_evaluation_id is not None:
        evaluation = PolicyEvaluation.objects.filter(
            company=company, id=policy_evaluation_id
        ).first()
        if evaluation is None:
            raise PackToolExecutionError(
                "policy_evaluation_not_found", "Policy evaluation was not found."
            )
        return evaluation
    return evaluate_policy(
        company=company,
        user=user,
        action_type=action_type,
        inputs=inputs,
        operation=operation,
    )


def _tool_definition(*, company: Graph, tool_id: str) -> dict[str, Any]:
    for installation in CompanyOperatingModelInstallation.objects.filter(
        company=company, status="active"
    ):
        definition = load_pack_definition(installation.pack_id)
        tools_file = definition.files.get("tools") if isinstance(definition.files, dict) else {}
        for key in ("tool_packages", "department_tools"):
            values = tools_file.get(key) if isinstance(tools_file, dict) else []
            if not isinstance(values, list):
                continue
            for tool in values:
                if isinstance(tool, dict) and str(tool.get("id") or "") == tool_id:
                    return {**tool, "pack_id": definition.pack_id}
    raise PackToolExecutionError("tool_not_found", "Tool is not declared by an installed pack.")


def _side_effect_class(*, effect: str, dry_run: bool) -> str:
    if dry_run or effect in {"", "none", "read"}:
        return "pure"
    if effect == "write":
        return "idempotent"
    return "non_idempotent"


def _attempt_id(*, idempotency_key: str, tool_id: str, inputs: dict[str, Any]) -> str:
    payload = json.dumps(
        {"idempotency_key": idempotency_key, "tool_id": tool_id, "inputs": inputs},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
