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
    Run,
)


def apply(event: DomainEvent) -> None:
    graph_version_id = str(event.payload.get("graph_version_id") or "").strip()
    run_id = str(event.payload.get("run_id") or "").strip()
    if graph_version_id:
        _project_graph_version(graph_version_id)
        return
    if run_id:
        run = Run.objects.select_related("graph_version__graph").filter(id=run_id).first()
        if run is not None:
            _project_graph_version(str(run.graph_version_id))


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
