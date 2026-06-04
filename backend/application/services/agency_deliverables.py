"""Backend-owned Atlas deliverable assembly services."""

from __future__ import annotations

from typing import Any

from application.services.agency_deliverable_catalog import (
    MVP_DELIVERABLE_TYPES,
    DeliverableDefinition,
    get_deliverable_definition,
    list_deliverable_definitions,
)
from application.services.company_archive import ArchiveService
from infrastructure.orm.models import (
    Asset,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    StateProjection,
    User,
    WorkWhiteboard,
)

ASSEMBLY_SOURCE = "atlas_deliverable_assembly"
CATALOG_SLUG = "digital-marketing-agency-engagement"
CATALOG_SOURCE_KEY = "atlas-catalog:digital-marketing-agency-engagement"
REQUIRED_PACK_ID = "digital_marketing_pro.v1"


def ensure_atlas_service_engagement(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
) -> ServiceEngagement:
    organization = whiteboard.organization or whiteboard.company.organization
    if organization is None:
        raise ValueError("Atlas deliverable assembly requires an organization-scoped whiteboard.")

    catalog, created = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug=CATALOG_SLUG,
        defaults={
            "title": "Digital Marketing Agency Engagement",
            "description": "Customer-facing Atlas digital marketing delivery package.",
            "status": "active",
            "visibility": "customer",
            "audience": "digital_marketing_client",
            "required_pack_ids_json": [REQUIRED_PACK_ID],
            "deliverables_schema_json": [
                {
                    "type": definition.type,
                    "label": definition.label,
                    "group": definition.group,
                    "owner_department_slug": definition.owner_department_slug,
                    "visibility": definition.visibility,
                    "requires_approval": definition.requires_approval,
                    "source_kinds": list(definition.source_kinds),
                }
                for definition in list_deliverable_definitions()
            ],
            "metadata_json": {
                "source": ASSEMBLY_SOURCE,
                "source_key": CATALOG_SOURCE_KEY,
            },
            "created_by": user,
        },
    )
    if not created:
        _update_catalog_defaults(catalog, user=user)

    source_key = f"atlas-engagement:{whiteboard.id}"
    engagement, engagement_created = ServiceEngagement.objects.get_or_create(
        company=whiteboard.company,
        source_key=source_key,
        defaults={
            "organization": organization,
            "catalog_item": catalog,
            "status": "in_progress",
            "customer_status": "working",
            "public_summary": _engagement_summary(whiteboard),
            "required_pack_ids_json": [REQUIRED_PACK_ID],
            "intake_data_json": _whiteboard_intake_data(whiteboard),
            "metadata_json": {
                "source": ASSEMBLY_SOURCE,
                "whiteboard_id": str(whiteboard.id),
            },
            "requested_by": user,
        },
    )
    if not engagement_created:
        _update_engagement_defaults(engagement, catalog=catalog, whiteboard=whiteboard)
    return engagement


def assemble_atlas_deliverable(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    deliverable_type: str,
    source_state: dict[str, Any] | None = None,
) -> ServiceDeliverable:
    definition = get_deliverable_definition(deliverable_type)
    if definition is None:
        raise ValueError(f"Unknown Atlas deliverable type: {deliverable_type}")

    engagement = ensure_atlas_service_engagement(whiteboard=whiteboard, user=user)
    sources = _source_state_for_whiteboard(whiteboard, source_state=source_state)
    existing_package_items = _package_items(engagement=engagement, exclude_type=deliverable_type)
    content = _markdown_content(
        whiteboard=whiteboard,
        definition=definition,
        sources=sources,
        package_items=existing_package_items,
    )
    asset = _upsert_asset(whiteboard=whiteboard, definition=definition, user=user)
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri=f"forgegraph://atlas-deliverables/{whiteboard.id}/{definition.type}.md",
        content=content.encode("utf-8"),
        mime_type="text/markdown",
        provenance={
            "source": ASSEMBLY_SOURCE,
            "whiteboard_id": str(whiteboard.id),
            "deliverable_type": definition.type,
            "inline_content": content,
        },
    )
    inline_uri = f"forgegraph://assets/{version.id}/inline"
    if version.content_uri != inline_uri:
        version.content_uri = inline_uri
        version.save(update_fields=["content_uri"])

    blocked_by = _blocked_channel_ids(sources.get("deployment"))
    metadata = {
        "source": ASSEMBLY_SOURCE,
        "whiteboard_id": str(whiteboard.id),
        "deliverable_type": definition.type,
        "owner_department_slug": definition.owner_department_slug,
        "asset_version_id": str(version.id),
        "source_refs": _source_refs(sources),
        "blocked_by": blocked_by,
        "evidence": _evidence_refs(sources),
    }
    deliverable = (
        ServiceDeliverable.objects.filter(
            engagement=engagement,
            deliverable_type=definition.type,
        )
        .order_by("created_at")
        .first()
    )
    if deliverable is None:
        deliverable = ServiceDeliverable.objects.create(
            organization=engagement.organization,
            company=engagement.company,
            engagement=engagement,
            title=definition.label,
            deliverable_type=definition.type,
            status="ready",
            visibility=definition.visibility,
            artifact=asset,
            summary=_deliverable_summary(whiteboard=whiteboard, definition=definition),
            metadata_json=metadata,
            created_by=user,
        )
    else:
        deliverable.title = definition.label
        deliverable.status = "ready"
        deliverable.visibility = definition.visibility
        deliverable.artifact = asset
        deliverable.summary = _deliverable_summary(whiteboard=whiteboard, definition=definition)
        deliverable.metadata_json = metadata
        deliverable.save(
            update_fields=[
                "title",
                "status",
                "visibility",
                "artifact",
                "summary",
                "metadata_json",
                "updated_at",
            ]
        )
    return deliverable


