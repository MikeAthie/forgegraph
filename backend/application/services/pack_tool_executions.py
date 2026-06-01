"""Generic pack-declared tool execution gates and dry-run receipts."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.email_connectors import (
    EMAIL_CONNECTOR_TOOL_IDS,
    EMAIL_MODE_DRY_RUN,
    EMAIL_MODE_REAL_SEND,
    EMAIL_SEND_DRY_RUN_TOOL_ID,
    EMAIL_SEND_TOOL_ID,
    EmailConnectorError,
    EmailSendRequest,
    dry_run_email,
    get_email_provider_adapter,
    validate_email_request,
)
from application.services.email_connectors import (
    recipient_evidence as email_recipient_evidence,
)
from application.services.email_connectors import (
    sanitize_provider_error as sanitize_email_provider_error,
)
from application.services.email_connectors import (
    validate_real_send_allowed as validate_email_real_send_allowed,
)
from application.services.operating_model_packs import OperatingModelPackError, load_pack_definition
from application.services.policy_evaluations import evaluate_policy, policy_evaluation_payload
from application.services.social_connectors import (
    SOCIAL_CONNECTOR_TOOL_IDS,
    SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID,
    SOCIAL_MODE_DRY_RUN,
    SOCIAL_MODE_MANUAL_PUBLISH_RECORD,
    SOCIAL_MODE_PROVIDER_PUBLISH,
    SOCIAL_PROVIDER_PUBLISH_TOOL_ID,
    SOCIAL_PUBLISH_DRY_RUN_TOOL_ID,
    SocialConnectorError,
    SocialPublishRequest,
    dry_run_social_publish,
    get_social_provider_adapter,
    record_manual_publish_evidence,
    validate_social_request,
)
from application.services.social_connectors import (
    sanitize_provider_error as sanitize_social_provider_error,
)
from application.services.social_connectors import (
    validate_real_publish_allowed as validate_social_real_publish_allowed,
)
from application.services.whatsapp_connectors import (
    WHATSAPP_CONNECTOR_TOOL_IDS,
    WHATSAPP_MODE_DRY_RUN,
    WHATSAPP_MODE_MANUAL_OPS,
    WHATSAPP_MODE_REAL_SEND,
    WHATSAPP_SEND_DRY_RUN_TOOL_ID,
    WHATSAPP_SEND_MANUAL_TOOL_ID,
    WHATSAPP_WEB_AUTOMATION_SEND_TOOL_ID,
    WhatsAppConnectorError,
    WhatsAppSendRequest,
    dry_run_whatsapp,
    get_whatsapp_provider_adapter,
    manual_ops_whatsapp,
    validate_whatsapp_request,
)
from application.services.whatsapp_connectors import (
    recipient_evidence as whatsapp_recipient_evidence,
)
from application.services.whatsapp_connectors import (
    sanitize_provider_error as sanitize_whatsapp_provider_error,
)
from application.services.whatsapp_connectors import (
    validate_real_send_allowed as validate_whatsapp_real_send_allowed,
)
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    Graph,
    PolicyEvaluation,
    Run,
    ToolExecution,
    User,
)

EMAIL_CONNECTOR_COMPAT_TOOL_IDS = {"dmp.email_draft_send_schedule", "email_service_connector"}
EMAIL_EXECUTION_TOOL_IDS = set(EMAIL_CONNECTOR_TOOL_IDS) | EMAIL_CONNECTOR_COMPAT_TOOL_IDS
EMAIL_SANDBOX_TOOL_IDS = set(EMAIL_EXECUTION_TOOL_IDS)
WHATSAPP_CONNECTOR_COMPAT_TOOL_IDS = {"messaging.whatsapp_template_send"}
WHATSAPP_EXECUTION_TOOL_IDS = set(WHATSAPP_CONNECTOR_TOOL_IDS) | WHATSAPP_CONNECTOR_COMPAT_TOOL_IDS
SOCIAL_CONNECTOR_COMPAT_TOOL_IDS = {
    "social.instagram_publish",
    "social.facebook_publish",
    "social.instagram_publish_dry_run",
    "social.facebook_publish_dry_run",
    "social.instagram_provider_publish",
    "social.facebook_provider_publish",
}
SOCIAL_EXECUTION_TOOL_IDS = set(SOCIAL_CONNECTOR_TOOL_IDS) | SOCIAL_CONNECTOR_COMPAT_TOOL_IDS
CONNECTOR_EXECUTION_TOOL_IDS = (
    set(EMAIL_EXECUTION_TOOL_IDS)
    | set(WHATSAPP_EXECUTION_TOOL_IDS)
    | set(SOCIAL_EXECUTION_TOOL_IDS)
)
DEPLOYMENT_EVIDENCE_TOOL_IDS = set(CONNECTOR_EXECUTION_TOOL_IDS)

_BUILT_IN_EMAIL_TOOLS: dict[str, dict[str, Any]] = {
    EMAIL_SEND_DRY_RUN_TOOL_ID: {
        "id": EMAIL_SEND_DRY_RUN_TOOL_ID,
        "label": "Email Send Dry Run",
        "category": "email",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": True,
        "policy_action_type": "send_email",
        "pack_id": "forgegraph.email_connector",
    },
    EMAIL_SEND_TOOL_ID: {
        "id": EMAIL_SEND_TOOL_ID,
        "label": "Email Send",
        "category": "email",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": False,
        "policy_action_type": "send_email",
        "pack_id": "forgegraph.email_connector",
    },
}

_BUILT_IN_WHATSAPP_TOOLS: dict[str, dict[str, Any]] = {
    WHATSAPP_SEND_DRY_RUN_TOOL_ID: {
        "id": WHATSAPP_SEND_DRY_RUN_TOOL_ID,
        "label": "Messaging Send Dry Run",
        "category": "messaging",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": True,
        "policy_action_type": "send_message",
        "pack_id": "forgegraph.messaging_connector",
    },
    WHATSAPP_SEND_MANUAL_TOOL_ID: {
        "id": WHATSAPP_SEND_MANUAL_TOOL_ID,
        "label": "Messaging Manual Evidence",
        "category": "messaging",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": True,
        "policy_action_type": "send_message",
        "pack_id": "forgegraph.messaging_connector",
    },
    WHATSAPP_WEB_AUTOMATION_SEND_TOOL_ID: {
        "id": WHATSAPP_WEB_AUTOMATION_SEND_TOOL_ID,
        "label": "Messaging Web Automation Send",
        "category": "messaging",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": False,
        "policy_action_type": "send_message",
        "pack_id": "forgegraph.messaging_connector",
    },
}

_BUILT_IN_SOCIAL_TOOLS: dict[str, dict[str, Any]] = {
    SOCIAL_PUBLISH_DRY_RUN_TOOL_ID: {
        "id": SOCIAL_PUBLISH_DRY_RUN_TOOL_ID,
        "label": "Social Publish Dry Run",
        "category": "social",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": True,
        "policy_action_type": "publish_social",
        "pack_id": "forgegraph.social_connector",
    },
    SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID: {
        "id": SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID,
        "label": "Social Manual Evidence",
        "category": "social",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": True,
        "policy_action_type": "publish_social",
        "pack_id": "forgegraph.social_connector",
    },
    SOCIAL_PROVIDER_PUBLISH_TOOL_ID: {
        "id": SOCIAL_PROVIDER_PUBLISH_TOOL_ID,
        "label": "Social Provider Publish",
        "category": "social",
        "side_effects": "external",
        "approval_required": True,
        "dry_run": False,
        "policy_action_type": "publish_social",
        "pack_id": "forgegraph.social_connector",
    },
}


class PackToolExecutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def execute_pack_tool(  # noqa: C901
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    policy_evaluation_id: UUID | None = None,
    idempotency_key: str = "",
    approved: bool = False,
    approval_id: str = "",
    policy_allows_live: bool = False,
    requires_unsubscribe_footer: bool = False,
    policy_allows_web_automation_evidence: bool = False,
    policy_allows_manual_publish_evidence: bool = False,
    policy_allows_provider_publish: bool = False,
    requires_compliance_gate: bool = False,
    requires_originality_check: bool = False,
    operator_confirmed: bool = False,
) -> dict[str, Any]:
    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    effect = str(tool.get("side_effects") or "none").lower()
    side_effecting = effect not in {"", "none", "read", "false"}
    action_type = str(tool.get("policy_action_type") or tool.get("category") or tool_id)
    payload = dict(inputs or {})
    policy_evaluation = None
    deployment_approved_connector_send = (
        _is_managed_connector_tool(tool_id)
        and not dry_run
        and bool(approved)
        and bool(policy_allows_live)
    )
    if side_effecting and not deployment_approved_connector_send:
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

    attempt_id = (
        _connector_attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload)
        if _is_managed_connector_tool(tool_id)
        else _attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload)
    )
    side_effect_class = _side_effect_class(effect=effect, dry_run=dry_run)
    if _is_email_tool(tool_id):
        return _execute_email_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=policy_evaluation,
            approved=approved,
            approval_id=approval_id,
            policy_allows_live=policy_allows_live,
            requires_unsubscribe_footer=requires_unsubscribe_footer,
        )
    if _is_whatsapp_tool(tool_id):
        return _execute_whatsapp_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=policy_evaluation,
            approved=approved,
            approval_id=approval_id,
            policy_allows_live=policy_allows_live,
            operator_confirmed=operator_confirmed,
            policy_allows_web_automation_evidence=policy_allows_web_automation_evidence,
        )
    if _is_social_tool(tool_id):
        return _execute_social_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=policy_evaluation,
            approved=approved,
            approval_id=approval_id,
            policy_allows_provider_publish=policy_allows_provider_publish or policy_allows_live,
            policy_allows_manual_publish_evidence=policy_allows_manual_publish_evidence,
            requires_compliance_gate=requires_compliance_gate,
            requires_originality_check=requires_originality_check,
            operator_confirmed=operator_confirmed,
        )
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


def execute_email_connector_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    idempotency_key: str = "",
    approved: bool = False,
    approval_id: str = "",
    policy_allows_live: bool = False,
    requires_unsubscribe_footer: bool = False,
) -> dict[str, Any]:
    """Execute the built-in email connector without creating a second policy gate."""

    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    if not _is_email_tool(tool_id):
        raise PackToolExecutionError("tool_not_found", "Tool is not an email connector tool.")
    payload = dict(inputs or {})
    attempt_id = _connector_attempt_id(
        idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload
    )
    return _execute_email_tool(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        inputs=payload,
        dry_run=dry_run,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        side_effect_class=_side_effect_class(
            effect=str(tool.get("side_effects") or "external"), dry_run=dry_run
        ),
        policy_evaluation=None,
        approved=approved,
        approval_id=approval_id,
        policy_allows_live=policy_allows_live,
        requires_unsubscribe_footer=requires_unsubscribe_footer,
    )


def execute_deployment_connector_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    idempotency_key: str = "",
    approved: bool = False,
    approval_id: str = "",
    policy_allows_live: bool = False,
    requires_unsubscribe_footer: bool = False,
    operator_confirmed: bool = False,
    policy_allows_web_automation_evidence: bool = False,
    policy_allows_manual_publish_evidence: bool = False,
    policy_allows_provider_publish: bool = False,
    requires_compliance_gate: bool = False,
    requires_originality_check: bool = False,
) -> dict[str, Any]:
    """Execute a built-in deployment connector without creating a second policy gate."""

    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    if not _is_managed_connector_tool(tool_id):
        raise PackToolExecutionError("tool_not_found", "Tool is not a managed connector tool.")
    payload = dict(inputs or {})
    attempt_id = _connector_attempt_id(
        idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload
    )
    side_effect_class = _side_effect_class(
        effect=str(tool.get("side_effects") or "external"), dry_run=dry_run
    )
    if _is_email_tool(tool_id):
        return _execute_email_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=None,
            approved=approved,
            approval_id=approval_id,
            policy_allows_live=policy_allows_live,
            requires_unsubscribe_footer=requires_unsubscribe_footer,
        )
    if _is_whatsapp_tool(tool_id):
        return _execute_whatsapp_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=None,
            approved=approved,
            approval_id=approval_id,
            policy_allows_live=policy_allows_live,
            operator_confirmed=operator_confirmed,
            policy_allows_web_automation_evidence=policy_allows_web_automation_evidence,
        )
    if _is_social_tool(tool_id):
        return _execute_social_tool(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            inputs=payload,
            dry_run=dry_run,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            side_effect_class=side_effect_class,
            policy_evaluation=None,
            approved=approved,
            approval_id=approval_id,
            policy_allows_provider_publish=policy_allows_provider_publish or policy_allows_live,
            policy_allows_manual_publish_evidence=policy_allows_manual_publish_evidence,
            requires_compliance_gate=requires_compliance_gate,
            requires_originality_check=requires_originality_check,
            operator_confirmed=operator_confirmed,
        )
    raise PackToolExecutionError("tool_not_found", "Tool is not a managed connector tool.")


def execute_whatsapp_connector_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    idempotency_key: str = "",
    approved: bool = False,
    approval_id: str = "",
    policy_allows_live: bool = False,
    operator_confirmed: bool = False,
    policy_allows_web_automation_evidence: bool = False,
) -> dict[str, Any]:
    """Execute the built-in messaging connector for focused service tests."""

    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    if not _is_whatsapp_tool(tool_id):
        raise PackToolExecutionError("tool_not_found", "Tool is not a messaging connector tool.")
    payload = dict(inputs or {})
    attempt_id = _connector_attempt_id(
        idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload
    )
    return _execute_whatsapp_tool(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        inputs=payload,
        dry_run=dry_run,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        side_effect_class=_side_effect_class(
            effect=str(tool.get("side_effects") or "external"), dry_run=dry_run
        ),
        policy_evaluation=None,
        approved=approved,
        approval_id=approval_id,
        policy_allows_live=policy_allows_live,
        operator_confirmed=operator_confirmed,
        policy_allows_web_automation_evidence=policy_allows_web_automation_evidence,
    )


def execute_social_connector_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
    idempotency_key: str = "",
    approved: bool = False,
    approval_id: str = "",
    policy_allows_provider_publish: bool = False,
    policy_allows_manual_publish_evidence: bool = False,
    requires_compliance_gate: bool = False,
    requires_originality_check: bool = False,
    operator_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute the built-in social connector for focused service tests."""

    if operation.graph_version.graph_id != company.id:
        raise PackToolExecutionError("operation_not_found", "Operation was not found.")
    tool = _tool_definition(company=company, tool_id=tool_id)
    if not _is_social_tool(tool_id):
        raise PackToolExecutionError("tool_not_found", "Tool is not a social connector tool.")
    payload = dict(inputs or {})
    attempt_id = _connector_attempt_id(
        idempotency_key=idempotency_key, tool_id=tool_id, inputs=payload
    )
    return _execute_social_tool(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        inputs=payload,
        dry_run=dry_run,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        side_effect_class=_side_effect_class(
            effect=str(tool.get("side_effects") or "external"), dry_run=dry_run
        ),
        policy_evaluation=None,
        approved=approved,
        approval_id=approval_id,
        policy_allows_provider_publish=policy_allows_provider_publish,
        policy_allows_manual_publish_evidence=policy_allows_manual_publish_evidence,
        requires_compliance_gate=requires_compliance_gate,
        requires_originality_check=requires_originality_check,
        operator_confirmed=operator_confirmed,
    )


