"""Phase 1 OS read models and on-demand projection helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

from application.dto.accounting import AvailableAccountingMetric, NotInstrumentedAccountingMetric
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    AuditLog,
    CostAggregate,
    CostLedgerEntry,
    DecisionRecord,
    DomainEvent,
    EventDeadLetterRecord,
    Graph,
    GraphVersion,
    LLMUsage,
    MemoryObservation,
    MemoryUsage,
    NodeRun,
    Organization,
    OrganizationStateFeedEvent,
    ProjectionCursor,
    Run,
    RuntimeIntentOutcome,
    TaskDeadLetterRecord,
    TaskLifecycleRecord,
    TaskRecord,
    TenantPolicy,
    User,
)

ACTIVE_RUN_STATUSES = {"pending", "running", "paused"}
ATTENTION_RUN_STATUSES = {"failed"}
TASK_ACTIVE_STATUSES = {
    "created",
    "queued",
    "claimed",
    "running",
    "paused",
    "waiting",
    "waiting_for_decision",
    "retry_scheduled",
}
TASK_BLOCKED_STATUSES = {"paused", "waiting", "waiting_for_decision", "failed", "dead_lettered"}
DECIMAL_ZERO = Decimal("0")
LEGACY_SWEEP_DISABLED_MESSAGE = "Legacy OS projection sweep disabled"


@dataclass(slots=True)
class ProjectionBundle:
    organization: Organization
    agents: list[AgentRegistryEntry]
    tasks: list[TaskRecord]
    decisions: list[DecisionRecord]
    ledger: list[CostLedgerEntry]


def _organization_for_user(user: User) -> Organization:
    if not user.default_organization_id:
        raise ValueError("User does not have a default organization.")
    return user.default_organization  # type: ignore[return-value]


def projection_organization_for_user(user: User) -> Organization:
    """Return the organization whose materialized read models should be read.

    This performs no projection repair or synchronization. GET request paths use
    this helper to keep reads side-effect free.
    """

    return _organization_for_user(user)


def _ensure_legacy_sweep_enabled() -> None:
    if not bool(getattr(settings, "ENABLE_LEGACY_OS_PROJECTION_SWEEP", False)):
        raise RuntimeError(LEGACY_SWEEP_DISABLED_MESSAGE)


def _graph_scope_filter(organization: Organization) -> models.Q:
    return models.Q(organization_id=organization.id) | models.Q(
        organization__isnull=True,
        owner__default_organization_id=organization.id,
    )


def _run_scope_filter(organization: Organization, prefix: str = "") -> models.Q:
    return models.Q(**{f"{prefix}organization_id": organization.id}) | models.Q(
        **{
            f"{prefix}organization__isnull": True,
            f"{prefix}owner__default_organization_id": organization.id,
        }
    )


def _workflow_queryset(organization: Organization) -> models.QuerySet[Graph]:
    return cast(
        models.QuerySet[Graph],
        Graph.objects.filter(_graph_scope_filter(organization)),
    )


def _latest_version(graph: Graph) -> GraphVersion | None:
    return graph.versions.order_by("-version").first()


def _extract_nodes(graph_json: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph_json.get("nodes", [])
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    return []


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data", {})
    return data if isinstance(data, dict) else {}


def _node_type(node: dict[str, Any]) -> str:
    data = _node_data(node)
    return str(node.get("type") or data.get("type") or data.get("node_type") or "").strip().lower()


def _is_agent_node(node: dict[str, Any]) -> bool:
    node_type = _node_type(node)
    return (
        node_type == "agent" or str(_node_data(node).get("kind") or "").strip().lower() == "agent"
    )


def _node_name(node: dict[str, Any]) -> str:
    data = _node_data(node)
    return str(
        node.get("name") or data.get("label") or data.get("name") or node.get("id") or "Agent"
    ).strip()


def _find_latest_node_run(
    graph: Graph,
    node_id: str,
    organization: Organization,
) -> NodeRun | None:
    return (
        NodeRun.objects.filter(
            _run_scope_filter(organization, prefix="run__"),
            run__graph_version__graph=graph,
            node_id=node_id,
        )
        .select_related("run")
        .order_by("-started_at", "-id")
        .first()
    )


def _derive_agent_status(latest_run: NodeRun | None, has_pending_decision: bool) -> str:
    if has_pending_decision:
        return "attention"
    if latest_run and latest_run.run.status in ACTIVE_RUN_STATUSES:
        return "active"
    if latest_run and latest_run.run.status in ATTENTION_RUN_STATUSES:
        return "attention"
    if latest_run:
        return "idle"
    return "offline"


def _agent_defaults(node: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    data = _node_data(node)
    config = data.get("config", {})
    config = config if isinstance(config, dict) else {}
    default_model = str(
        data.get("model") or config.get("model") or config.get("default_model") or ""
    ).strip()
    capabilities = {
        "tools": data.get("tools") or config.get("tools") or [],
        "memory": data.get("memory") or config.get("memory") or {},
        "inputs": data.get("inputs") or [],
        "outputs": data.get("outputs") or [],
    }
    policy_snapshot = data.get("policy") or config.get("policy") or {}
    return policy_snapshot, capabilities, default_model


def sync_agent_registry_for_organization(organization: Organization) -> list[AgentRegistryEntry]:
    _ensure_legacy_sweep_enabled()
    active_ids: list[UUID] = []
    graphs = (
        _workflow_queryset(organization)
        .select_related("owner")
        .prefetch_related("versions")
        .order_by("name")
    )

    for graph in graphs:
        latest_version = _latest_version(graph)
        if latest_version is None:
            continue

        for node in _extract_nodes(latest_version.graph_json):
            if not _is_agent_node(node):
                continue

            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue

            display_name = _node_name(node)
            latest_run = _find_latest_node_run(graph, node_id, organization)
            has_pending_decision = ApprovalTask.objects.filter(
                _run_scope_filter(organization, prefix="run__"),
                run__graph_version__graph=graph,
                node_id=node_id,
                status="pending",
            ).exists()
            policy_snapshot, capabilities, default_model = _agent_defaults(node)
            base_slug = slugify(display_name) or slugify(node_id) or "agent"
            workflow_token = str(graph.id).split("-")[0]
            node_token = slugify(node_id) or "node"
            entry, _ = AgentRegistryEntry.objects.update_or_create(
                organization=organization,
                source_workflow=graph,
                source_node_id=node_id,
                defaults={
                    "slug": f"{base_slug}-{workflow_token}-{node_token}"[:160],
                    "display_name": display_name,
                    "source_workflow_revision": latest_version,
                    "status": _derive_agent_status(latest_run, has_pending_decision),
                    "policy_snapshot_json": policy_snapshot
                    if isinstance(policy_snapshot, dict)
                    else {},
                    "capabilities_json": capabilities,
                    "default_model": default_model,
                    "last_execution": latest_run.run if latest_run else None,
                    "last_seen_at": latest_run.started_at if latest_run else None,
                },
            )
            active_ids.append(entry.id)

    AgentRegistryEntry.objects.filter(organization=organization).exclude(id__in=active_ids).delete()
    return list(
        AgentRegistryEntry.objects.filter(organization=organization).order_by("display_name")
    )


def _task_status_from(node_run: NodeRun) -> str:
    if node_run.status == "waiting":
        return "waiting_for_decision"
    run_status = str(node_run.run.status)
    if run_status == "canceled":
        return "cancelled"
    if node_run.status == "pending":
        return "queued"
    if node_run.status == "succeeded":
        return "completed"
    if node_run.status in {"running", "failed"}:
        return node_run.status
    return run_status


def _task_priority_from(run: Run) -> str:
    if run.status == "paused":
        return "high"
    if run.status == "failed":
        return "urgent"
    return "normal"


def _task_summary(node_run: NodeRun, agent: AgentRegistryEntry | None) -> str:
    actor = agent.display_name if agent else node_run.node_id
    workflow_name = node_run.run.graph_version.graph.name
    if node_run.status == "waiting":
        return f"{actor} is waiting for a decision in {workflow_name}."
    if node_run.status == "running":
        return f"{actor} is actively executing in {workflow_name}."
    if node_run.status == "failed":
        return f"{actor} failed during {workflow_name}."
    if node_run.status == "succeeded":
        return f"{actor} completed work in {workflow_name}."
    return f"{actor} is scheduled in {workflow_name}."


def _lifecycle_task_summary(task: TaskLifecycleRecord) -> str:
    if task.summary:
        return task.summary
    if task.status == "waiting_for_decision":
        return f"{task.title} is waiting for a human decision."
    if task.status == "retry_scheduled":
        return f"{task.title} has a bounded retry scheduled."
    if task.status == "dead_lettered":
        return f"{task.title} is dead-lettered and needs operator recovery."
    return f"{task.title} is {task.status.replace('_', ' ')}."


def _task_dead_letter_summary(task: TaskLifecycleRecord) -> dict[str, Any] | None:
    dead_letter = task.dead_letters.order_by("-created_at").first()
    if dead_letter is None:
        return None
    return {
        "id": str(dead_letter.id),
        "status": dead_letter.status,
        "reason": dead_letter.reason,
        "attempt_count": dead_letter.attempt_count,
        "last_error": dead_letter.last_error,
        "recovery_options": dead_letter.recovery_options,
        "acknowledged_at": dead_letter.acknowledged_at.isoformat()
        if dead_letter.acknowledged_at
        else None,
    }


def sync_task_records_for_organization(
    organization: Organization,
    agents: list[AgentRegistryEntry] | None = None,
) -> list[TaskRecord]:
    _ensure_legacy_sweep_enabled()
    agents = agents or list(AgentRegistryEntry.objects.filter(organization=organization))
    agents_by_key = {
        (str(agent.source_workflow_id), agent.source_node_id): agent for agent in agents
    }
    node_runs = (
        NodeRun.objects.filter(
            _run_scope_filter(organization, prefix="run__"),
        )
        .select_related("run__graph_version__graph")
        .order_by("-started_at", "-id")
    )
    active_ids: list[UUID] = []

    lifecycle_tasks = (
        TaskLifecycleRecord.objects.filter(
            organization=organization,
        )
        .select_related("run__graph_version__graph", "current_node_run")
        .order_by("-updated_at", "-created_at")
    )
    for lifecycle_task in lifecycle_tasks:
        run = lifecycle_task.run
        agent = agents_by_key.get((str(run.graph_version.graph_id), lifecycle_task.source_node_id))
        task, _ = TaskRecord.objects.update_or_create(
            organization=organization,
            external_key=lifecycle_task.external_key,
            defaults={
                "execution": run,
                "lifecycle_task": lifecycle_task,
                "agent": agent,
                "source_node_id": lifecycle_task.source_node_id,
                "title": lifecycle_task.title,
                "status": lifecycle_task.status,
                "priority": lifecycle_task.priority,
                "summary": _lifecycle_task_summary(lifecycle_task),
                "current_step": lifecycle_task.current_node_run,
                "current_decision": lifecycle_task.current_decision,
                "started_at": lifecycle_task.started_at,
                "ended_at": lifecycle_task.ended_at,
            },
        )
        active_ids.append(task.id)

    for node_run in node_runs:
        run = node_run.run
        agent = agents_by_key.get((str(run.graph_version.graph_id), node_run.node_id))
        if agent is None and node_run.node_type != "agent":
            continue
        external_key = f"{run.id}:{node_run.node_id}"
        if TaskLifecycleRecord.objects.filter(
            organization=organization,
            external_key=external_key,
        ).exists():
            continue
        title = f"{agent.display_name if agent else node_run.node_id} task"
        task, _ = TaskRecord.objects.update_or_create(
            organization=organization,
            external_key=external_key,
            defaults={
                "execution": run,
                "agent": agent,
                "source_node_id": node_run.node_id,
                "title": title,
                "status": _task_status_from(node_run),
                "priority": _task_priority_from(run),
                "summary": _task_summary(node_run, agent),
                "current_step": node_run,
                "started_at": node_run.started_at or run.started_at,
                "ended_at": node_run.ended_at or run.ended_at,
            },
        )
        active_ids.append(task.id)

    TaskRecord.objects.filter(
        organization=organization,
        lifecycle_task__isnull=True,
    ).exclude(id__in=active_ids).delete()
    return list(
        TaskRecord.objects.filter(organization=organization)
        .select_related("agent", "execution", "current_step", "current_decision")
        .order_by("-created_at")
    )


def _policy_decision_type(run: Run) -> str | None:
    text = (run.error_message or "").lower()
    for token in ("policy denied", "budget exceeded", "quota exceeded", "entitlement exceeded"):
        if token in text:
            return "policy_guardrail"
    return None


def sync_decision_records_for_organization(
    organization: Organization,
    agents: list[AgentRegistryEntry] | None = None,
    tasks: list[TaskRecord] | None = None,
) -> list[DecisionRecord]:
    _ensure_legacy_sweep_enabled()
    agents = agents or list(AgentRegistryEntry.objects.filter(organization=organization))
    tasks = tasks or list(TaskRecord.objects.filter(organization=organization))
    tasks_by_key = {(str(task.execution_id), task.source_node_id): task for task in tasks}
    agents_by_key = {
        (str(agent.source_workflow_id), agent.source_node_id): agent for agent in agents
    }
    active_ids: list[UUID] = []

    approvals = (
        ApprovalTask.objects.filter(_run_scope_filter(organization, prefix="run__"))
        .select_related("run__graph_version__graph")
        .order_by("-created_at")
    )
    for approval in approvals:
        run = approval.run
        task = tasks_by_key.get((str(run.id), approval.node_id))
        agent = (
            task.agent
            if task and task.agent_id
            else agents_by_key.get((str(run.graph_version.graph_id), approval.node_id))
        )
        decision, _ = DecisionRecord.objects.update_or_create(
            organization=organization,
            external_key=f"approval:{approval.id}",
            defaults={
                "execution": run,
                "task": task,
                "task_lifecycle": approval.task_lifecycle
                or (task.lifecycle_task if task else None),
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
        active_ids.append(decision.id)

    policy_runs = Run.objects.filter(_run_scope_filter(organization)).exclude(error_message="")
    for run in policy_runs:
        decision_type = _policy_decision_type(run)
        if not decision_type:
            continue
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
        active_ids.append(decision.id)

    reviews = AuditLog.objects.filter(
        tenant_id=organization.id,
        action__icontains="review",
    ).order_by("-created_at")
    for review in reviews:
        decision, _ = DecisionRecord.objects.update_or_create(
            organization=organization,
            external_key=f"audit-review:{review.id}",
            defaults={
                "execution": None,
                "task": None,
                "agent": None,
                "decision_type": "marketplace_review",
                "status": "resolved",
                "context_json": {
                    "action": review.action,
                    "resource_type": review.resource_type,
                    "resource_id": review.resource_id,
                    "metadata": review.metadata,
                },
                "resolution_json": review.metadata if isinstance(review.metadata, dict) else {},
                "requested_at": review.created_at,
                "resolved_at": review.created_at,
            },
        )
        active_ids.append(decision.id)

    DecisionRecord.objects.filter(organization=organization).exclude(id__in=active_ids).delete()

    pending_decisions = {
        (str(decision.execution_id), decision.task.source_node_id if decision.task else "")
        if decision.execution_id
        else None: decision
        for decision in DecisionRecord.objects.filter(organization=organization, status="pending")
        .select_related("task")
        .order_by("-requested_at")
    }
    for task in TaskRecord.objects.filter(organization=organization):
        task.current_decision = pending_decisions.get((str(task.execution_id), task.source_node_id))
        task.save(update_fields=["current_decision", "updated_at"])
        if task.lifecycle_task_id and task.current_decision_id:
            TaskLifecycleRecord.objects.filter(id=task.lifecycle_task_id).update(
                current_decision_id=task.current_decision_id
            )

    return list(
        DecisionRecord.objects.filter(organization=organization)
        .select_related("execution", "task", "agent", "source_approval_task")
        .order_by("-requested_at", "-created_at")
    )


def sync_accounting_for_organization(
    organization: Organization,
    agents: list[AgentRegistryEntry] | None = None,
    tasks: list[TaskRecord] | None = None,
) -> list[CostLedgerEntry]:
    _ensure_legacy_sweep_enabled()
    agents = agents or list(AgentRegistryEntry.objects.filter(organization=organization))
    tasks = tasks or list(TaskRecord.objects.filter(organization=organization))
    tasks_by_run_node = {(str(task.execution_id), task.source_node_id): task for task in tasks}
    active_ids: list[UUID] = []

    llm_entries = LLMUsage.objects.filter(tenant_id=organization.id).select_related(
        "run__graph_version"
    )
    for llm_usage in llm_entries:
        task = tasks_by_run_node.get((str(llm_usage.run_id), llm_usage.node_id))
        agent = task.agent if task else None
        unit_cost = (
            llm_usage.cost_usd / llm_usage.total_tokens if llm_usage.total_tokens else DECIMAL_ZERO
        )
        ledger, _ = CostLedgerEntry.objects.update_or_create(
            organization=organization,
            external_key=f"llm:{llm_usage.id}",
            defaults={
                "execution": llm_usage.run,
                "task": task,
                "agent": agent,
                "workflow_revision": llm_usage.run.graph_version,
                "provider": llm_usage.provider,
                "model": llm_usage.model,
                "cost_type": "llm",
                "quantity": Decimal(llm_usage.total_tokens),
                "unit_cost_usd": unit_cost,
                "total_cost_usd": llm_usage.cost_usd,
                "occurred_at": llm_usage.created_at,
            },
        )
        active_ids.append(ledger.id)

    memory_entries = MemoryUsage.objects.filter(tenant_id=organization.id)
    for memory_usage in memory_entries:
        occurred_at = datetime.combine(memory_usage.usage_date, datetime.min.time(), tzinfo=UTC)
        quantity = Decimal(memory_usage.summarization_total_tokens)
        unit_cost = memory_usage.summarization_cost_usd / quantity if quantity > 0 else DECIMAL_ZERO
        ledger, _ = CostLedgerEntry.objects.update_or_create(
            organization=organization,
            external_key=f"memory:{memory_usage.id}",
            defaults={
                "execution": None,
                "task": None,
                "agent": None,
                "workflow_revision": None,
                "provider": "forgegraph",
                "model": "memory-summarization",
                "cost_type": "memory_summarization",
                "quantity": quantity,
                "unit_cost_usd": unit_cost,
                "total_cost_usd": memory_usage.summarization_cost_usd,
                "occurred_at": occurred_at,
            },
        )
        active_ids.append(ledger.id)

    CostLedgerEntry.objects.filter(organization=organization).exclude(id__in=active_ids).delete()
    ledger_entries = list(
        CostLedgerEntry.objects.filter(organization=organization)
        .select_related("agent", "task", "execution", "workflow_revision")
        .order_by("-occurred_at", "-created_at")
    )
    _refresh_cost_aggregates(organization, ledger_entries)
    return ledger_entries


def _aggregate_key(entry: CostLedgerEntry, grain: str) -> tuple[str, str, str, str, str, datetime]:
    occurred_at = entry.occurred_at.astimezone(UTC)
    period_start = occurred_at.replace(minute=0, second=0, microsecond=0)
    if grain == "daily":
        period_start = period_start.replace(hour=0)
    return (
        grain,
        str(entry.agent_id or ""),
        entry.provider,
        entry.model,
        entry.cost_type,
        period_start,
    )


def _refresh_cost_aggregates(
    organization: Organization,
    ledger_entries: list[CostLedgerEntry],
) -> None:
    active_ids: list[UUID] = []
    buckets: dict[tuple[str, str, str, str, str, datetime], list[CostLedgerEntry]] = defaultdict(
        list
    )
    for entry in ledger_entries:
        buckets[_aggregate_key(entry, "hourly")].append(entry)
        buckets[_aggregate_key(entry, "daily")].append(entry)

    for key, entries in buckets.items():
        grain, agent_id, provider, model, cost_type, period_start = key
        period_end = period_start + (timedelta(hours=1) if grain == "hourly" else timedelta(days=1))
        total_cost = sum((entry.total_cost_usd for entry in entries), DECIMAL_ZERO)
        total_quantity = sum((entry.quantity for entry in entries), DECIMAL_ZERO)
        workflow_revision_id = next(
            (entry.workflow_revision_id for entry in entries if entry.workflow_revision_id), None
        )
        aggregate, _ = CostAggregate.objects.update_or_create(
            organization=organization,
            external_key=f"{grain}:{agent_id}:{provider}:{model}:{cost_type}:{period_start.isoformat()}",
            defaults={
                "agent_id": agent_id or None,
                "task": None,
                "workflow_revision_id": workflow_revision_id,
                "grain": grain,
                "period_start": period_start,
                "period_end": period_end,
                "provider": provider,
                "model": model,
                "cost_type": cost_type,
                "total_cost_usd": total_cost,
                "total_quantity": total_quantity,
                "entry_count": len(entries),
            },
        )
        active_ids.append(aggregate.id)

    CostAggregate.objects.filter(organization=organization).exclude(id__in=active_ids).delete()


def refresh_phase1_projections_for_organization(organization: Organization) -> ProjectionBundle:
    _ensure_legacy_sweep_enabled()
    with transaction.atomic():
        agents = sync_agent_registry_for_organization(organization)
        tasks = sync_task_records_for_organization(organization, agents)
        decisions = sync_decision_records_for_organization(organization, agents, tasks)
        ledger = sync_accounting_for_organization(organization, agents, tasks)
    return ProjectionBundle(
        organization=organization,
        agents=agents,
        tasks=tasks,
        decisions=decisions,
        ledger=ledger,
    )


def refresh_phase1_projections(user: User) -> ProjectionBundle:
    _ensure_legacy_sweep_enabled()
    organization = _organization_for_user(user)
    return refresh_phase1_projections_for_organization(organization)


def projection_metadata(organization: Organization) -> dict[str, Any]:
    computed_at = timezone.now()
    state_feed_version = (
        OrganizationStateFeedEvent.objects.filter(organization=organization)
        .order_by("-state_version")
        .values_list("state_version", flat=True)
        .first()
        or 0
    )
    latest_event = (
        DomainEvent.objects.filter(organization=organization).order_by("-sequence").first()
    )
    cursors = list(ProjectionCursor.objects.filter(organization=organization))
    cursor = min(cursors, key=lambda value: int(value.last_sequence), default=None)
    last_sequence = int(cursor.last_sequence) if cursor is not None else 0
    last_event_id = str(cursor.last_event_id or "") if cursor is not None else ""
    pending_event = None
    if latest_event is not None and last_sequence < int(latest_event.sequence):
        pending_event = (
            DomainEvent.objects.filter(organization=organization, sequence__gt=last_sequence)
            .order_by("sequence")
            .first()
        )
    lag_seconds = 0.0
    if pending_event is not None:
        lag_seconds = max(0.0, (computed_at - pending_event.occurred_at).total_seconds())
    active_dead_letter = EventDeadLetterRecord.objects.filter(
        organization=organization,
        source="os_projection_worker",
        status__in={"active", "replay_requested"},
    ).exists()
    cursor_statuses = {cursor.status for cursor in cursors}
    if "rebuilding" in cursor_statuses:
        status = "rebuilding"
    elif active_dead_letter or "degraded" in cursor_statuses:
        status = "degraded"
    elif pending_event is not None:
        status = "stale"
    else:
        status = "fresh"
    lag_ms = int(lag_seconds * 1000)

    return {
        "computed_at": computed_at.isoformat(),
        "last_sequence": last_sequence,
        "last_event_id": last_event_id,
        "state_feed_version": int(state_feed_version),
        "lag_seconds": lag_seconds,
        "status": status,
        "projection_lag_ms": lag_ms,
        "watermark": cursor.updated_at.isoformat() if cursor is not None else None,
    }


def agent_summary(agent: AgentRegistryEntry) -> dict[str, Any]:
    task_count = TaskRecord.objects.filter(agent=agent).count()
    pending_decisions = DecisionRecord.objects.filter(agent=agent, status="pending").count()
    total_cost = (
        CostLedgerEntry.objects.filter(agent=agent)
        .aggregate(total=models.Sum("total_cost_usd"))
        .get("total")
        or DECIMAL_ZERO
    )
    return {
        "id": str(agent.id),
        "organization_id": str(agent.organization_id),
        "slug": agent.slug,
        "display_name": agent.display_name,
        "status": agent.status,
        "source_workflow_id": str(agent.source_workflow_id),
        "source_workflow_revision_id": str(agent.source_workflow_revision_id)
        if agent.source_workflow_revision_id
        else None,
        "source_node_id": agent.source_node_id,
        "default_model": agent.default_model,
        "last_execution_id": str(agent.last_execution_id) if agent.last_execution_id else None,
        "last_seen_at": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
        "policy_snapshot_json": agent.policy_snapshot_json,
        "capabilities_json": agent.capabilities_json,
        "task_count": task_count,
        "pending_decisions": pending_decisions,
        "total_cost_usd": float(total_cost),
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


def task_summary(task: TaskRecord) -> dict[str, Any]:
    lifecycle_task = task.lifecycle_task if task.lifecycle_task_id else None
    return {
        "id": str(task.id),
        "organization_id": str(task.organization_id),
        "execution_id": str(task.execution_id),
        "agent_id": str(task.agent_id) if task.agent_id else None,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "summary": task.summary,
        "lifecycle_task_id": str(task.lifecycle_task_id) if task.lifecycle_task_id else None,
        "source_node_id": task.source_node_id,
        "current_step_id": str(task.current_step_id) if task.current_step_id else None,
        "current_decision_id": str(task.current_decision_id) if task.current_decision_id else None,
        "attempt_count": lifecycle_task.current_attempt if lifecycle_task is not None else None,
        "retry_metadata": lifecycle_task.retry_metadata if lifecycle_task is not None else {},
        "dead_letter": _task_dead_letter_summary(lifecycle_task)
        if lifecycle_task is not None
        else None,
        "stale_event_count": lifecycle_task.stale_event_count if lifecycle_task is not None else 0,
        "late_event_count": lifecycle_task.late_event_count if lifecycle_task is not None else 0,
        "recovery_options": lifecycle_task.recovery_options if lifecycle_task is not None else [],
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "ended_at": task.ended_at.isoformat() if task.ended_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def decision_summary(decision: DecisionRecord) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "organization_id": str(decision.organization_id),
        "execution_id": str(decision.execution_id) if decision.execution_id else None,
        "task_id": str(decision.task_id) if decision.task_id else None,
        "task_lifecycle_id": str(decision.task_lifecycle_id)
        if decision.task_lifecycle_id
        else None,
        "agent_id": str(decision.agent_id) if decision.agent_id else None,
        "decision_type": decision.decision_type,
        "status": decision.status,
        "source_approval_task_id": str(decision.source_approval_task_id)
        if decision.source_approval_task_id
        else None,
        "context_json": decision.context_json,
        "resolution_json": decision.resolution_json,
        "requested_at": decision.requested_at.isoformat() if decision.requested_at else None,
        "resolved_at": decision.resolved_at.isoformat() if decision.resolved_at else None,
        "created_at": decision.created_at.isoformat(),
        "updated_at": decision.updated_at.isoformat(),
    }


def cost_ledger_summary(entry: CostLedgerEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "organization_id": str(entry.organization_id),
        "execution_id": str(entry.execution_id) if entry.execution_id else None,
        "task_id": str(entry.task_id) if entry.task_id else None,
        "agent_id": str(entry.agent_id) if entry.agent_id else None,
        "workflow_revision_id": str(entry.workflow_revision_id)
        if entry.workflow_revision_id
        else None,
        "provider": entry.provider,
        "model": entry.model,
        "cost_type": entry.cost_type,
        "quantity": float(entry.quantity),
        "unit_cost_usd": float(entry.unit_cost_usd),
        "total_cost_usd": float(entry.total_cost_usd),
        "occurred_at": entry.occurred_at.isoformat(),
    }


def accounting_overview(organization: Organization) -> dict[str, Any]:
    computed_at = timezone.now().isoformat()
    ledger_qs = CostLedgerEntry.objects.filter(organization=organization)
    total_cost = (
        ledger_qs.aggregate(total=models.Sum("total_cost_usd")).get("total") or DECIMAL_ZERO
    )
    cost_by_type = list(
        ledger_qs.values("cost_type")
        .annotate(total_cost_usd=models.Sum("total_cost_usd"), entry_count=models.Count("id"))
        .order_by("cost_type")
    )
    top_agents = (
        AgentRegistryEntry.objects.filter(organization=organization)
        .annotate(total_cost_usd=models.Sum("cost_ledger_entries__total_cost_usd"))
        .order_by("-total_cost_usd", "display_name")[:5]
    )
    recent_aggregates = list(
        CostAggregate.objects.filter(organization=organization, grain="daily").order_by(
            "-period_start"
        )[:14]
    )
    cost_metric = AvailableAccountingMetric(
        value=float(total_cost),
        currency="USD",
        computed_at=computed_at,
        source="backend_ledger",
    ).to_json()
    revenue_metric = NotInstrumentedAccountingMetric(
        reason="Backend revenue ledger is not instrumented yet.",
        computed_at=computed_at,
        source="backend_accounting",
    ).to_json()
    profit_metric = NotInstrumentedAccountingMetric(
        reason="Backend profit ledger is not instrumented yet.",
        computed_at=computed_at,
        source="backend_accounting",
    ).to_json()
    return {
        "organization_id": str(organization.id),
        "total_cost_usd": float(total_cost),
        "generated_at": computed_at,
        "projection": projection_metadata(organization),
        "metrics": {
            "cost": cost_metric,
            "revenue": revenue_metric,
            "profit": profit_metric,
        },
        "metric_provenance": {
            "total_cost_usd": {
                "source": cost_metric["source"],
                "computed_at": cost_metric["computed_at"],
                "freshness_ms": 0,
                "status": cost_metric["status"],
                "value": cost_metric["value"],
            },
            "revenue": {
                "source": revenue_metric["source"],
                "computed_at": revenue_metric["computed_at"],
                "freshness_ms": 0,
                "status": "not_instrumented",
                "value": None,
            },
            "profit": {
                "source": profit_metric["source"],
                "computed_at": profit_metric["computed_at"],
                "freshness_ms": 0,
                "status": "not_instrumented",
                "value": None,
            },
        },
        "cost_by_type": [
            {
                "cost_type": row["cost_type"],
                "total_cost_usd": float(row["total_cost_usd"] or DECIMAL_ZERO),
                "entry_count": row["entry_count"],
            }
            for row in cost_by_type
        ],
        "top_agents": [
            {
                "id": str(agent.id),
                "display_name": agent.display_name,
                "status": agent.status,
                "total_cost_usd": float(agent.total_cost_usd or DECIMAL_ZERO),
            }
            for agent in top_agents
        ],
        "recent_aggregates": [
            {
                "id": str(aggregate.id),
                "grain": aggregate.grain,
                "period_start": aggregate.period_start.isoformat(),
                "period_end": aggregate.period_end.isoformat(),
                "provider": aggregate.provider,
                "model": aggregate.model,
                "cost_type": aggregate.cost_type,
                "total_cost_usd": float(aggregate.total_cost_usd),
                "total_quantity": float(aggregate.total_quantity),
                "entry_count": aggregate.entry_count,
            }
            for aggregate in recent_aggregates
        ],
    }


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone=UTC)
    return parsed


def _latest_datetime(*values: datetime | str | None) -> datetime | None:
    parsed_values = [parsed for value in values if (parsed := _coerce_datetime(value)) is not None]
    return max(parsed_values) if parsed_values else None


def _section_metadata(
    *,
    source: str,
    computed_at: datetime | str | None,
    last_updated_at: datetime | str | None = None,
    status: str = "fresh",
    now: datetime | None = None,
) -> dict[str, Any]:
    measured_at = now or timezone.now()
    computed_dt = _coerce_datetime(computed_at) or measured_at
    updated_dt = _coerce_datetime(last_updated_at) or computed_dt
    normalized_status = str(status or "fresh")
    freshness_ms = max(0, int((measured_at - updated_dt).total_seconds() * 1000))
    return {
        "source": source,
        "computed_at": computed_dt.isoformat(),
        "last_updated_at": updated_dt.isoformat(),
        "freshness_ms": freshness_ms,
        "status": normalized_status,
        "stale": normalized_status in {"stale", "rebuilding"},
        "degraded": normalized_status == "degraded",
    }


def organization_state_summary(organization: Organization) -> dict[str, Any]:
    now = timezone.now()
    projection = projection_metadata(organization)
    active_agents = AgentRegistryEntry.objects.filter(
        organization=organization,
        status__in={"active", "attention"},
    ).order_by("status", "display_name")
    active_tasks = TaskRecord.objects.filter(
        organization=organization,
        status__in=TASK_ACTIVE_STATUSES,
    ).select_related("agent", "execution")[:8]
    blocked_task_qs = TaskRecord.objects.filter(
        organization=organization,
        status__in=TASK_BLOCKED_STATUSES,
    )
    pending_decisions = DecisionRecord.objects.filter(
        organization=organization,
        status="pending",
    ).select_related("agent", "execution")[:8]
    recent_executions = (
        Run.objects.filter(_run_scope_filter(organization))
        .select_related("graph_version__graph")
        .order_by("-started_at")[:8]
    )
    policy = TenantPolicy.objects.filter(tenant_id=organization.id).first()
    memory_count = MemoryObservation.objects.filter(
        tenant_id=organization.id, deleted_at__isnull=True
    ).count()
    total_cost = (
        CostLedgerEntry.objects.filter(organization=organization)
        .aggregate(total=models.Sum("total_cost_usd"))
        .get("total")
        or DECIMAL_ZERO
    )
    accounting = accounting_overview(organization)
    task_dead_letter_count = TaskDeadLetterRecord.objects.filter(
        lifecycle_task__organization=organization,
        status="active",
    ).count()
    event_dead_letter_count = EventDeadLetterRecord.objects.filter(
        organization=organization,
        status__in={"active", "replay_requested"},
    ).count()
    runtime_intent_dead_letter_qs = RuntimeIntentOutcome.objects.filter(
        run__organization=organization,
        outcome="dead_lettered",
        acknowledged_at__isnull=True,
    )
    runtime_intent_dead_letter_count = runtime_intent_dead_letter_qs.count()
    dead_letter_count = (
        task_dead_letter_count + event_dead_letter_count + runtime_intent_dead_letter_count
    )
    operations_status = (
        "degraded"
        if dead_letter_count > 0 or projection["status"] in {"stale", "rebuilding", "degraded"}
        else "fresh"
    )
    runtime_intent_lag_seconds = 0.0
    oldest_runtime_intent_dead_letter = runtime_intent_dead_letter_qs.order_by(
        "processed_at"
    ).first()
    if oldest_runtime_intent_dead_letter is not None:
        runtime_intent_lag_seconds = max(
            0.0,
            (now - oldest_runtime_intent_dead_letter.processed_at).total_seconds(),
        )

    active_agent_count = active_agents.count()
    active_task_count = TaskRecord.objects.filter(
        organization=organization, status__in=TASK_ACTIVE_STATUSES
    ).count()
    pending_decision_count = DecisionRecord.objects.filter(
        organization=organization, status="pending"
    ).count()
    execution_count_24h = Run.objects.filter(
        _run_scope_filter(organization),
        started_at__gte=now - timedelta(hours=24),
    ).count()
    memory_write_count_24h = MemoryObservation.objects.filter(
        tenant_id=organization.id,
        deleted_at__isnull=True,
        created_at__gte=now - timedelta(hours=24),
    ).count()
    cost_metric = accounting.get("metrics", {}).get("cost", {})
    cost_metric_status = (
        "fresh"
        if cost_metric.get("status") == "available" and operations_status == "fresh"
        else operations_status
    )
    cost_computed_at = cost_metric.get("computed_at") or accounting.get("generated_at") or now
    running_updated_at = _latest_datetime(
        active_agents.aggregate(latest=models.Max("updated_at")).get("latest"),
        TaskRecord.objects.filter(organization=organization, status__in=TASK_ACTIVE_STATUSES)
        .aggregate(latest=models.Max("updated_at"))
        .get("latest"),
    )
    blocked_updated_at = blocked_task_qs.aggregate(latest=models.Max("updated_at")).get("latest")
    decisions_updated_at = (
        DecisionRecord.objects.filter(organization=organization, status="pending")
        .aggregate(latest=models.Max("updated_at"))
        .get("latest")
    )
    costs_updated_at = (
        CostLedgerEntry.objects.filter(organization=organization)
        .aggregate(latest=models.Max("occurred_at"))
        .get("latest")
    )
    memory_updated_at = (
        MemoryObservation.objects.filter(tenant_id=organization.id, deleted_at__isnull=True)
        .aggregate(latest=models.Max("updated_at"))
        .get("latest")
    )
    task_dead_letter_updated_at = (
        TaskDeadLetterRecord.objects.filter(
            lifecycle_task__organization=organization,
            status="active",
        )
        .aggregate(latest=models.Max("updated_at"))
        .get("latest")
    )
    event_dead_letter_updated_at = (
        EventDeadLetterRecord.objects.filter(
            organization=organization,
            status__in={"active", "replay_requested"},
        )
        .aggregate(latest=models.Max("last_seen_at"))
        .get("latest")
    )
    runtime_intent_dead_letter_updated_at = runtime_intent_dead_letter_qs.aggregate(
        latest=models.Max("updated_at")
    ).get("latest")
    failures_updated_at = _latest_datetime(
        task_dead_letter_updated_at,
        event_dead_letter_updated_at,
        runtime_intent_dead_letter_updated_at,
    )
    projection_section = {
        **projection,
        **_section_metadata(
            source="backend_projection",
            computed_at=projection.get("computed_at"),
            last_updated_at=projection.get("watermark") or projection.get("computed_at"),
            status=str(projection.get("status") or "fresh"),
            now=now,
        ),
    }

    return {
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
        },
        "summary": {
            "active_agent_count": active_agent_count,
            "active_task_count": active_task_count,
            "pending_decision_count": pending_decision_count,
            "execution_count_24h": execution_count_24h,
            "memory_observation_count": memory_count,
            "total_cost_usd": float(total_cost),
        },
        "running": {
            **_section_metadata(
                source="backend_projection",
                computed_at=projection.get("computed_at"),
                last_updated_at=running_updated_at,
                status=str(projection.get("status") or "fresh"),
                now=now,
            ),
            "active_agent_count": active_agent_count,
            "running_task_count": active_task_count,
            "operation_count_24h": execution_count_24h,
            "items": [task_summary(task) for task in active_tasks],
        },
        "blocked": {
            **_section_metadata(
                source="backend_projection",
                computed_at=projection.get("computed_at"),
                last_updated_at=blocked_updated_at,
                status=str(projection.get("status") or "fresh"),
                now=now,
            ),
            "blocked_task_count": blocked_task_qs.count(),
            "items": [
                task_summary(task)
                for task in blocked_task_qs.select_related("agent", "execution").order_by(
                    "-updated_at"
                )[:8]
            ],
        },
        "decisions": {
            **_section_metadata(
                source="backend_projection",
                computed_at=projection.get("computed_at"),
                last_updated_at=decisions_updated_at,
                status=str(projection.get("status") or "fresh"),
                now=now,
            ),
            "pending_decision_count": pending_decision_count,
            "items": [decision_summary(decision) for decision in pending_decisions],
        },
        "costs": {
            **_section_metadata(
                source=str(cost_metric.get("source") or "backend_ledger"),
                computed_at=cost_computed_at,
                last_updated_at=costs_updated_at,
                status=cost_metric_status,
                now=now,
            ),
            "total_cost_usd": float(total_cost),
            "currency": cost_metric.get("currency") or "USD",
            "metric": cost_metric,
            "cost_by_type": accounting["cost_by_type"],
        },
        "failures": {
            **_section_metadata(
                source="backend_ops",
                computed_at=now,
                last_updated_at=failures_updated_at,
                status=operations_status,
                now=now,
            ),
            "dead_letter_count": dead_letter_count,
            "task_dead_letter_count": task_dead_letter_count,
            "event_dead_letter_count": event_dead_letter_count,
            "runtime_intent_dead_letter_count": runtime_intent_dead_letter_count,
            "runtime_intent_lag_seconds": runtime_intent_lag_seconds,
        },
        "active_agents": [agent_summary(agent) for agent in active_agents[:6]],
        "active_tasks": [task_summary(task) for task in active_tasks],
        "pending_decisions": [decision_summary(decision) for decision in pending_decisions],
        "recent_executions": [
            {
                "id": str(run.id),
                "workflow_id": str(run.graph_version.graph_id),
                "workflow_name": run.graph_version.graph.name,
                "workflow_revision_id": str(run.graph_version_id),
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "duration_ms": run.duration_ms,
            }
            for run in recent_executions
        ],
        "memory": {
            **_section_metadata(
                source="backend_memory",
                computed_at=projection.get("computed_at"),
                last_updated_at=memory_updated_at,
                status=str(projection.get("status") or "fresh"),
                now=now,
            ),
            "active_observation_count": memory_count,
            "memory_write_count_24h": memory_write_count_24h,
            "recent_topics": list(
                MemoryObservation.objects.filter(tenant_id=organization.id, deleted_at__isnull=True)
                .exclude(topic_key="")
                .order_by("-last_seen_at")
                .values_list("topic_key", flat=True)[:6]
            ),
        },
        "policy": {
            "configured": policy is not None,
            "allowed_providers": policy.allowed_providers if policy else [],
            "allowed_models": policy.allowed_models if policy else [],
            "http_default_deny": policy.http_default_deny if policy else False,
        },
        "accounting": accounting,
        "operations": {
            "status": operations_status,
            "dead_letter_count": dead_letter_count,
            "task_dead_letter_count": task_dead_letter_count,
            "event_dead_letter_count": event_dead_letter_count,
            "runtime_intent_dead_letter_count": runtime_intent_dead_letter_count,
            "projection_status": projection["status"],
            "projection_lag_seconds": projection["lag_seconds"],
            "runtime_intent_lag_seconds": runtime_intent_lag_seconds,
            "generated_at": now.isoformat(),
        },
        "generated_at": now.isoformat(),
        "projection": projection_section,
    }