def assemble_atlas_mvp_deliverables(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    source_state: dict[str, Any] | None = None,
) -> list[ServiceDeliverable]:
    sources = _source_state_for_whiteboard(whiteboard, source_state=source_state)
    deliverables: list[ServiceDeliverable] = []
    for deliverable_type in MVP_DELIVERABLE_TYPES:
        deliverables.append(
            assemble_atlas_deliverable(
                whiteboard=whiteboard,
                user=user,
                deliverable_type=deliverable_type,
                source_state=sources,
            )
        )
    return deliverables


def _update_catalog_defaults(catalog: ServiceCatalogItem, *, user: User | None) -> None:
    deliverables_schema = [
        {
            "type": definition.type,
            "label": definition.label,
            "group": definition.group,
            "owner_department_slug": definition.owner_department_slug,
            "visibility": definition.visibility,
            "requires_approval": definition.requires_approval,
            "source_kinds": list(definition.source_kinds),
        }
        for definition in list_deliverable_definitions()
    ]
    metadata = {**(catalog.metadata_json or {}), "source": ASSEMBLY_SOURCE, "source_key": CATALOG_SOURCE_KEY}
    changed = False
    for attr, value in {
        "title": "Digital Marketing Agency Engagement",
        "description": "Customer-facing Atlas digital marketing delivery package.",
        "status": "active",
        "visibility": "customer",
        "audience": "digital_marketing_client",
        "required_pack_ids_json": [REQUIRED_PACK_ID],
        "deliverables_schema_json": deliverables_schema,
        "metadata_json": metadata,
    }.items():
        if getattr(catalog, attr) != value:
            setattr(catalog, attr, value)
            changed = True
    if catalog.created_by_id is None and user is not None:
        catalog.created_by = user
        changed = True
    if changed:
        catalog.save(update_fields=[
            "title",
            "description",
            "status",
            "visibility",
            "audience",
            "required_pack_ids_json",
            "deliverables_schema_json",
            "metadata_json",
            "created_by",
            "updated_at",
        ])


def _update_engagement_defaults(
    engagement: ServiceEngagement,
    *,
    catalog: ServiceCatalogItem,
    whiteboard: WorkWhiteboard,
) -> None:
    engagement.catalog_item = catalog
    engagement.status = "in_progress" if engagement.status == "requested" else engagement.status
    engagement.customer_status = (
        "working" if engagement.customer_status == "requested" else engagement.customer_status
    )
    engagement.public_summary = _engagement_summary(whiteboard)
    engagement.required_pack_ids_json = [REQUIRED_PACK_ID]
    engagement.intake_data_json = _whiteboard_intake_data(whiteboard)
    engagement.metadata_json = {
        **(engagement.metadata_json or {}),
        "source": ASSEMBLY_SOURCE,
        "whiteboard_id": str(whiteboard.id),
    }
    engagement.save(
        update_fields=[
            "catalog_item",
            "status",
            "customer_status",
            "public_summary",
            "required_pack_ids_json",
            "intake_data_json",
            "metadata_json",
            "updated_at",
        ]
    )