def _execute_email_tool(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    inputs: dict[str, Any],
    dry_run: bool,
    attempt_id: str,
    idempotency_key: str,
    side_effect_class: str,
    policy_evaluation: PolicyEvaluation | None,
    approved: bool,
    approval_id: str,
    policy_allows_live: bool,
    requires_unsubscribe_footer: bool,
) -> dict[str, Any]:
    request = _email_request_from_inputs(
        inputs=inputs,
        dry_run=dry_run,
        idempotency_key=idempotency_key or attempt_id,
        approval_id=approval_id,
        requires_unsubscribe_footer=requires_unsubscribe_footer,
    )
    existing_execution = ToolExecution.objects.filter(
        run=operation,
        node_id=f"pack_tool:{tool_id}"[:255],
        attempt_id=attempt_id,
    ).first()
    if existing_execution is not None and existing_execution.status in {
        "succeeded",
        "failed",
        "ambiguous",
    }:
        return _email_receipt_payload(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            dry_run=dry_run,
            tool_execution=existing_execution,
            policy_evaluation=policy_evaluation,
        )
    if existing_execution is not None and existing_execution.status == "in_progress":
        raise PackToolExecutionError(
            "email_send_in_progress",
            "Email send with this idempotency key is already in progress.",
        )
    if dry_run:
        try:
            validate_email_request(request, dry_run=True)
        except EmailConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc
    else:
        try:
            adapter = get_email_provider_adapter(request.provider)
            validate_email_request(request, dry_run=False)
            validate_email_real_send_allowed(
                request,
                approved=approved or _policy_evaluation_approved(policy_evaluation),
                policy_allows_live=policy_allows_live,
                adapter=adapter,
            )
        except EmailConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc

    with transaction.atomic():
        tool_execution, created = ToolExecution.objects.select_for_update().get_or_create(
            run=operation,
            node_id=f"pack_tool:{tool_id}"[:255],
            attempt_id=attempt_id,
            defaults={
                "tool_name": tool_id[:128],
                "tool_version": str(tool.get("pack_id") or "")[:64],
                "idempotency_key": (idempotency_key or attempt_id)[:128],
                "side_effect_class": side_effect_class,
                "status": "in_progress" if not dry_run else "planned",
                "result_json": {},
                "error_json": {},
            },
        )
        if not created and tool_execution.status in {"succeeded", "failed", "ambiguous"}:
            return _email_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )
        if not created and tool_execution.status == "in_progress":
            raise PackToolExecutionError(
                "email_send_in_progress",
                "Email send with this idempotency key is already in progress.",
            )

    if dry_run:
        receipt_json = dry_run_email(request).as_dict()
        completed_at = timezone.now()
        with transaction.atomic():
            tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
            tool_execution.status = "succeeded"
            tool_execution.result_json = receipt_json
            tool_execution.error_json = {}
            tool_execution.completed_at = completed_at
            tool_execution.save(
                update_fields=["status", "result_json", "error_json", "completed_at", "updated_at"]
            )
        return _email_receipt_payload(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            dry_run=dry_run,
            tool_execution=tool_execution,
            policy_evaluation=policy_evaluation,
        )

    try:
        receipt_json = adapter.send(request).as_dict()
    except Exception as exc:  # noqa: BLE001 - provider errors must become durable receipts.
        error_json = sanitize_email_provider_error(
            exc, provider=request.provider, mode=EMAIL_MODE_REAL_SEND
        )
        completed_at = timezone.now()
        with transaction.atomic():
            tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
            tool_execution.status = "failed"
            tool_execution.result_json = {}
            tool_execution.error_json = error_json
            tool_execution.completed_at = completed_at
            tool_execution.save(
                update_fields=["status", "result_json", "error_json", "completed_at", "updated_at"]
            )
        return _email_receipt_payload(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            dry_run=dry_run,
            tool_execution=tool_execution,
            policy_evaluation=policy_evaluation,
        )

    completed_at = timezone.now()
    with transaction.atomic():
        tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
        tool_execution.status = "succeeded"
        tool_execution.result_json = receipt_json
        tool_execution.error_json = {}
        tool_execution.completed_at = completed_at
        tool_execution.save(
            update_fields=["status", "result_json", "error_json", "completed_at", "updated_at"]
        )
    return _email_receipt_payload(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        dry_run=dry_run,
        tool_execution=tool_execution,
        policy_evaluation=policy_evaluation,
    )


