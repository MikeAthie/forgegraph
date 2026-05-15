from __future__ import annotations

from application.services.os_projections import (
    _lifecycle_task_summary,
    _task_priority_from,
    _task_status_from,
    _task_summary,
)
from infrastructure.orm.models import (
    AgentRegistryEntry,
    DomainEvent,
    NodeRun,
    Run,
    TaskLifecycleRecord,
    TaskRecord,
)


def apply(event: DomainEvent) -> None:
    task_lifecycle_id = str(event.payload.get("task_lifecycle_id") or "").strip()
    node_run_id = str(event.payload.get("node_run_id") or "").strip()
    run_id = str(event.payload.get("run_id") or "").strip()

    if task_lifecycle_id:
        task = (
            TaskLifecycleRecord.objects.select_related(
                "run__graph_version__graph",
                "current_node_run",
                "current_decision",
            )
            .filter(id=task_lifecycle_id)
            .first()
        )
        if task is not None:
            _project_lifecycle_task(task)

    if node_run_id:
        node_run = (
            NodeRun.objects.select_related("run__graph_version__graph")
            .filter(id=node_run_id)
            .first()
        )
        if node_run is not None:
            _project_node_run(node_run)

    if run_id and not task_lifecycle_id and not node_run_id:
        for task in TaskLifecycleRecord.objects.filter(run_id=run_id).select_related(
            "run__graph_version__graph",
            "current_node_run",
            "current_decision",
        ):
            _project_lifecycle_task(task)
        for node_run in NodeRun.objects.filter(run_id=run_id).select_related(
            "run__graph_version__graph"
        ):
            _project_node_run(node_run)


def _project_lifecycle_task(lifecycle_task: TaskLifecycleRecord) -> TaskRecord:
    run = lifecycle_task.run
    agent = _agent_for(run=run, node_id=lifecycle_task.source_node_id)
    task, _ = TaskRecord.objects.update_or_create(
        organization=lifecycle_task.organization,
        external_key=lifecycle_task.external_key,
        defaults={
            "execution": run,
            "lifecycle_task": lifecycle_task,
            "agent": agent,
            "department": lifecycle_task.current_department,
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
    return task


def _project_node_run(node_run: NodeRun) -> TaskRecord | None:
    run = node_run.run
    organization = (
        run.organization or run.graph_version.graph.organization or run.owner.default_organization
    )
    if organization is None:
        return None

    external_key = f"{run.id}:{node_run.node_id}"
    if TaskLifecycleRecord.objects.filter(
        organization=organization, external_key=external_key
    ).exists():
        return None

    agent = _agent_for(run=run, node_id=node_run.node_id)
    if agent is None and node_run.node_type != "agent":
        return None

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
    return task


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