def _upsert_asset(
    *,
    whiteboard: WorkWhiteboard,
    definition: DeliverableDefinition,
    user: User | None,
) -> Asset:
    metadata = {
        "source": ASSEMBLY_SOURCE,
        "whiteboard_id": str(whiteboard.id),
        "deliverable_type": definition.type,
        "owner_department_slug": definition.owner_department_slug,
        "visibility": definition.visibility,
    }
    asset = ArchiveService().create_asset(
        company=whiteboard.company,
        title=definition.label,
        asset_type="deliverable",
        source_key=f"atlas-deliverable:{whiteboard.id}:{definition.type}",
        created_by_type="user" if user is not None else "system",
        created_by_id=user.id if user is not None else None,
        metadata=metadata,
    )
    updates: list[str] = []
    if asset.title != definition.label:
        asset.title = definition.label
        updates.append("title")
    if asset.metadata_json != metadata:
        asset.metadata_json = metadata
        updates.append("metadata_json")
    if asset.status != "active":
        asset.status = "active"
        updates.append("status")
    if updates:
        asset.save(update_fields=updates + ["updated_at"])
    return asset


def _source_state_for_whiteboard(
    whiteboard: WorkWhiteboard,
    *,
    source_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if source_state is not None:
        if "deployment" in source_state or "performance" in source_state:
            return {
                "deployment": dict(source_state.get("deployment") or {}),
                "performance": dict(source_state.get("performance") or {}),
            }
        if "channels" in source_state:
            return {"deployment": dict(source_state), "performance": {}}
        if any(key in source_state for key in ("metric_snapshot_id", "report_run_id", "evaluation_id")):
            return {"deployment": {}, "performance": dict(source_state)}
        return {"deployment": {}, "performance": {}}
    return {
        "deployment": _projection_state(whiteboard, f"whiteboard_deployment:{whiteboard.id}"),
        "performance": _projection_state(whiteboard, f"whiteboard_performance:{whiteboard.id}"),
    }


def _projection_state(whiteboard: WorkWhiteboard, projection_type: str) -> dict[str, Any]:
    projection = StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=projection_type,
    ).first()
    if projection is None or not isinstance(projection.json_state, dict):
        return {}
    state = dict(projection.json_state)
    state["_projection_id"] = str(projection.id)
    state["_projection_type"] = projection.projection_type
    state["_source_refs"] = list(projection.source_refs_json or [])
    return state


def _markdown_content(
    *,
    whiteboard: WorkWhiteboard,
    definition: DeliverableDefinition,
    sources: dict[str, Any],
    package_items: list[dict[str, str]],
) -> str:
    lines = [
        f"# {definition.label}",
        "",
        "## Client Summary",
        _client_summary(whiteboard),
        "",
        "## Source Evidence",
    ]
    lines.extend(_source_evidence_lines(definition=definition, sources=sources, package_items=package_items))
    lines.extend(
        [
            "",
            "## Status",
            _status_line(definition=definition, sources=sources),
            "",
        ]
    )
    return "\n".join(lines)


def _source_evidence_lines(
    *,
    definition: DeliverableDefinition,
    sources: dict[str, Any],
    package_items: list[dict[str, str]],
) -> list[str]:
    if definition.type == "campaign_launch_package":
        if not package_items:
            return ["- No assembled deliverables are linked yet."]
        return [
            f"- {item['label']} (`{item['type']}`): {item['status']}"
            for item in package_items
        ]

    lines = [f"- Source kinds: {', '.join(definition.source_kinds)}."]
    deployment = sources.get("deployment") if isinstance(sources.get("deployment"), dict) else {}
    performance = sources.get("performance") if isinstance(sources.get("performance"), dict) else {}
    if definition.type in {"connector_gap_report", "execution_receipt"}:
        lines.extend(_deployment_lines(deployment))
    if definition.type == "performance_report":
        lines.extend(_performance_lines(performance))
    if definition.type == "measurement_plan":
        lines.extend(_performance_lines(performance))
    return lines


def _deployment_lines(deployment: dict[str, Any]) -> list[str]:
    channels = _channels(deployment)
    if not channels:
        return ["- Deployment state: not available."]
    lines = [f"- Deployment status: {deployment.get('status') or 'unknown'}."]
    for channel in channels:
        label = str(channel.get("label") or channel.get("id") or "channel")
        status = str(channel.get("status") or "unknown")
        reason = str(channel.get("blocked_reason_code") or channel.get("blocked_reason") or "")
        receipt = channel.get("receipt") if isinstance(channel.get("receipt"), dict) else {}
        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        result_status = str(result.get("status") or "")
        detail = f"- {label}: {status}"
        if reason:
            detail = f"{detail} ({reason})"
        if result_status:
            detail = f"{detail}; receipt {result_status}"
        lines.append(detail)
    return lines


def _performance_lines(performance: dict[str, Any]) -> list[str]:
    if not performance:
        return ["- Performance state: not available."]
    lines = [f"- Performance status: {performance.get('status') or 'unknown'}."]
    for key in ("metric_snapshot_id", "report_run_id", "evaluation_id"):
        value = str(performance.get(key) or "")
        if value:
            lines.append(f"- {key}: {value}")
    return lines


