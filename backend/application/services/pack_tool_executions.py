"""Generic pack-declared tool execution gates and dry-run receipts."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

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

EMAIL_SANDBOX_TOOL_IDS = {"dmp.email_draft_send_schedule", "email_service_connector"}


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
        policy_evaluation = _evaluate_and_enforce_policy(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            action_type=action_type,
            payload=payload,
            dry_run=dry_run,
            policy_evaluation_id=policy_evaluation_id,
        )

    attempt_id = _attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload)
    side_effect_class = _side_effect_class(effect=effect, dry_run=dry_run)
    result_json = _tool_execution_result(
        company=company,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        inputs=payload,
        dry_run=dry_run,
        attempt_id=attempt_id,
    )
    completed_at = timezone.now()
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
                "result_json": result_json,
                "error_json": {},
                "completed_at": completed_at,
            },
        )
        update_fields: list[str] = []
        if tool_execution.status != "succeeded":
            tool_execution.status = "succeeded"
            update_fields.append("status")
        if not tool_execution.result_json:
            tool_execution.result_json = result_json
            update_fields.append("result_json")
        if tool_execution.error_json:
            tool_execution.error_json = {}
            update_fields.append("error_json")
        if tool_execution.completed_at is None:
            tool_execution.completed_at = completed_at
            update_fields.append("completed_at")
        if update_fields:
            tool_execution.save(update_fields=[*update_fields, "updated_at"])
    receipt = {
        "tool_execution_id": str(tool_execution.id),
        "company_id": str(company.id),
        "operation_id": str(operation.id),
        "tool_id": tool_id,
        "label": str(tool.get("label") or tool.get("name") or tool_id),
        "dry_run": dry_run,
        "side_effects": effect,
        "status": tool_execution.status,
        "result": tool_execution.result_json,
        "error": tool_execution.error_json or None,
        "completed_at": tool_execution.completed_at.isoformat()
        if tool_execution.completed_at
        else None,
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


def _evaluate_and_enforce_policy(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    action_type: str,
    payload: dict[str, Any],
    dry_run: bool,
    policy_evaluation_id: UUID | None,
) -> PolicyEvaluation:
    evaluation = _policy_evaluation(
        company=company,
        user=user,
        operation=operation,
        action_type=action_type,
        inputs={
            **_policy_inputs_for_tool(tool_id=tool_id, inputs=payload),
            "external_write_side_effect": True,
        },
        policy_evaluation_id=policy_evaluation_id,
    )
    if evaluation.status == "blocked":
        raise PackToolExecutionError(
            "policy_blocked", "Policy evaluation blocked this side-effecting tool."
        )
    if _requires_approved_policy_gate(tool_id=tool_id, tool=tool, dry_run=dry_run, evaluation=evaluation):
        raise PackToolExecutionError(
            "approval_required",
            "This side-effecting tool requires an approved policy gate.",
        )
    return evaluation


def _requires_approved_policy_gate(
    *,
    tool_id: str,
    tool: dict[str, Any],
    dry_run: bool,
    evaluation: PolicyEvaluation,
) -> bool:
    if dry_run:
        return False
    if evaluation.status == "approval_required":
        approval = evaluation.approval_task
        return approval is None or approval.status != "approved"
    return tool_id in EMAIL_SANDBOX_TOOL_IDS and bool(tool.get("approval_required"))


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


def _tool_execution_result(
    *,
    company: Graph,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    inputs: dict[str, Any],
    dry_run: bool,
    attempt_id: str,
) -> dict[str, Any]:
    if tool_id in EMAIL_SANDBOX_TOOL_IDS:
        return _email_sandbox_result(
            company=company,
            operation=operation,
            tool_id=tool_id,
            inputs=inputs,
            dry_run=dry_run,
            attempt_id=attempt_id,
        )
    return {
        "provider": "forgegraph",
        "mode": "dry_run" if dry_run else "recorded",
        "status": "recorded",
        "tool_id": tool_id,
        "tool_label": str(tool.get("label") or tool.get("name") or tool_id),
        "related": {
            "company_id": str(company.id),
            "operation_id": str(operation.id),
            "tool_id": tool_id,
        },
    }


def _email_sandbox_result(
    *,
    company: Graph,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any],
    dry_run: bool,
    attempt_id: str,
) -> dict[str, Any]:
    subject = _clean_subject(inputs.get("subject") or inputs.get("title"))
    recipient_domains, recipient_count = _recipient_domains_and_count(inputs)
    provider = os.environ.get("EMAIL_TOOL_SANDBOX_PROVIDER", "local_capture")
    capture_id = hashlib.sha256(
        json.dumps(
            {
                "attempt_id": attempt_id,
                "company_id": str(company.id),
                "operation_id": str(operation.id),
                "tool_id": tool_id,
                "subject": subject,
                "recipient_domains": recipient_domains,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "provider": provider,
        "mode": "sandbox",
        "message_id": f"fg-email-sandbox-{capture_id}",
        "subject": subject,
        "recipient_count": recipient_count,
        "recipient_domains": recipient_domains,
        "status": "captured",
        "send_intent": "dry_run" if dry_run else "approved_sandbox_send",
        "related": {
            "company_id": str(company.id),
            "operation_id": str(operation.id),
            "tool_id": tool_id,
        },
    }


def _policy_inputs_for_tool(*, tool_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if tool_id not in EMAIL_SANDBOX_TOOL_IDS:
        return inputs
    recipient_domains, recipient_count = _recipient_domains_and_count(inputs)
    return {
        "subject": _clean_subject(inputs.get("subject") or inputs.get("title")),
        "recipient_count": recipient_count,
        "recipient_domains": recipient_domains,
        "budget": inputs.get("budget", 0),
        "channel": "email",
        "personal_data_exposure": bool(inputs.get("personal_data_exposure", False)),
        "regulated_claims": bool(inputs.get("regulated_claims", False)),
    }


def _clean_subject(value: Any) -> str:
    subject = str(value or "Untitled sandbox email").strip()
    return subject[:200]


def _recipient_domains_and_count(inputs: dict[str, Any]) -> tuple[list[str], int]:
    recipients = _recipient_values(inputs)
    domains: set[str] = set()
    count = 0
    for recipient in recipients:
        address = recipient.strip().lower()
        if not address:
            continue
        count += 1
        if "@" not in address:
            domains.add("unknown")
            continue
        domain = address.rsplit("@", 1)[1].strip(" >")
        domains.add(domain or "unknown")
    return sorted(domains), count


def _recipient_values(inputs: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("recipients", "to", "recipient_emails", "audience_emails"):
        raw = inputs.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            values.extend(part.strip() for part in raw.replace(";", ",").split(","))
            continue
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    values.append(str(item.get("email") or item.get("address") or ""))
                else:
                    values.append(str(item))
    return values


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