def _execute_whatsapp_tool(  # noqa: C901
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    inputs: dict[str, Any],
    dry_run: bool,
    attempt_id: str,
    idempotency_key: str,
    side_effect_class: str,
    policy_evaluation: PolicyEvaluation | None,
    approved: bool,
    approval_id: str,
    policy_allows_live: bool,
    operator_confirmed: bool,
    policy_allows_web_automation_evidence: bool,
) -> dict[str, Any]:
    mode = _whatsapp_mode_for_tool(tool_id=tool_id, dry_run=dry_run)
    request = _whatsapp_request_from_inputs(
        inputs=inputs,
        mode=mode,
        idempotency_key=idempotency_key or attempt_id,
        approval_id=approval_id,
        operator_confirmed=operator_confirmed,
    )
    existing_execution = ToolExecution.objects.filter(
        run=operation,
        node_id=f"pack_tool:{tool_id}"[:255],
        attempt_id=attempt_id,
    ).first()
    if existing_execution is not None and existing_execution.status in {
        "succeeded",
        "failed",
        "ambiguous",
    }:
        return _whatsapp_receipt_payload(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            dry_run=dry_run,
            tool_execution=existing_execution,
            policy_evaluation=policy_evaluation,
        )
    if existing_execution is not None and existing_execution.status == "in_progress":
        raise PackToolExecutionError(
            "message_send_in_progress",
            "Messaging send with this idempotency key is already in progress.",
        )

    if mode == WHATSAPP_MODE_MANUAL_OPS and not policy_allows_web_automation_evidence:
        raise PackToolExecutionError(
            "web_automation_evidence_not_allowed",
            "Policy does not allow web automation evidence for this connector.",
        )
    if mode in {WHATSAPP_MODE_DRY_RUN, WHATSAPP_MODE_MANUAL_OPS}:
        try:
            validate_whatsapp_request(request, dry_run=True)
        except WhatsAppConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc
    else:
        try:
            adapter = get_whatsapp_provider_adapter(request.provider)
            validate_whatsapp_request(request, dry_run=False)
            validate_whatsapp_real_send_allowed(
                request,
                approved=approved or _policy_evaluation_approved(policy_evaluation),
                policy_allows_live=policy_allows_live,
                adapter=adapter,
            )
        except WhatsAppConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc

    with transaction.atomic():
        tool_execution, created = ToolExecution.objects.select_for_update().get_or_create(
            run=operation,
            node_id=f"pack_tool:{tool_id}"[:255],
            attempt_id=attempt_id,
            defaults={
                "tool_name": tool_id[:128],
                "tool_version": str(tool.get("pack_id") or "")[:64],
                "idempotency_key": (idempotency_key or attempt_id)[:128],
                "side_effect_class": side_effect_class,
                "status": "in_progress" if mode == WHATSAPP_MODE_REAL_SEND else "planned",
                "result_json": {},
                "error_json": {},
            },
        )
        if not created and tool_execution.status in {"succeeded", "failed", "ambiguous"}:
            return _whatsapp_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )
        if not created and tool_execution.status == "in_progress":
            raise PackToolExecutionError(
                "message_send_in_progress",
                "Messaging send with this idempotency key is already in progress.",
            )

    if mode == WHATSAPP_MODE_DRY_RUN:
        receipt_json = dry_run_whatsapp(request).as_dict()
    elif mode == WHATSAPP_MODE_MANUAL_OPS:
        receipt_json = manual_ops_whatsapp(request).as_dict()
    else:
        try:
            receipt_json = adapter.send(request).as_dict()
        except WhatsAppConnectorError as exc:
            if exc.blocked_before_provider_call:
                ToolExecution.objects.filter(id=tool_execution.id).delete()
                raise PackToolExecutionError(exc.code, exc.message) from exc
            error_json = sanitize_whatsapp_provider_error(
                exc,
                provider=request.provider,
                mode=WHATSAPP_MODE_REAL_SEND,
            )
            completed_at = timezone.now()
            with transaction.atomic():
                tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
                tool_execution.status = "failed"
                tool_execution.result_json = {}
                tool_execution.error_json = error_json
                tool_execution.completed_at = completed_at
                tool_execution.save(
                    update_fields=[
                        "status",
                        "result_json",
                        "error_json",
                        "completed_at",
                        "updated_at",
                    ]
                )
            return _whatsapp_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors must become durable receipts.
            error_json = sanitize_whatsapp_provider_error(
                exc,
                provider=request.provider,
                mode=WHATSAPP_MODE_REAL_SEND,
            )
            completed_at = timezone.now()
            with transaction.atomic():
                tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
                tool_execution.status = "failed"
                tool_execution.result_json = {}
                tool_execution.error_json = error_json
                tool_execution.completed_at = completed_at
                tool_execution.save(
                    update_fields=[
                        "status",
                        "result_json",
                        "error_json",
                        "completed_at",
                        "updated_at",
                    ]
                )
            return _whatsapp_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )

    completed_at = timezone.now()
    with transaction.atomic():
        tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
        tool_execution.status = "succeeded"
        tool_execution.result_json = receipt_json
        tool_execution.error_json = {}
        tool_execution.completed_at = completed_at
        tool_execution.save(
            update_fields=["status", "result_json", "error_json", "completed_at", "updated_at"]
        )
    return _whatsapp_receipt_payload(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        dry_run=dry_run,
        tool_execution=tool_execution,
        policy_evaluation=policy_evaluation,
    )


