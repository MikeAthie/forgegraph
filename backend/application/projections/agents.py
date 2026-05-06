from __future__ import annotations

from typing import Any

from django.utils.text import slugify

from application.services.os_projections import (
    _agent_defaults,
    _derive_agent_status,
    _extract_nodes,
    _find_latest_node_run,
    _is_agent_node,
    _node_name,
)
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    DomainEvent,
    GraphVersion,
    NodeRun,
    Run,
)


def apply(event: DomainEvent) -> None:
    node_run_id = str(event.payload.get("node_run_id") or "").strip()
    if node_run_id and str(event.event_type or "").startswith("node_run."):
        if _project_node_run_agent(node_run_id):
            return

    graph_version_id = str(event.payload.get("graph_version_id") or "").strip()
    run_id = str(event.payload.get("run_id") or "").strip()
    if graph_version_id:
        _project_graph_version(graph_version_id)
        return
    if run_id:
        run = Run.objects.select_related("graph_version__graph").filter(id=run_id).first()
        if run is not None:
            _project_graph_version(str(run.graph_version_id))


def _project_node_run_agent(node_run_id: str) -> bool:
    node_run = (
        NodeRun.objects.select_related(
            "run",
            "run__graph_version",
            "run__graph_version__graph",
            "run__graph_version__graph__owner__default_organization",
            "run__owner__default_organization",
            "run__organization",
        )
        .filter(id=node_run_id)
        .first()
    )
    if node_run is None:
        return False
    if node_run.node_type != "agent":
        return True

    run = node_run.run
    version = run.graph_version
    graph = version.graph
    organization = run.organization or graph.organization or run.owner.default_organization
    if organization is None:
        return True

    entry = AgentRegistryEntry.objects.filter(
        organization=organization,
        source_workflow=graph,
        source_node_id=node_run.node_id,
    ).first()
    has_pending_decision = ApprovalTask.objects.filter(
        run__organization=organization,
        run__graph_version__graph=graph,
        node_id=node_run.node_id,
        status="pending",
    ).exists()
    if entry is None:
        node = _agent_node_for(version, node_run.node_id)
        if node is None:
            return True
        display_name = _node_name(node)
        policy_snapshot, capabilities, default_model = _agent_defaults(node)
        base_slug = slugify(display_name) or slugify(node_run.node_id) or "agent"
        workflow_token = str(graph.id).split("-")[0]
        node_token = slugify(node_run.node_id) or "node"
        AgentRegistryEntry.objects.update_or_create(
            organization=organization,
            source_workflow=graph,
            source_node_id=node_run.node_id,
            defaults={
                "slug": f"{base_slug}-{workflow_token}-{node_token}"[:160],
                "display_name": display_name,
                "source_workflow_revision": version,
                "status": _derive_agent_status(node_run, has_pending_decision),
                "policy_snapshot_json": policy_snapshot
                if isinstance(policy_snapshot, dict)
                else {},
                "capabilities_json": capabilities,
                "default_model": default_model,
                "last_execution": run,
                "last_seen_at": node_run.started_at,
            },
        )
    else:
        entry.status = _derive_agent_status(node_run, has_pending_decision)
        entry.source_workflow_revision = version
        entry.last_execution = run
        entry.last_seen_at = node_run.started_at
        entry.save(
            update_fields=[
                "status",
                "source_workflow_revision",
                "last_execution",
                "last_seen_at",
                "updated_at",
            ]
        )
    return True


def _agent_node_for(version: GraphVersion, node_id: str) -> dict[str, Any] | None:
    for node in _extract_nodes(version.graph_json):
        candidate_node_id = str(node.get("id") or "").strip()
        if candidate_node_id == node_id and _is_agent_node(node):
            return node
    return None


def _project_graph_version(graph_version_id: str) -> None:
    version = (
        GraphVersion.objects.select_related("graph", "graph__owner__default_organization")
        .filter(id=graph_version_id)
        .first()
    )
    if version is None:
        return

    organization = version.graph.organization or version.graph.owner.default_organization
    if organization is None:
        return

    active_ids: list[Any] = []
    for node in _extract_nodes(version.graph_json):
        if not _is_agent_node(node):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        display_name = _node_name(node)
        latest_node_run = _find_latest_node_run(version.graph, node_id, organization)
        has_pending_decision = ApprovalTask.objects.filter(
            run__organization=organization,
            run__graph_version__graph=version.graph,
            node_id=node_id,
            status="pending",
        ).exists()
        policy_snapshot, capabilities, default_model = _agent_defaults(node)
        base_slug = slugify(display_name) or slugify(node_id) or "agent"
        workflow_token = str(version.graph_id).split("-")[0]
        node_token = slugify(node_id) or "node"
        entry, _ = AgentRegistryEntry.objects.update_or_create(
            organization=organization,
            source_workflow=version.graph,
            source_node_id=node_id,
            defaults={
                "slug": f"{base_slug}-{workflow_token}-{node_token}"[:160],
                "display_name": display_name,
                "source_workflow_revision": version,
                "status": _derive_agent_status(latest_node_run, has_pending_decision),
                "policy_snapshot_json": policy_snapshot
                if isinstance(policy_snapshot, dict)
                else {},
                "capabilities_json": capabilities,
                "default_model": default_model,
                "last_execution": latest_node_run.run if latest_node_run else None,
                "last_seen_at": latest_node_run.started_at if latest_node_run else None,
            },
        )
        active_ids.append(entry.id)

    AgentRegistryEntry.objects.filter(
        organization=organization, source_workflow=version.graph
    ).exclude(id__in=active_ids).delete()