def _status_line(*, definition: DeliverableDefinition, sources: dict[str, Any]) -> str:
    if definition.type == "connector_gap_report" and _blocked_channel_ids(sources.get("deployment")):
        return "Ready with connector gaps identified."
    return "Ready for customer review."


def _source_refs(sources: dict[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    deployment = sources.get("deployment")
    if isinstance(deployment, dict) and deployment:
        refs["deployment"] = _compact_state_ref(
            deployment,
            keys=("status", "_projection_id", "_projection_type", "channels"),
        )
    performance = sources.get("performance")
    if isinstance(performance, dict) and performance:
        refs["performance"] = _compact_state_ref(
            performance,
            keys=(
                "status",
                "_projection_id",
                "_projection_type",
                "metric_snapshot_id",
                "report_run_id",
                "evaluation_id",
            ),
        )
    return refs


def _compact_state_ref(state: dict[str, Any], *, keys: tuple[str, ...]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in keys:
        if key not in state:
            continue
        value = state[key]
        if key == "channels":
            compact[key] = [
                {
                    "id": channel.get("id"),
                    "label": channel.get("label"),
                    "status": channel.get("status"),
                    "blocked_reason_code": channel.get("blocked_reason_code"),
                }
                for channel in _channels(state)
            ]
            continue
        compact[key.lstrip("_")] = value
    source_refs = state.get("_source_refs")
    if source_refs:
        compact["source_refs"] = source_refs
    return compact


def _evidence_refs(sources: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    deployment = sources.get("deployment")
    if isinstance(deployment, dict):
        for channel in _channels(deployment):
            receipt = channel.get("receipt") if isinstance(channel.get("receipt"), dict) else {}
            if receipt:
                evidence.append(
                    {
                        "kind": "deployment_receipt",
                        "channel_id": str(channel.get("id") or ""),
                        "status": str(channel.get("status") or ""),
                    }
                )
    performance = sources.get("performance")
    if isinstance(performance, dict):
        for key in ("metric_snapshot_id", "report_run_id", "evaluation_id"):
            value = str(performance.get(key) or "")
            if value:
                evidence.append({"kind": key, "id": value})
    return evidence


def _channels(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    channels = deployment.get("channels")
    if isinstance(channels, list):
        return [channel for channel in channels if isinstance(channel, dict)]
    policy = deployment.get("policy") if isinstance(deployment.get("policy"), dict) else {}
    policy_channels = policy.get("channels")
    if isinstance(policy_channels, list):
        return [channel for channel in policy_channels if isinstance(channel, dict)]
    return []


def _blocked_channel_ids(deployment: Any) -> list[str]:
    if not isinstance(deployment, dict):
        return []
    blocked: list[str] = []
    for channel in _channels(deployment):
        if str(channel.get("status") or "") == "blocked":
            blocked.append(str(channel.get("id") or channel.get("label") or "channel"))
    return blocked


def _package_items(
    *,
    engagement: ServiceEngagement,
    exclude_type: str,
) -> list[dict[str, str]]:
    deliverables = (
        ServiceDeliverable.objects.filter(engagement=engagement)
        .exclude(deliverable_type=exclude_type)
        .order_by("created_at")
    )
    return [
        {
            "type": deliverable.deliverable_type,
            "label": deliverable.title,
            "status": deliverable.status,
        }
        for deliverable in deliverables
    ]


def _engagement_summary(whiteboard: WorkWhiteboard) -> str:
    values = [
        whiteboard.project_name,
        whiteboard.request_summary,
        whiteboard.objective,
    ]
    summary = " ".join(value.strip() for value in values if value and value.strip())
    return summary[:1000]


def _whiteboard_intake_data(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    return {
        "whiteboard_id": str(whiteboard.id),
        "request_type": whiteboard.request_type,
        "project_name": whiteboard.project_name,
        "client_name": whiteboard.client_name,
        "request_summary": whiteboard.request_summary,
        "objective": whiteboard.objective,
        "budget_limit": whiteboard.budget_limit,
        "timeline": whiteboard.timeline,
    }


def _client_summary(whiteboard: WorkWhiteboard) -> str:
    values = {
        "Client": whiteboard.client_name or whiteboard.company.name,
        "Project": whiteboard.project_name or "Atlas campaign",
        "Request": whiteboard.request_summary or "No request summary recorded.",
        "Objective": whiteboard.objective or "No objective recorded.",
    }
    return "\n".join(f"- {label}: {value}" for label, value in values.items())


def _deliverable_summary(
    *,
    whiteboard: WorkWhiteboard,
    definition: DeliverableDefinition,
) -> str:
    objective = whiteboard.objective.strip() if whiteboard.objective else "campaign delivery"
    return f"{definition.label} assembled from Atlas whiteboard state for {objective}."[:500]