def _execute_social_tool(  # noqa: C901
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    inputs: dict[str, Any],
    dry_run: bool,
    attempt_id: str,
    idempotency_key: str,
    side_effect_class: str,
    policy_evaluation: PolicyEvaluation | None,
    approved: bool,
    approval_id: str,
    policy_allows_provider_publish: bool,
    policy_allows_manual_publish_evidence: bool,
    requires_compliance_gate: bool,
    requires_originality_check: bool,
    operator_confirmed: bool,
) -> dict[str, Any]:
    mode = _social_mode_for_tool(tool_id=tool_id, dry_run=dry_run)
    request = _social_request_from_inputs(
        inputs=inputs,
        mode=mode,
        idempotency_key=idempotency_key or attempt_id,
        approval_id=approval_id,
        requires_compliance_gate=requires_compliance_gate,
        requires_originality_check=requires_originality_check,
        operator_confirmed=operator_confirmed,
    )
    existing_execution = ToolExecution.objects.filter(
        run=operation,
        node_id=f"pack_tool:{tool_id}"[:255],
        attempt_id=attempt_id,
    ).first()
    if existing_execution is not None and existing_execution.status in {
        "succeeded",
        "failed",
        "ambiguous",
    }:
        return _social_receipt_payload(
            company=company,
            user=user,
            operation=operation,
            tool_id=tool_id,
            tool=tool,
            dry_run=dry_run,
            tool_execution=existing_execution,
            policy_evaluation=policy_evaluation,
        )
    if existing_execution is not None and existing_execution.status == "in_progress":
        raise PackToolExecutionError(
            "social_publish_in_progress",
            "Social publish with this idempotency key is already in progress.",
        )

    if mode == SOCIAL_MODE_MANUAL_PUBLISH_RECORD and not policy_allows_manual_publish_evidence:
        raise PackToolExecutionError(
            "manual_publish_evidence_not_allowed",
            "Policy does not allow manual social publish evidence for this connector.",
        )
    if mode in {SOCIAL_MODE_DRY_RUN, SOCIAL_MODE_MANUAL_PUBLISH_RECORD}:
        try:
            validate_social_request(request, dry_run=True)
        except SocialConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc
    else:
        try:
            adapter = get_social_provider_adapter(request.provider)
            validate_social_request(request, dry_run=False)
            validate_social_real_publish_allowed(
                request,
                approved=approved or _policy_evaluation_approved(policy_evaluation),
                policy_allows_provider_publish=policy_allows_provider_publish,
                adapter=adapter,
            )
        except SocialConnectorError as exc:
            raise PackToolExecutionError(exc.code, exc.message) from exc

    with transaction.atomic():
        tool_execution, created = ToolExecution.objects.select_for_update().get_or_create(
            run=operation,
            node_id=f"pack_tool:{tool_id}"[:255],
            attempt_id=attempt_id,
            defaults={
                "tool_name": tool_id[:128],
                "tool_version": str(tool.get("pack_id") or "")[:64],
                "idempotency_key": (idempotency_key or attempt_id)[:128],
                "side_effect_class": side_effect_class,
                "status": "in_progress" if mode == SOCIAL_MODE_PROVIDER_PUBLISH else "planned",
                "result_json": {},
                "error_json": {},
            },
        )
        if not created and tool_execution.status in {"succeeded", "failed", "ambiguous"}:
            return _social_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )
        if not created and tool_execution.status == "in_progress":
            raise PackToolExecutionError(
                "social_publish_in_progress",
                "Social publish with this idempotency key is already in progress.",
            )

    if mode == SOCIAL_MODE_DRY_RUN:
        receipt_json = dry_run_social_publish(request).as_dict()
    elif mode == SOCIAL_MODE_MANUAL_PUBLISH_RECORD:
        try:
            receipt_json = record_manual_publish_evidence(request).as_dict()
        except SocialConnectorError as exc:
            ToolExecution.objects.filter(id=tool_execution.id).delete()
            raise PackToolExecutionError(exc.code, exc.message) from exc
    else:
        try:
            adapter = get_social_provider_adapter(request.provider)
            receipt_json = adapter.publish(request).as_dict()
        except SocialConnectorError as exc:
            if exc.blocked_before_provider_call:
                ToolExecution.objects.filter(id=tool_execution.id).delete()
                raise PackToolExecutionError(exc.code, exc.message) from exc
            error_json = sanitize_social_provider_error(
                exc,
                provider=request.provider,
                mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            )
            completed_at = timezone.now()
            with transaction.atomic():
                tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
                tool_execution.status = "failed"
                tool_execution.result_json = {}
                tool_execution.error_json = error_json
                tool_execution.completed_at = completed_at
                tool_execution.save(
                    update_fields=[
                        "status",
                        "result_json",
                        "error_json",
                        "completed_at",
                        "updated_at",
                    ]
                )
            return _social_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors must become durable receipts.
            error_json = sanitize_social_provider_error(
                exc,
                provider=request.provider,
                mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            )
            completed_at = timezone.now()
            with transaction.atomic():
                tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
                tool_execution.status = "failed"
                tool_execution.result_json = {}
                tool_execution.error_json = error_json
                tool_execution.completed_at = completed_at
                tool_execution.save(
                    update_fields=[
                        "status",
                        "result_json",
                        "error_json",
                        "completed_at",
                        "updated_at",
                    ]
                )
            return _social_receipt_payload(
                company=company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                tool=tool,
                dry_run=dry_run,
                tool_execution=tool_execution,
                policy_evaluation=policy_evaluation,
            )

    completed_at = timezone.now()
    with transaction.atomic():
        tool_execution = ToolExecution.objects.select_for_update().get(id=tool_execution.id)
        tool_execution.status = "succeeded"
        tool_execution.result_json = receipt_json
        tool_execution.error_json = {}
        tool_execution.completed_at = completed_at
        tool_execution.save(
            update_fields=["status", "result_json", "error_json", "completed_at", "updated_at"]
        )
    return _social_receipt_payload(
        company=company,
        user=user,
        operation=operation,
        tool_id=tool_id,
        tool=tool,
        dry_run=dry_run,
        tool_execution=tool_execution,
        policy_evaluation=policy_evaluation,
    )


