"""Generic validation-driven rework plan services."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.state_projections import materialize_current_truth_projection
from application.services.work_artifacts import (
    canonical_version,
    create_artifact_revision,
    set_canonical_revision,
)
from infrastructure.orm.models import (
    AssetVersion,
    CompanyProgram,
    Graph,
    ProgramStageState,
    ReworkPlan,
    ReworkPlanItem,
    User,
    ValidationDecision,
)


def create_rework_plan(
    *,
    company: Graph,
    user: User,
    program: CompanyProgram | None = None,
    validation_decision_ids: list[UUID] | None = None,
    notes: str = "",
) -> ReworkPlan:
    decisions = _decisions(company=company, program=program, ids=validation_decision_ids)
    required_approval = any(decision.decision in {"REJECT", "EDIT"} for decision in decisions)
    impact = _impact(decisions)
    with transaction.atomic():
        plan = ReworkPlan.objects.create(
            organization=cast(Any, company.organization),
            company=company,
            program=program,
            status="approval_required" if required_approval else "draft",
            trigger_summary=notes or _trigger_summary(decisions),
            impact_json=impact,
            required_approvals_json=[{"type": "rework", "reason": "Validation changed source work"}]
            if required_approval
            else [],
            estimated_effort_json={
                "items": len(decisions),
                "relative_cost": sum(_effort_for_decision(decision) for decision in decisions),
                "scope": _scope_for_effort(
                    sum(_effort_for_decision(decision) for decision in decisions)
                ),
            },
            created_by=user,
        )
        for index, decision in enumerate(decisions, start=1):
            ReworkPlanItem.objects.create(
                plan=plan,
                organization=cast(Any, company.organization),
                company=company,
                item_type=_item_type(decision),
                target_id=_target_id(decision),
                action=_action_for_decision(decision),
                reason=decision.rationale,
                recommended_order=index,
                metadata_json={
                    "validation_decision_id": str(decision.id),
                    "category": decision.category,
                    "stage_id": _stage_id_for_decision(decision),
                    "proposed_change": decision.proposed_change_json,
                },
            )
        if program is not None:
            _mark_stage_rework_required(program=program, stage_ids=impact["impacted_stages"])
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="rework_plan.created",
        resource_type="rework_plan",
        resource_id=str(plan.id),
        metadata={"company_id": str(company.id), "item_count": len(decisions)},
    )
    return plan


def execute_rework_plan(*, plan: ReworkPlan, user: User) -> ReworkPlan:
    with transaction.atomic():
        for item in ReworkPlanItem.objects.filter(plan=plan, status="pending"):
            _execute_plan_item(item=item, user=user)
            item.status = "executed"
            item.executed_at = timezone.now()
            item.save(update_fields=["status", "executed_at"])
        plan.status = "executed"
        plan.executed_by = user
        plan.executed_at = timezone.now()
        plan.save(update_fields=["status", "executed_by", "executed_at", "updated_at"])
        program = plan.program if plan.program_id else None
        if program is not None:
            _activate_earliest_impacted_stage(program, plan.impact_json)
    program = plan.program if plan.program_id else None
    if program is not None:
        materialize_current_truth_projection(company=plan.company, program=program)
    record_audit_log(
        actor=user,
        tenant_id=str(plan.organization_id),
        action="rework_plan.executed",
        resource_type="rework_plan",
        resource_id=str(plan.id),
        metadata={"company_id": str(plan.company_id)},
    )
    return plan


def rework_plan_payload(plan: ReworkPlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "company_id": str(plan.company_id),
        "program_id": str(plan.program_id) if plan.program_id else None,
        "status": plan.status,
        "trigger_summary": plan.trigger_summary,
        "impact": plan.impact_json,
        "required_approvals": plan.required_approvals_json,
        "estimated_effort": plan.estimated_effort_json,
        "items": [
            {
                "id": str(item.id),
                "item_type": item.item_type,
                "target_id": item.target_id,
                "action": item.action,
                "reason": item.reason,
                "recommended_order": item.recommended_order,
                "status": item.status,
                "metadata": item.metadata_json,
            }
            for item in ReworkPlanItem.objects.filter(plan=plan).order_by("recommended_order")
        ],
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
        "executed_at": plan.executed_at.isoformat() if plan.executed_at else None,
    }


def _decisions(
    *,
    company: Graph,
    program: CompanyProgram | None,
    ids: list[UUID] | None,
) -> list[ValidationDecision]:
    queryset = ValidationDecision.objects.filter(company=company)
    if program is not None:
        queryset = queryset.filter(program=program)
    if ids:
        queryset = queryset.filter(id__in=ids)
    return list(queryset.exclude(decision="ACCEPT").order_by("created_at"))


def _trigger_summary(decisions: list[ValidationDecision]) -> str:
    if not decisions:
        return "No validation changes require rework."
    categories = sorted({decision.category or "uncategorized" for decision in decisions})
    return f"Validation changes require rework for: {', '.join(categories)}."


def _impact(decisions: list[ValidationDecision]) -> dict[str, Any]:
    impacted_stages = sorted(
        {stage_id for decision in decisions if (stage_id := _stage_id_for_decision(decision))}
    )
    return {
        "decision_count": len(decisions),
        "impacted_artifacts": [
            str(decision.asset_id) for decision in decisions if decision.asset_id
        ],
        "impacted_assertions": [
            str(decision.assertion_id) for decision in decisions if decision.assertion_id
        ],
        "impacted_stages": impacted_stages,
        "categories": sorted({decision.category for decision in decisions if decision.category}),
    }


def _item_type(decision: ValidationDecision) -> str:
    if decision.asset_id:
        return "artifact"
    if decision.assertion_id:
        return "assertion"
    return "program"


def _target_id(decision: ValidationDecision) -> str:
    if decision.asset_id:
        return str(decision.asset_id)
    if decision.assertion_id:
        return str(decision.assertion_id)
    if decision.program_id:
        return str(decision.program_id)
    return ""


def _action_for_decision(decision: ValidationDecision) -> str:
    if decision.decision == "NEEDS_RESEARCH":
        return "research"
    if decision.decision == "EDIT":
        return "revise"
    if decision.decision == "REJECT":
        return "replace"
    if decision.decision == "DEFER":
        return "defer"
    return "review"


def _stage_id_for_decision(decision: ValidationDecision) -> str:
    change = (
        decision.proposed_change_json if isinstance(decision.proposed_change_json, dict) else {}
    )
    if change.get("stage_id"):
        return str(change["stage_id"])
    asset = decision.asset if decision.asset_id else None
    if asset is not None:
        metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
        if metadata.get("stage_id"):
            return str(metadata["stage_id"])
    assertion = decision.assertion if decision.assertion_id else None
    if assertion is not None:
        metadata = assertion.metadata_json if isinstance(assertion.metadata_json, dict) else {}
        if metadata.get("stage_id"):
            return str(metadata["stage_id"])
    program = decision.program if decision.program_id else None
    if program is not None:
        return program.current_stage_id
    return ""


def _effort_for_decision(decision: ValidationDecision) -> int:
    if decision.decision == "REJECT":
        return 5
    if decision.decision == "NEEDS_RESEARCH":
        return 4
    if decision.decision == "EDIT":
        return 3
    if decision.decision == "DEFER":
        return 1
    return 0


def _scope_for_effort(effort: int) -> str:
    if effort >= 12:
        return "large"
    if effort >= 6:
        return "medium"
    if effort > 0:
        return "small"
    return "none"


def _mark_stage_rework_required(*, program: CompanyProgram, stage_ids: list[str]) -> None:
    if not stage_ids:
        return
    ProgramStageState.objects.filter(program=program, stage_id__in=stage_ids).exclude(
        status="completed"
    ).update(status="rerun_required")
    ProgramStageState.objects.filter(
        program=program, stage_id__in=stage_ids, status="completed"
    ).update(status="rerun_required", completed_at=None)
    first = (
        ProgramStageState.objects.filter(program=program, stage_id__in=stage_ids)
        .order_by("sequence")
        .first()
    )
    if first is not None:
        program.current_stage_id = first.stage_id
        program.status = "active"
        program.save(update_fields=["current_stage_id", "status", "updated_at"])


def _activate_earliest_impacted_stage(program: CompanyProgram, impact: dict[str, Any]) -> None:
    stage_ids = impact.get("impacted_stages") if isinstance(impact, dict) else []
    if not isinstance(stage_ids, list) or not stage_ids:
        return
    first = (
        ProgramStageState.objects.filter(
            program=program, stage_id__in=[str(item) for item in stage_ids]
        )
        .order_by("sequence")
        .first()
    )
    if first is None:
        return
    first.status = "in_progress"
    first.started_at = first.started_at or timezone.now()
    first.completed_at = None
    first.save(update_fields=["status", "started_at", "completed_at", "updated_at"])
    program.current_stage_id = first.stage_id
    program.status = "active"
    program.save(update_fields=["current_stage_id", "status", "updated_at"])


def _execute_plan_item(*, item: ReworkPlanItem, user: User) -> None:
    decision_id = item.metadata_json.get("validation_decision_id")
    decision = ValidationDecision.objects.filter(company=item.company, id=decision_id).first()
    if (
        decision is None
        or decision.asset is None
        or item.action not in {"revise", "replace", "research"}
    ):
        return
    asset = decision.asset
    change = (
        decision.proposed_change_json if isinstance(decision.proposed_change_json, dict) else {}
    )
    content = change.get("content")
    if content is None:
        content = _default_revision_content(decision)
    parent = decision.asset_version or canonical_version(asset)
    revision = create_artifact_revision(
        asset=asset,
        user=user,
        content=content,
        parent_version=parent,
        label=str(change.get("label") or _next_rework_label(parent)),
        metadata={
            "source": "rework_plan",
            "rework_plan_id": str(item.plan_id),
            "rework_plan_item_id": str(item.id),
            "validation_decision_id": str(decision.id),
        },
    )
    set_canonical_revision(asset=asset, version=revision, user=user)


def _default_revision_content(decision: ValidationDecision) -> dict[str, Any]:
    asset = decision.asset
    parent = decision.asset_version or (canonical_version(asset) if asset is not None else None)
    previous = _inline_content(parent)
    return {
        "rework_summary": decision.rationale or "Rework generated from validation decision.",
        "decision": decision.decision,
        "category": decision.category,
        "previous_content": previous,
    }


def _inline_content(version: AssetVersion | None) -> Any:
    if version is None:
        return None
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    return provenance.get("inline_content")


def _next_rework_label(parent: AssetVersion | None) -> str:
    if parent is None:
        return "v2"
    parent_label = ""
    provenance = parent.provenance_json if isinstance(parent.provenance_json, dict) else {}
    if provenance.get("label"):
        parent_label = str(provenance["label"])
    if parent_label and "." not in parent_label and parent_label.startswith("v"):
        try:
            return f"v{int(parent_label[1:]) + 1}"
        except ValueError:
            return "v2"
    return f"v{parent.version_number + 1}"
