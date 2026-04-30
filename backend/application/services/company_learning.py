"""Company learning services for HITL feedback, outcomes, and policies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q

from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    ContextPack,
    DecisionRecord,
    EscalationRule,
    Graph,
    NodeRun,
    OutcomeReview,
    PolicyRule,
    PreferenceEvent,
    Run,
    TaskRecord,
    User,
)


class PreferenceEventService:
    """Convert HITL actions into structured preference events."""

    def record_hitl_feedback(
        self,
        *,
        approval_task: ApprovalTask,
        actor: User | None,
        final_value: dict[str, Any] | None,
        context_pack: ContextPack | None = None,
    ) -> PreferenceEvent:
        existing = PreferenceEvent.objects.filter(approval_task=approval_task).first()
        if existing is not None:
            return existing

        run = approval_task.run
        company = run.graph_version.graph
        if company.organization_id is None:
            raise ValueError("Preference events require an organization-scoped company.")
        if context_pack is not None and context_pack.company_id != company.id:
            raise ValueError("Context pack does not belong to company.")
        final = final_value or {}
        proposed = approval_task.payload if isinstance(approval_task.payload, dict) else {}
        task = _task_for_run_node(run=run, node_id=approval_task.node_id)
        node_run = _node_run_for_run_node(run=run, node_id=approval_task.node_id)
        decision = (
            DecisionRecord.objects.filter(source_approval_task=approval_task)
            .order_by("-created_at")
            .first()
        )
        context_pack = context_pack or _latest_context_pack(run)
        diff = _dict_diff(proposed, final)
        event_type = _feedback_event_type(
            final=final, approval_status=approval_task.status, diff=diff
        )

        defaults = {
            "organization": company.organization,
            "company": company,
            "operation": run,
            "task": task,
            "node_run": node_run,
            "decision": decision,
            "context_pack": context_pack,
            "actor_id": getattr(actor, "id", None),
            "actor_type": _actor_type(actor),
            "event_type": event_type,
            "proposed_value_json": proposed,
            "final_value_json": final,
            "diff_json": diff,
            "rationale": _rationale(final),
            "risk_level": _optional_float(final.get("risk_level")),
            "metadata_json": {
                "node_id": approval_task.node_id,
                "run_id": str(run.id),
                "approval_status": approval_task.status,
            },
        }
        try:
            event, _ = PreferenceEvent.objects.get_or_create(
                approval_task=approval_task,
                defaults=defaults,
            )
            return event
        except IntegrityError:
            existing = PreferenceEvent.objects.filter(approval_task=approval_task).first()
            if existing is not None:
                return existing
            raise

    def record_approval_event(
        self,
        *,
        approval_task: ApprovalTask,
        actor: User | None,
    ) -> PreferenceEvent:
        return self.record_hitl_feedback(
            approval_task=approval_task,
            actor=actor,
            final_value=approval_task.result if isinstance(approval_task.result, dict) else {},
        )

    def record_edit_event(
        self,
        *,
        approval_task: ApprovalTask,
        actor: User | None,
        final_value: dict[str, Any],
    ) -> PreferenceEvent:
        final = dict(final_value)
        final.setdefault("edited", True)
        return self.record_hitl_feedback(
            approval_task=approval_task,
            actor=actor,
            final_value=final,
        )

    def record_override_event(
        self,
        *,
        approval_task: ApprovalTask,
        actor: User | None,
        final_value: dict[str, Any],
    ) -> PreferenceEvent:
        final = dict(final_value)
        final.setdefault("override", True)
        return self.record_hitl_feedback(
            approval_task=approval_task,
            actor=actor,
            final_value=final,
        )


class OutcomeReviewService:
    """Create and attach outcome reviews to company work."""

    def create_outcome_review(
        self,
        *,
        company: Graph,
        operation: Run | None = None,
        task: TaskRecord | None = None,
        node_run: NodeRun | None = None,
        decision: DecisionRecord | None = None,
        deliverable_id: UUID | None = None,
        asset: Asset | None = None,
        success_score: float | None = None,
        success_metrics: dict[str, Any] | None = None,
        human_feedback: str | None = None,
        issues: list[dict[str, Any]] | None = None,
        root_cause: str | None = None,
        created_by_type: str = "user",
        created_by_id: UUID | None = None,
    ) -> OutcomeReview:
        _assert_company_scope(
            company=company,
            operation=operation,
            task=task,
            node_run=node_run,
            decision=decision,
            asset=asset,
        )
        organization = company.organization
        if organization is None:
            raise ValueError("Outcome reviews require an organization-scoped company.")
        return OutcomeReview.objects.create(
            organization=organization,
            company=company,
            operation=operation,
            task=task,
            node_run=node_run,
            decision=decision,
            deliverable_id=deliverable_id,
            asset=asset,
            success_score=success_score,
            success_metrics_json=success_metrics or {},
            human_feedback=human_feedback,
            issues_json=issues or [],
            root_cause=root_cause,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
        )

    def attach_outcome_to_deliverable(
        self,
        *,
        company: Graph,
        deliverable_id: UUID,
        **kwargs: Any,
    ) -> OutcomeReview:
        return self.create_outcome_review(
            company=company,
            deliverable_id=deliverable_id,
            **kwargs,
        )

    def attach_outcome_to_decision(
        self,
        *,
        company: Graph,
        decision: DecisionRecord,
        **kwargs: Any,
    ) -> OutcomeReview:
        return self.create_outcome_review(
            company=company,
            decision=decision,
            **kwargs,
        )


class PolicyCandidateService:
    """Manage explicit policy candidates and active learned policies."""

    def find_repeated_preferences(
        self,
        *,
        company: Graph,
        min_count: int = 2,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[PreferenceEvent]] = {}
        for event in PreferenceEvent.objects.filter(company=company).order_by("-created_at")[:100]:
            key = _preference_group_key(event)
            grouped.setdefault(key, []).append(event)
        return [
            {
                "key": key,
                "count": len(events),
                "preference_event_ids": [str(event.id) for event in events],
            }
            for key, events in grouped.items()
            if key and len(events) >= min_count
        ]

    def create_policy_candidate(
        self,
        *,
        company: Graph,
        title: str,
        condition: dict[str, Any],
        recommendation: dict[str, Any],
        confidence: float = 0.5,
        scope_type: str = "company",
        scope_id: str = "",
        supporting_preference_event_ids: list[UUID] | None = None,
        supporting_outcome_review_ids: list[UUID] | None = None,
    ) -> PolicyRule:
        organization = company.organization
        if organization is None:
            raise ValueError("Policy rules require an organization-scoped company.")
        preference_ids = _validated_preference_ids(
            company=company,
            ids=supporting_preference_event_ids or [],
        )
        outcome_ids = _validated_outcome_ids(
            company=company,
            ids=supporting_outcome_review_ids or [],
        )
        return PolicyRule.objects.create(
            organization=organization,
            company=company,
            scope_type=scope_type,
            scope_id=scope_id,
            title=title.strip(),
            condition_json=condition,
            recommendation_json=recommendation,
            confidence=_clamp(confidence),
            status="candidate",
            supporting_preference_event_ids_json=[str(item) for item in preference_ids],
            supporting_outcome_review_ids_json=[str(item) for item in outcome_ids],
        )

    def promote_policy_rule(self, *, policy_rule: PolicyRule) -> PolicyRule:
        if policy_rule.status == "rejected":
            raise ValueError("Rejected policy candidates cannot be promoted.")
        policy_rule.status = "active"
        policy_rule.save(update_fields=["status", "updated_at"])
        return policy_rule

    def reject_policy_candidate(self, *, policy_rule: PolicyRule) -> PolicyRule:
        policy_rule.status = "rejected"
        policy_rule.save(update_fields=["status", "updated_at"])
        return policy_rule


class EscalationRuleService:
    """Basic query service for active escalation rules."""

    def active_rules(
        self,
        *,
        company: Graph,
        scope_type: str | None = None,
        scope_id: str | None = None,
        trigger_type: str | None = None,
    ) -> list[EscalationRule]:
        queryset = EscalationRule.objects.filter(company=company, status="active")
        if scope_type:
            queryset = queryset.filter(scope_type=scope_type)
        if scope_id:
            queryset = queryset.filter(Q(scope_id="") | Q(scope_id=scope_id))
        if trigger_type:
            queryset = queryset.filter(trigger_type=trigger_type)
        return list(queryset.order_by("-updated_at")[:50])


def preference_event_payload(event: PreferenceEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "company_id": str(event.company_id),
        "operation_id": str(event.operation_id) if event.operation_id else None,
        "task_id": str(event.task_id) if event.task_id else None,
        "node_run_id": str(event.node_run_id) if event.node_run_id else None,
        "decision_id": str(event.decision_id) if event.decision_id else None,
        "approval_task_id": str(event.approval_task_id) if event.approval_task_id else None,
        "context_pack_id": str(event.context_pack_id) if event.context_pack_id else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "actor_type": event.actor_type,
        "event_type": event.event_type,
        "proposed_value": event.proposed_value_json,
        "final_value": event.final_value_json,
        "diff": event.diff_json,
        "rationale": event.rationale,
        "risk_level": event.risk_level,
        "metadata": event.metadata_json,
        "created_at": event.created_at.isoformat(),
    }


def outcome_review_payload(review: OutcomeReview) -> dict[str, Any]:
    return {
        "id": str(review.id),
        "company_id": str(review.company_id),
        "operation_id": str(review.operation_id) if review.operation_id else None,
        "task_id": str(review.task_id) if review.task_id else None,
        "node_run_id": str(review.node_run_id) if review.node_run_id else None,
        "decision_id": str(review.decision_id) if review.decision_id else None,
        "deliverable_id": str(review.deliverable_id) if review.deliverable_id else None,
        "asset_id": str(review.asset_id) if review.asset_id else None,
        "success_score": review.success_score,
        "success_metrics": review.success_metrics_json,
        "human_feedback": review.human_feedback,
        "issues": review.issues_json,
        "root_cause": review.root_cause,
        "created_by_type": review.created_by_type,
        "created_by_id": str(review.created_by_id) if review.created_by_id else None,
        "created_at": review.created_at.isoformat(),
    }


def policy_rule_payload(rule: PolicyRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "company_id": str(rule.company_id),
        "scope_type": rule.scope_type,
        "scope_id": rule.scope_id or None,
        "title": rule.title,
        "condition": rule.condition_json,
        "recommendation": rule.recommendation_json,
        "confidence": rule.confidence,
        "status": rule.status,
        "supporting_preference_event_ids": rule.supporting_preference_event_ids_json,
        "supporting_outcome_review_ids": rule.supporting_outcome_review_ids_json,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def _task_for_run_node(*, run: Run, node_id: str) -> TaskRecord | None:
    return (
        TaskRecord.objects.filter(execution=run)
        .filter(Q(source_node_id=node_id) | Q(current_step__node_id=node_id))
        .order_by("-updated_at")
        .first()
    )


def _node_run_for_run_node(*, run: Run, node_id: str) -> NodeRun | None:
    return NodeRun.objects.filter(run=run, node_id=node_id).order_by("-attempt").first()


def _latest_context_pack(run: Run) -> ContextPack | None:
    return ContextPack.objects.filter(operation=run).order_by("-created_at").first()


def _dict_diff(proposed: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    added: dict[str, Any] = {}
    removed: dict[str, Any] = {}
    changed: dict[str, dict[str, Any]] = {}
    for key, value in final.items():
        if key not in proposed:
            added[key] = value
        elif proposed[key] != value:
            changed[key] = {"from": proposed[key], "to": value}
    for key, value in proposed.items():
        if key not in final:
            removed[key] = value
    return {"added": added, "removed": removed, "changed": changed}


def _feedback_event_type(
    *,
    final: dict[str, Any],
    approval_status: str,
    diff: dict[str, Any],
) -> str:
    if approval_status == "rejected" or final.get("approved") is False:
        return "rejected"
    if final.get("override") or final.get("overridden"):
        return "overridden"
    if final.get("clarified") or final.get("clarification"):
        return "clarified"
    if final.get("edited") or any(diff.get(key) for key in ("added", "removed", "changed")):
        return "edited"
    return "approved"


def _actor_type(actor: User | None) -> str:
    if actor is None:
        return "system"
    return "user"


def _rationale(final: dict[str, Any]) -> str | None:
    for key in ("rationale", "feedback", "reason", "comment"):
        value = final.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _assert_company_scope(
    *,
    company: Graph,
    operation: Run | None = None,
    task: TaskRecord | None = None,
    node_run: NodeRun | None = None,
    decision: DecisionRecord | None = None,
    asset: Asset | None = None,
) -> None:
    if operation is not None and operation.graph_version.graph_id != company.id:
        raise ValueError("Operation does not belong to company.")
    if task is not None and task.execution.graph_version.graph_id != company.id:
        raise ValueError("Task does not belong to company.")
    if node_run is not None and node_run.run.graph_version.graph_id != company.id:
        raise ValueError("Node run does not belong to company.")
    if decision is not None and not _decision_belongs_to_company(
        decision=decision, company=company
    ):
        raise ValueError("Decision does not belong to company organization.")
    if asset is not None and asset.company_id != company.id:
        raise ValueError("Asset does not belong to company.")


def _validated_preference_ids(*, company: Graph, ids: list[UUID]) -> list[UUID]:
    if not ids:
        return []
    found = set(
        PreferenceEvent.objects.filter(company=company, id__in=ids).values_list("id", flat=True)
    )
    missing = [item for item in ids if item not in found]
    if missing:
        raise ValueError("Some preference events do not belong to company.")
    return ids


def _validated_outcome_ids(*, company: Graph, ids: list[UUID]) -> list[UUID]:
    if not ids:
        return []
    found = set(
        OutcomeReview.objects.filter(company=company, id__in=ids).values_list("id", flat=True)
    )
    missing = [item for item in ids if item not in found]
    if missing:
        raise ValueError("Some outcome reviews do not belong to company.")
    return ids


def _decision_belongs_to_company(*, decision: DecisionRecord, company: Graph) -> bool:
    execution = decision.execution
    if execution is not None and execution.graph_version.graph_id == company.id:
        return True
    task = decision.task
    if task is not None and task.execution.graph_version.graph_id == company.id:
        return True
    approval = decision.source_approval_task
    if approval is not None and approval.run.graph_version.graph_id == company.id:
        return True
    return False


def _preference_group_key(event: PreferenceEvent) -> str:
    diff = event.diff_json or {}
    changed = diff.get("changed") if isinstance(diff, dict) else None
    if isinstance(changed, dict) and changed:
        return ",".join(sorted(changed.keys()))
    rationale = (event.rationale or "").strip().lower()
    return rationale[:80]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