def _email_receipt_payload(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    dry_run: bool,
    tool_execution: ToolExecution,
    policy_evaluation: PolicyEvaluation | None,
) -> dict[str, Any]:
    receipt = {
        "tool_execution_id": str(tool_execution.id),
        "company_id": str(company.id),
        "operation_id": str(operation.id),
        "tool_id": tool_id,
        "label": str(tool.get("label") or tool.get("name") or tool_id),
        "dry_run": dry_run,
        "side_effects": str(tool.get("side_effects") or "external"),
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


def _whatsapp_receipt_payload(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    dry_run: bool,
    tool_execution: ToolExecution,
    policy_evaluation: PolicyEvaluation | None,
) -> dict[str, Any]:
    receipt = {
        "tool_execution_id": str(tool_execution.id),
        "company_id": str(company.id),
        "operation_id": str(operation.id),
        "tool_id": tool_id,
        "label": str(tool.get("label") or tool.get("name") or tool_id),
        "dry_run": dry_run,
        "side_effects": str(tool.get("side_effects") or "external"),
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


def _social_receipt_payload(
    *,
    company: Graph,
    user: User,
    operation: Run,
    tool_id: str,
    tool: dict[str, Any],
    dry_run: bool,
    tool_execution: ToolExecution,
    policy_evaluation: PolicyEvaluation | None,
) -> dict[str, Any]:
    receipt = {
        "tool_execution_id": str(tool_execution.id),
        "company_id": str(company.id),
        "operation_id": str(operation.id),
        "tool_id": tool_id,
        "label": str(tool.get("label") or tool.get("name") or tool_id),
        "dry_run": dry_run,
        "side_effects": str(tool.get("side_effects") or "external"),
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
    if _requires_approved_policy_gate(
        tool_id=tool_id, tool=tool, dry_run=dry_run, evaluation=evaluation
    ):
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
    return tool_id in CONNECTOR_EXECUTION_TOOL_IDS and bool(tool.get("approval_required"))


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


def _tool_definition(*, company: Graph, tool_id: str) -> dict[str, Any]:  # noqa: C901
    if tool_id in _BUILT_IN_EMAIL_TOOLS:
        return dict(_BUILT_IN_EMAIL_TOOLS[tool_id])
    if tool_id in _BUILT_IN_WHATSAPP_TOOLS:
        return dict(_BUILT_IN_WHATSAPP_TOOLS[tool_id])
    if tool_id in _BUILT_IN_SOCIAL_TOOLS:
        return dict(_BUILT_IN_SOCIAL_TOOLS[tool_id])
    if _is_email_tool_alias(tool_id):
        return {**_BUILT_IN_EMAIL_TOOLS[EMAIL_SEND_DRY_RUN_TOOL_ID], "id": tool_id}
    if _is_whatsapp_tool_alias(tool_id):
        return {**_BUILT_IN_WHATSAPP_TOOLS[WHATSAPP_SEND_DRY_RUN_TOOL_ID], "id": tool_id}
    if _is_social_tool_alias(tool_id):
        built_in_id = (
            SOCIAL_PROVIDER_PUBLISH_TOOL_ID
            if _social_alias_is_provider_publish(tool_id)
            else SOCIAL_PUBLISH_DRY_RUN_TOOL_ID
        )
        return {**_BUILT_IN_SOCIAL_TOOLS[built_in_id], "id": tool_id}
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
                    return {**tool, "pack_id": definition.pack_id}
                if (
                    _is_email_tool_alias(tool_id)
                    and isinstance(tool, dict)
                    and str(tool.get("id") or "") in EMAIL_CONNECTOR_TOOL_IDS
                ):
                    return {**tool, "pack_id": definition.pack_id}
                if (
                    _is_whatsapp_tool_alias(tool_id)
                    and isinstance(tool, dict)
                    and str(tool.get("id") or "") in WHATSAPP_CONNECTOR_TOOL_IDS
                ):
                    return {**tool, "pack_id": definition.pack_id}
                if (
                    _is_social_tool_alias(tool_id)
                    and isinstance(tool, dict)
                    and str(tool.get("id") or "") in SOCIAL_CONNECTOR_TOOL_IDS
                ):
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


def _policy_inputs_for_tool(*, tool_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if _is_email_tool(tool_id):
        evidence = email_recipient_evidence(_recipient_values(inputs), allowlist_matched=False)
        return {
            "subject": _clean_subject(inputs.get("subject") or inputs.get("title")),
            "recipient_count": evidence["recipient_count"],
            "recipient_domains": evidence["recipient_domains"],
            "recipient_hashes": evidence["recipient_hashes"],
            "budget": inputs.get("budget", 0),
            "personal_data_exposure": bool(inputs.get("personal_data_exposure", False)),
            "regulated_claims": bool(inputs.get("regulated_claims", False)),
        }
    if _is_whatsapp_tool(tool_id):
        evidence = whatsapp_recipient_evidence(
            _whatsapp_recipient_values(inputs), allowlist_matched=False
        )
        message = str(inputs.get("text") or inputs.get("message") or inputs.get("body") or "")
        return {
            "recipient_count": evidence["recipient_count"],
            "recipient_domains": evidence["recipient_domains"],
            "recipient_hashes": evidence["recipient_hashes"],
            "message_length": min(len(message), 10000),
            "personal_data_exposure": bool(inputs.get("personal_data_exposure", False)),
            "regulated_claims": bool(inputs.get("regulated_claims", False)),
        }
    if _is_social_tool(tool_id):
        caption = str(inputs.get("caption") or inputs.get("text") or inputs.get("body") or "")
        account = _social_target_account(inputs)
        return {
            "platform": str(inputs.get("platform") or "")[:80],
            "asset_count": len(_social_asset_ids(inputs)),
            "asset_ids": _social_asset_ids(inputs),
            "caption_hash": _hash_social_value(caption),
            "caption_length": min(len(caption), 10000),
            "account_id_hash": _hash_social_value(account),
            "personal_data_exposure": bool(inputs.get("personal_data_exposure", False)),
            "regulated_claims": bool(inputs.get("regulated_claims", False)),
        }
    if tool_id not in CONNECTOR_EXECUTION_TOOL_IDS:
        return inputs
    return {}


def _email_request_from_inputs(
    *,
    inputs: dict[str, Any],
    dry_run: bool,
    idempotency_key: str,
    approval_id: str,
    requires_unsubscribe_footer: bool,
) -> EmailSendRequest:
    metadata = {
        key: inputs.get(key)
        for key in (
            "policy_id",
            "source_policy_id",
            "pack_id",
            "channel_id",
            "metric_source_id",
        )
        if inputs.get(key)
    }
    raw_metadata = inputs.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    from_email = (
        inputs.get("from_email")
        or inputs.get("sender_email")
        or _email_from_friendly_address(str(inputs.get("from") or ""))
        or getattr(settings, "EMAIL_CONNECTOR_DEFAULT_FROM_EMAIL", "")
    )
    return EmailSendRequest(
        provider=str(
            inputs.get("provider")
            or getattr(settings, "EMAIL_CONNECTOR_PROVIDER", "fake")
            or "fake"
        ),
        mode=EMAIL_MODE_DRY_RUN if dry_run else EMAIL_MODE_REAL_SEND,
        from_email=str(from_email or "").strip(),
        from_name=str(
            inputs.get("from_name")
            or inputs.get("sender_name")
            or getattr(settings, "EMAIL_CONNECTOR_DEFAULT_FROM_NAME", "")
            or ""
        ).strip(),
        to=_recipient_values(inputs),
        cc=_address_values(inputs, "cc"),
        bcc=_address_values(inputs, "bcc"),
        subject=_clean_subject(inputs.get("subject") or inputs.get("title")),
        html=str(inputs.get("html") or inputs.get("body_html") or ""),
        text=str(inputs.get("text") or inputs.get("body") or inputs.get("message") or ""),
        metadata=metadata,
        idempotency_key=(idempotency_key or "")[:128],
        approval_id=approval_id or _optional_str(inputs.get("approval_id")),
        whiteboard_id=_optional_str(inputs.get("whiteboard_id")),
        deployment_channel_id=_optional_str(
            inputs.get("deployment_channel_id") or inputs.get("channel_id")
        ),
        asset_id=_optional_str(inputs.get("asset_id")),
        publication_draft_id=_optional_str(inputs.get("publication_draft_id")),
        allow_cc=bool(inputs.get("allow_cc", False)),
        allow_bcc=bool(inputs.get("allow_bcc", False)),
        requires_unsubscribe_footer=requires_unsubscribe_footer,
    )


def _whatsapp_request_from_inputs(
    *,
    inputs: dict[str, Any],
    mode: str,
    idempotency_key: str,
    approval_id: str,
    operator_confirmed: bool,
) -> WhatsAppSendRequest:
    metadata = {
        key: inputs.get(key)
        for key in (
            "policy_id",
            "source_policy_id",
            "pack_id",
            "channel_id",
            "metric_source_id",
        )
        if inputs.get(key)
    }
    raw_metadata = inputs.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    return WhatsAppSendRequest(
        provider=str(
            inputs.get("provider")
            or getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "fake")
            or "fake"
        ),
        mode=mode,
        to=_whatsapp_recipient_values(inputs),
        text=str(inputs.get("text") or inputs.get("message") or inputs.get("body") or ""),
        metadata=metadata,
        idempotency_key=(idempotency_key or "")[:128],
        approval_id=approval_id or _optional_str(inputs.get("approval_id")),
        whiteboard_id=_optional_str(inputs.get("whiteboard_id")),
        deployment_channel_id=_optional_str(
            inputs.get("deployment_channel_id") or inputs.get("channel_id")
        ),
        asset_id=_optional_str(inputs.get("asset_id")),
        publication_draft_id=_optional_str(inputs.get("publication_draft_id")),
        operator_confirmed=bool(
            operator_confirmed
            or inputs.get("operator_confirmed")
            or inputs.get("operator_confirmation")
            or inputs.get("manual_operator_confirmed")
        ),
        session_ref=getattr(settings, "WHATSAPP_WEB_AUTOMATION_SESSION_REF", ""),
    )


def _social_request_from_inputs(
    *,
    inputs: dict[str, Any],
    mode: str,
    idempotency_key: str,
    approval_id: str,
    requires_compliance_gate: bool,
    requires_originality_check: bool,
    operator_confirmed: bool,
) -> SocialPublishRequest:
    metadata = {
        key: inputs.get(key)
        for key in (
            "policy_id",
            "source_policy_id",
            "pack_id",
            "channel_id",
            "metric_source_id",
        )
        if inputs.get(key)
    }
    raw_metadata = inputs.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    platform = str(
        inputs.get("platform") or inputs.get("channel_platform") or inputs.get("channel_id") or ""
    ).strip()
    return SocialPublishRequest(
        provider=str(
            inputs.get("provider")
            or getattr(settings, "SOCIAL_CONNECTOR_PROVIDER", "fake")
            or "fake"
        ),
        platform=platform,
        mode=mode,
        account_id=_optional_str(inputs.get("account_id")) or "",
        page_id=_optional_str(inputs.get("page_id")) or "",
        profile_id=_optional_str(inputs.get("profile_id")) or "",
        asset_ids=_social_asset_ids(inputs),
        publication_draft_id=_optional_str(inputs.get("publication_draft_id")),
        caption=str(inputs.get("caption") or inputs.get("text") or inputs.get("body") or ""),
        link_url=str(inputs.get("link_url") or ""),
        media_url=str(inputs.get("media_url") or ""),
        external_post_url=str(inputs.get("external_post_url") or ""),
        external_post_id=str(inputs.get("external_post_id") or ""),
        scheduled_at=_optional_str(inputs.get("scheduled_at")),
        metadata=metadata,
        idempotency_key=(idempotency_key or "")[:128],
        approval_id=approval_id or _optional_str(inputs.get("approval_id")),
        whiteboard_id=_optional_str(inputs.get("whiteboard_id")),
        deployment_channel_id=_optional_str(
            inputs.get("deployment_channel_id") or inputs.get("channel_id")
        ),
        asset_approved=bool(inputs.get("asset_approved") or inputs.get("content_approved")),
        caption_approved=bool(inputs.get("caption_approved") or inputs.get("content_approved")),
        compliance_gate_passed=bool(inputs.get("compliance_gate_passed")),
        originality_check_passed=bool(inputs.get("originality_check_passed")),
        requires_compliance_gate=bool(
            requires_compliance_gate or inputs.get("requires_compliance_gate")
        ),
        requires_originality_check=bool(
            requires_originality_check or inputs.get("requires_originality_check")
        ),
        operator_confirmed=bool(
            operator_confirmed
            or inputs.get("operator_confirmed")
            or inputs.get("operator_confirmation")
            or inputs.get("manual_operator_confirmed")
        ),
    )


def _policy_evaluation_approved(evaluation: PolicyEvaluation | None) -> bool:
    if evaluation is None:
        return False
    approval = evaluation.approval_task
    if approval is not None and approval.status == "approved":
        return True
    decision = evaluation.decision_record
    return bool(decision is not None and decision.status == "approved")


def _is_email_tool(tool_id: str) -> bool:
    return str(tool_id or "").strip() in EMAIL_EXECUTION_TOOL_IDS


def _is_whatsapp_tool(tool_id: str) -> bool:
    return str(tool_id or "").strip() in WHATSAPP_EXECUTION_TOOL_IDS


def _is_social_tool(tool_id: str) -> bool:
    return str(tool_id or "").strip() in SOCIAL_EXECUTION_TOOL_IDS


def _is_managed_connector_tool(tool_id: str) -> bool:
    return str(tool_id or "").strip() in CONNECTOR_EXECUTION_TOOL_IDS


def _is_email_tool_alias(tool_id: str) -> bool:
    return str(tool_id or "").strip() in EMAIL_CONNECTOR_COMPAT_TOOL_IDS


def _is_whatsapp_tool_alias(tool_id: str) -> bool:
    return str(tool_id or "").strip() in WHATSAPP_CONNECTOR_COMPAT_TOOL_IDS


def _is_social_tool_alias(tool_id: str) -> bool:
    return str(tool_id or "").strip() in SOCIAL_CONNECTOR_COMPAT_TOOL_IDS


def _whatsapp_mode_for_tool(*, tool_id: str, dry_run: bool) -> str:
    if str(tool_id or "").strip() == WHATSAPP_SEND_MANUAL_TOOL_ID:
        return WHATSAPP_MODE_MANUAL_OPS
    if dry_run:
        return WHATSAPP_MODE_DRY_RUN
    return WHATSAPP_MODE_REAL_SEND


def _social_mode_for_tool(*, tool_id: str, dry_run: bool) -> str:
    normalized = str(tool_id or "").strip()
    if normalized == SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID:
        return SOCIAL_MODE_MANUAL_PUBLISH_RECORD
    if normalized == SOCIAL_PROVIDER_PUBLISH_TOOL_ID or _social_alias_is_provider_publish(
        normalized
    ):
        return SOCIAL_MODE_DRY_RUN if dry_run else SOCIAL_MODE_PROVIDER_PUBLISH
    return SOCIAL_MODE_DRY_RUN if dry_run else SOCIAL_MODE_PROVIDER_PUBLISH


def _social_alias_is_provider_publish(tool_id: str) -> bool:
    return str(tool_id or "").strip() in {
        "social.instagram_publish",
        "social.facebook_publish",
        "social.instagram_provider_publish",
        "social.facebook_provider_publish",
    }


def _clean_subject(value: Any) -> str:
    subject = str(value or "Untitled sandbox email").strip()
    return subject[:200]


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


def _whatsapp_recipient_values(inputs: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("recipients", "to", "recipient_phones", "phone_numbers", "audience_phones"):
        raw = inputs.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            values.extend(part.strip() for part in raw.replace(";", ",").split(","))
            continue
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    values.append(
                        str(
                            item.get("phone")
                            or item.get("number")
                            or item.get("address")
                            or item.get("recipient")
                            or ""
                        )
                    )
                else:
                    values.append(str(item))
    return values


def _social_asset_ids(inputs: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw = inputs.get("asset_ids")
    if isinstance(raw, str):
        values.extend(part.strip() for part in raw.replace(";", ",").split(","))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                values.append(str(item.get("id") or item.get("asset_id") or ""))
            else:
                values.append(str(item))
    for key in ("asset_id", "media_asset_id"):
        if inputs.get(key):
            values.append(str(inputs.get(key)))
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        result.append(clean[:128])
        seen.add(clean)
    return result


def _social_target_account(inputs: dict[str, Any]) -> str:
    return str(
        inputs.get("account_id") or inputs.get("page_id") or inputs.get("profile_id") or ""
    ).strip()


def _address_values(inputs: dict[str, Any], key: str) -> list[str]:
    raw = inputs.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                values.append(str(item.get("email") or item.get("address") or ""))
            else:
                values.append(str(item))
        return values
    return []


def _email_from_friendly_address(value: str) -> str:
    if "<" not in value or ">" not in value:
        return value.strip()
    return value.rsplit("<", 1)[1].split(">", 1)[0].strip()


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _hash_social_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"sha256:{hashlib.sha256(text.lower().encode('utf-8')).hexdigest()}"


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


def _email_attempt_id(*, idempotency_key: str, tool_id: str, inputs: dict[str, Any]) -> str:
    return _connector_attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=inputs)


def _connector_attempt_id(*, idempotency_key: str, tool_id: str, inputs: dict[str, Any]) -> str:
    clean_key = str(idempotency_key or "").strip()
    if clean_key:
        payload = {"idempotency_key": clean_key, "tool_id": tool_id}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()[:32]
    return _attempt_id(idempotency_key=idempotency_key, tool_id=tool_id, inputs=inputs)
