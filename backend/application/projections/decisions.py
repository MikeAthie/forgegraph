from __future__ import annotations

from application.services.os_projections import _policy_decision_type
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    AuditLog,
    DecisionRecord,
    DomainEvent,
    Run,
    TaskRecord,
)


def apply(event: DomainEvent) -> None:
    approval_id = str(event.payload.get("approval_task_id") or "").strip()
    run_id = str(event.payload.get("run_id") or "").strip()
    audit_log_id = str(event.payload.get("audit_log_id") or "").strip()

    if approval_id:
        approval = (
            ApprovalTask.objects.select_related("run__graph_version__graph", "task_lifecycle")
            .filter(id=approval_id)
            .first()
        )
        if approval is not None:
            _project_approval(approval)

    if run_id:
        run = (
            Run.objects.select_related("organization", "owner__default_organization")
            .filter(id=run_id)
            .first()
        )
        if run is not None:
            _project_policy_run(run)

    if audit_log_id:
        audit_log = AuditLog.objects.filter(id=audit_log_id).first()
        if audit_log is not None:
            _project_audit_review(audit_log)


def _project_approval(approval: ApprovalTask) -> DecisionRecord | None:
    run = approval.run
    organization = (
        run.organization or run.graph_version.graph.organization or run.owner.default_organization
    )
    if organization is None:
        return None
    task = TaskRecord.objects.filter(
        organization=organization,
        execution=run,
        source_node_id=approval.node_id,
    ).first()
    agent = task.agent if task and task.agent_id else _agent_for(run=run, node_id=approval.node_id)
    decision, _ = DecisionRecord.objects.update_or_create(
        organization=organization,
        external_key=f"approval:{approval.id}",
        defaults={
            "execution": run,
            "task": task,
            "task_lifecycle": approval.task_lifecycle or (task.lifecycle_task if task else None),
            "agent": agent,
            "decision_type": "human_approval",
            "status": approval.status,
            "source_approval_task": approval,
            "context_json": approval.payload if isinstance(approval.payload, dict) else {},
            "resolution_json": approval.result if isinstance(approval.result, dict) else {},
            "requested_at": approval.created_at,
            "resolved_at": approval.resolved_at,
        },
    )
    _sync_task_decision(decision)
    return decision


def _project_policy_run(run: Run) -> DecisionRecord | None:
    decision_type = _policy_decision_type(run)
    if not decision_type:
        return None
    organization = (
        run.organization or run.graph_version.graph.organization or run.owner.default_organization
    )
    if organization is None:
        return None
    decision, _ = DecisionRecord.objects.update_or_create(
        organization=organization,
        external_key=f"run-error:{run.id}",
        defaults={
            "execution": run,
            "task": None,
            "agent": None,
            "decision_type": decision_type,
            "status": "resolved" if run.status in {"failed", "canceled"} else "pending",
            "context_json": {"error_message": run.error_message, "status": run.status},
            "resolution_json": {},
            "requested_at": run.ended_at or run.started_at,
            "resolved_at": run.ended_at if run.status in {"failed", "canceled"} else None,
        },
    )
    return decision


def _project_audit_review(audit_log: AuditLog) -> DecisionRecord | None:
    organization_id = audit_log.tenant_id
    decision, _ = DecisionRecord.objects.update_or_create(
        organization_id=organization_id,
        external_key=f"audit-review:{audit_log.id}",
        defaults={
            "execution": None,
            "task": None,
            "agent": None,
            "decision_type": "marketplace_review",
            "status": "resolved",
            "context_json": {
                "action": audit_log.action,
                "resource_type": audit_log.resource_type,
                "resource_id": audit_log.resource_id,
                "metadata": audit_log.metadata,
            },
            "resolution_json": audit_log.metadata if isinstance(audit_log.metadata, dict) else {},
            "requested_at": audit_log.created_at,
            "resolved_at": audit_log.created_at,
        },
    )
    return decision


def _agent_for(*, run: Run, node_id: str) -> AgentRegistryEntry | None:
    organization = (
        run.organization or run.graph_version.graph.organization or run.owner.default_organization
    )
    if organization is None:
        return None
    return AgentRegistryEntry.objects.filter(
        organization=organization,
        source_workflow=run.graph_version.graph,
        source_node_id=node_id,
    ).first()


def _sync_task_decision(decision: DecisionRecord) -> None:
    if not decision.task_id:
        return
    if decision.status == "pending":
        TaskRecord.objects.filter(id=decision.task_id).update(current_decision=decision)
        return
    TaskRecord.objects.filter(id=decision.task_id, current_decision=decision).update(
        current_decision=None
    )
