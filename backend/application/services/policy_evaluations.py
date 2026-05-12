"""Generic policy evaluation services."""

from __future__ import annotations

from typing import Any, cast

from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.task_lifecycle import create_backend_approval_task
from infrastructure.orm.models import (
    DecisionRecord,
    EvaluationRun,
    Graph,
    PolicyEvaluation,
    PolicyPack,
    Run,
    User,
)

RISK_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SIDE_EFFECT_ACTIONS = {
    "publish",
    "send_email",
    "launch_ads",
    "sync_crm",
    "export_report",
    "schedule",
}


def evaluate_policy(
    *,
    company: Graph,
    user: User,
    action_type: str,
    inputs: dict[str, Any] | None = None,
    policy_pack_id: str = "",
    operation: Run | None = None,
) -> PolicyEvaluation:
    clean_action = str(action_type or "").strip()
    payload = inputs or {}
    policy_pack = _policy_pack(company=company, policy_pack_id=policy_pack_id)
    risk_level, trace = _risk_for_action(
        action_type=clean_action,
        inputs=payload,
        policy_pack=policy_pack,
    )
    blocker_trace = _blocking_evaluation_trace(company=company, inputs=payload)
    if blocker_trace:
        risk_level = _max_risk(risk_level, "CRITICAL")
        trace["evaluation_blockers"] = blocker_trace
    status = "approval_required" if risk_level in {"HIGH", "CRITICAL"} else "allowed"
    if risk_level == "CRITICAL" and (bool(payload.get("blocked_by_policy")) or blocker_trace):
        status = "blocked"
    evaluation = PolicyEvaluation.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        policy_pack=policy_pack,
        action_type=clean_action,
        risk_level=risk_level,
        status=status,
        input_json=payload,
        trace_json=trace,
        created_by=user,
    )
    approval_task = None
    if status == "approval_required" and operation is not None:
        approval_task = create_backend_approval_task(
            run=operation,
            node_id="policy_evaluation",
            assignee=user,
            payload={
                "prompt_message": f"Approve {clean_action} policy evaluation.",
                "required_fields": ["approved", "notes"],
                "policy_evaluation_id": str(evaluation.id),
                "risk_level": risk_level,
            },
        )
    decision = None
    if status in {"approval_required", "blocked"}:
        decision = DecisionRecord.objects.create(
            organization=cast(Any, company.organization),
            execution=operation,
            decision_type="policy_guardrail",
            status="pending" if status == "approval_required" else "rejected",
            source_approval_task=approval_task,
            external_key=f"policy_evaluation:{evaluation.id}",
            context_json={
                "policy_evaluation_id": str(evaluation.id),
                "action_type": clean_action,
                "risk_level": risk_level,
                "status": status,
            },
            requested_at=timezone.now(),
            resolved_at=timezone.now() if status == "blocked" else None,
        )
    if decision or approval_task:
        evaluation.decision_record = decision
        evaluation.approval_task = approval_task
        evaluation.save(update_fields=["decision_record", "approval_task"])
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="policy_evaluation.created",
        resource_type="policy_evaluation",
        resource_id=str(evaluation.id),
        metadata={
            "company_id": str(company.id),
            "action_type": clean_action,
            "risk_level": risk_level,
        },
    )
    return evaluation


def policy_evaluation_payload(evaluation: PolicyEvaluation) -> dict[str, Any]:
    return {
        "id": str(evaluation.id),
        "company_id": str(evaluation.company_id),
        "policy_pack_id": str(evaluation.policy_pack_id) if evaluation.policy_pack_id else None,
        "action_type": evaluation.action_type,
        "risk_level": evaluation.risk_level,
        "status": evaluation.status,
        "input": evaluation.input_json,
        "trace": evaluation.trace_json,
        "decision_record_id": str(evaluation.decision_record_id)
        if evaluation.decision_record_id
        else None,
        "approval_task_id": str(evaluation.approval_task_id)
        if evaluation.approval_task_id
        else None,
        "created_at": evaluation.created_at.isoformat(),
    }


def _policy_pack(company: Graph, policy_pack_id: str) -> PolicyPack | None:
    queryset = PolicyPack.objects.filter(company=company, status="active")
    if policy_pack_id:
        return queryset.filter(policy_pack_id=policy_pack_id).first()
    return queryset.first()


def _risk_for_action(
    *,
    action_type: str,
    inputs: dict[str, Any],
    policy_pack: PolicyPack | None,
) -> tuple[str, dict[str, Any]]:
    risk = "LOW"
    trace: list[dict[str, Any]] = []
    rules = (
        policy_pack.rules_json if policy_pack and isinstance(policy_pack.rules_json, list) else []
    )
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("action_type") != action_type:
            continue
        risk = _max_risk(risk, str(rule.get("risk_floor") or "LOW"))
        trace.append({"rule_id": rule.get("id"), "risk_floor": rule.get("risk_floor")})
    if action_type in SIDE_EFFECT_ACTIONS or bool(inputs.get("external_write_side_effect")):
        risk = _max_risk(risk, "MEDIUM")
        trace.append({"reason": "side_effecting_action", "risk": "MEDIUM"})
    if bool(inputs.get("personal_data_exposure")) or bool(inputs.get("regulated_claims")):
        risk = _max_risk(risk, "HIGH")
        trace.append({"reason": "sensitive_data_or_claims", "risk": "HIGH"})
    budget = float(inputs.get("budget") or 0)
    if budget >= 50000:
        risk = _max_risk(risk, "CRITICAL")
        trace.append({"reason": "budget_threshold_critical", "risk": "CRITICAL"})
    elif budget >= 5000:
        risk = _max_risk(risk, "HIGH")
        trace.append({"reason": "budget_threshold_high", "risk": "HIGH"})
    return risk, {"rules": trace}


def _max_risk(current: str, candidate: str) -> str:
    current = current if current in RISK_ORDER else "LOW"
    candidate = candidate if candidate in RISK_ORDER else "LOW"
    return candidate if RISK_ORDER.index(candidate) > RISK_ORDER.index(current) else current


def _blocking_evaluation_trace(*, company: Graph, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    if bool(inputs.get("allow_blocking_evaluation_override")):
        return []
    queryset = EvaluationRun.objects.filter(company=company, status="BLOCK")
    asset_id = str(inputs.get("asset_id") or "")
    program_id = str(inputs.get("program_id") or "")
    if asset_id:
        queryset = queryset.filter(asset_id=cast(Any, asset_id))
    elif program_id:
        queryset = queryset.filter(program_id=cast(Any, program_id))
    else:
        return []
    return [
        {
            "evaluation_id": str(item.id),
            "profile_id": item.profile_key,
            "asset_id": str(item.asset_id) if item.asset_id else None,
            "program_id": str(item.program_id) if item.program_id else None,
        }
        for item in queryset.order_by("-created_at")[:5]
    ]
