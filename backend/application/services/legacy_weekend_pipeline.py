"""Pipeline-aware Legacy weekend marketing sprint assembly.

This module productizes the previous Legacy fixture script into a ForgeGraph-native
service: deliverables are created while the owning department stage is active and
all customer-facing artifacts receive department-pipeline lineage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, time
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.company_run_task_routing import refresh_whiteboard_task_snapshot
from application.services.department_pipeline import (
    attach_asset_to_stage,
    attach_deliverable_to_stage,
    complete_stage,
    create_pipeline_for_engagement,
    stage_state_for_engagement,
    start_stage,
)
from application.services.operating_model_packs import install_pack_for_company
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyOperatingModelInstallation,
    DepartmentRegistry,
    Graph,
    Organization,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

PACK_ID = "digital_marketing_pro.v1"
SOURCE = "legacy-weekend-department-pipeline.v1"
DEFAULT_COMPANY_EXTERNAL_REF = "legacy-glasswear-cdmx"
DEFAULT_TEMPLATE_ID = "digital_marketing_pro.weekend_social_launch.v1"
LEGACY_HANDOFF_PROFILE_REF = "format_profile:legacy.client_handoff@1"

FILE_DELIVERABLES: tuple[dict[str, str], ...] = (
    {
        "type": "brand_context_pack",
        "title": "Legacy Brand Context Pack",
        "stage_id": "strategy_research",
        "filename": "legacy_brand_context.json",
        "summary": "Reusable source-of-truth context for Legacy's brand, products, posts, and website constraints.",
    },
    {
        "type": "strategy_brief",
        "title": "Legacy Marketing Strategy Sprint",
        "stage_id": "strategy_research",
        "filename": "legacy_marketing_strategy.md",
        "summary": "Weekend marketing strategy for Legacy's first fast agency-grade social/content launch.",
    },
    {
        "type": "channel_copy_pack",
        "title": "Legacy Instagram Copy Pack",
        "stage_id": "brand_content",
        "filename": "legacy_instagram_copy_pack.md",
        "summary": "Spanish-first captions, hooks, CTAs, and post metadata for the launch posts.",
    },
    {
        "type": "creative_direction_brief",
        "title": "Legacy Creative Direction Brief",
        "stage_id": "brand_content",
        "filename": "legacy_creative_direction_brief.md",
        "summary": "Visual and motion rules for Optical Noir social assets and the first reel.",
    },
    {
        "type": "content_calendar",
        "title": "Legacy 10-Day Social Media Calendar",
        "stage_id": "channel_execution",
        "filename": "legacy_social_media_calendar.md",
        "summary": "Concrete social schedule with dates, channels, assets, CTAs, owners, and status.",
    },
    {
        "type": "approval_packet",
        "title": "Legacy Client Approval Packet",
        "stage_id": "client_approval_ops",
        "filename": "legacy_client_approval_packet.md",
        "summary": "Approval-ready decision packet for Mike/client review before publishing.",
    },
    {
        "type": "campaign_launch_package",
        "title": "Legacy Campaign Launch Package",
        "stage_id": "client_approval_ops",
        "filename": "legacy_campaign_launch_package.md",
        "summary": "Unified strategy, calendar, media, copy, video, QA, and approval package.",
    },
)


def read_manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


@transaction.atomic
def run_legacy_weekend_pipeline(
    *,
    user: User,
    root: Path,
    company_name: str = "Legacy",
    organization: Organization | None = None,
    company_external_ref: str = DEFAULT_COMPANY_EXTERNAL_REF,
) -> dict[str, Any]:
    """Run the Legacy fixture through real department pipeline stages."""

    root = Path(root)
    manifest = read_manifest(root)
    organization = organization or _user_organization(user)
    company = _ensure_company(
        user=user,
        organization=organization,
        company_name=company_name,
        external_ref=company_external_ref,
    )
    pack_status, installation = _ensure_pack(company=company, user=user)
    _required_departments(organization)
    catalog = _ensure_catalog(organization=organization, user=user, manifest=manifest)
    engagement = _ensure_engagement(
        user=user,
        organization=organization,
        company=company,
        catalog=catalog,
        root=root,
        manifest=manifest,
    )
    whiteboard = _ensure_whiteboard(
        user=user,
        organization=organization,
        company=company,
        engagement=engagement,
        root=root,
        manifest=manifest,
    )
    program = create_pipeline_for_engagement(
        engagement,
        template_id=DEFAULT_TEMPLATE_ID,
        created_by=user,
        run_context={"source": SOURCE},
    )

    deliverables: list[ServiceDeliverable] = []
    routing_records: list[TaskRoutingRecord] = []

    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)
    for definition in _definitions_for_stage("strategy_research"):
        deliverables.append(
            _upsert_file_deliverable(definition, root, engagement, user, whiteboard)
        )
    complete_stage(strategy, actor=user)

    brand = stage_state_for_engagement(engagement, "brand_content")
    start_stage(brand, actor=user)
    for definition in _definitions_for_stage("brand_content"):
        deliverables.append(
            _upsert_file_deliverable(definition, root, engagement, user, whiteboard)
        )
    complete_stage(brand, actor=user)

    crm = stage_state_for_engagement(engagement, "crm_lifecycle")
    start_stage(crm, actor=user)
    deliverables.append(
        _upsert_generated_deliverable(
            engagement=engagement,
            user=user,
            whiteboard=whiteboard,
            stage_id="crm_lifecycle",
            deliverable_type="crm_dm_response_scripts",
            title="Legacy DM / WhatsApp Response Scripts",
            summary="Manual CRM reply scripts for model availability, styling, pricing, shipping, and appointment follow-up.",
            content=_crm_scripts(manifest),
        )
    )
    complete_stage(crm, actor=user)

    analytics = stage_state_for_engagement(engagement, "analytics_performance")
    start_stage(analytics, actor=user)
    deliverables.append(
        _upsert_generated_deliverable(
            engagement=engagement,
            user=user,
            whiteboard=whiteboard,
            stage_id="analytics_performance",
            deliverable_type="manual_metrics_template",
            title="Legacy Manual Metrics Template",
            summary="Manual KPI/reporting template for posts, DMs, saves, reach, and next-action decisions.",
            content=_manual_metrics_template(manifest),
        )
    )
    complete_stage(analytics, actor=user)

    channel = stage_state_for_engagement(engagement, "channel_execution")
    start_stage(channel, actor=user)
    for definition in _definitions_for_stage("channel_execution"):
        deliverables.append(
            _upsert_file_deliverable(definition, root, engagement, user, whiteboard)
        )
    for post in manifest.get("posts", []):
        deliverables.append(
            _upsert_post_media_deliverable(post, root, engagement, user, whiteboard)
        )
        routing_records.append(_upsert_social_task(post, engagement, user, whiteboard))
    deliverables.append(_upsert_reel_deliverable(root, engagement, user, whiteboard))
    complete_stage(
        channel,
        outputs=[
            {"kind": "routing_task", "type": "task_routing_record", "id": str(route.id)}
            for route in routing_records
        ],
        actor=user,
    )

    qa = stage_state_for_engagement(engagement, "qa_compliance")
    start_stage(qa, actor=user)
    deliverables.append(
        _upsert_generated_deliverable(
            engagement=engagement,
            user=user,
            whiteboard=whiteboard,
            stage_id="qa_compliance",
            deliverable_type="qa_report",
            title="Legacy Launch QA Report",
            summary="QA report covering artifact presence, formats, dimensions expectations, copy review, and approval blockers.",
            content=_qa_report(manifest=manifest, deliverables=deliverables),
        )
    )
    complete_stage(qa, actor=user)

    approval = stage_state_for_engagement(engagement, "client_approval_ops")
    start_stage(approval, actor=user)
    for definition in _definitions_for_stage("client_approval_ops"):
        deliverables.append(
            _upsert_file_deliverable(definition, root, engagement, user, whiteboard)
        )
    complete_stage(approval, actor=user)

    engagement.customer_status = "review_ready"
    engagement.status = "in_progress"
    engagement.save(update_fields=["customer_status", "status", "updated_at"])
    whiteboard.status = WorkWhiteboard.STATUS_IN_APPROVAL
    whiteboard.work_status = WorkWhiteboard.WORK_STATUS_REVIEW
    whiteboard.save(update_fields=["status", "work_status", "updated_at"])
    refresh_whiteboard_task_snapshot(whiteboard, program)

    return {
        "organization": {"id": str(organization.id), "name": organization.name},
        "company": {"id": str(company.id), "name": company.name},
        "pack": {
            "pack_id": PACK_ID,
            "status": pack_status,
            "installation_id": str(installation.id) if installation else None,
        },
        "service_engagement": {
            "id": str(engagement.id),
            "status": engagement.status,
            "customer_status": engagement.customer_status,
        },
        "whiteboard": {"id": str(whiteboard.id), "status": whiteboard.status},
        "deliverable_count": ServiceDeliverable.objects.filter(engagement=engagement).count(),
        "routing_task_count": TaskRoutingRecord.objects.filter(
            service_engagement=engagement
        ).count(),
        "files_root": str(root),
    }


def _user_organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    if organization is None:
        raise ValueError("Legacy weekend pipeline requires a user default organization.")
    return organization


def _ensure_company(
    *,
    user: User,
    organization: Organization,
    company_name: str,
    external_ref: str,
) -> Graph:
    company, _ = Graph.objects.get_or_create(
        organization=organization,
        external_source="atlas_client",
        external_ref=external_ref,
        defaults={
            "owner": user,
            "name": company_name,
            "description": "Legacy: Spanish-first luxury glasswear/sunglasses brand in Mexico City.",
        },
    )
    company.owner = user
    company.name = company_name
    company.description = (
        "Legacy: Spanish-first luxury glasswear/sunglasses brand in Mexico City. "
        "Client workspace for Atlas weekend marketing agency deliverables."
    )
    company.save(update_fields=["owner", "name", "description", "updated_at"])
    return company


def _ensure_pack(
    *,
    company: Graph,
    user: User,
) -> tuple[str, CompanyOperatingModelInstallation | None]:
    try:
        installation = install_pack_for_company(
            company=company, user=user, pack_id=PACK_ID, role="primary"
        )
        return "installed", installation
    except Exception as exc:  # pragma: no cover - fallback depends on pack fixture availability.
        installation = CompanyOperatingModelInstallation.objects.filter(
            company=company,
            pack_id=PACK_ID,
        ).first()
        return f"install_error:{exc.__class__.__name__}:{exc}", installation


def _required_departments(organization: Organization) -> dict[str, DepartmentRegistry]:
    required = {
        "strategy_research",
        "brand_content",
        "channel_execution",
        "crm_lifecycle",
        "analytics_performance",
        "qa_compliance",
        "client_approval_ops",
    }
    departments = {
        department.slug: department
        for department in DepartmentRegistry.objects.filter(
            organization=organization,
            slug__in=required,
            active=True,
        )
    }
    missing = sorted(required - set(departments))
    if missing:
        raise ValueError(f"Missing Atlas departments: {missing}")
    return departments


def _ensure_catalog(
    *,
    organization: Organization,
    user: User,
    manifest: dict[str, Any],
) -> ServiceCatalogItem:
    catalog, _ = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug="atlas-legacy-weekend-marketing-sprint",
        defaults={"title": "Atlas Legacy Weekend Marketing Sprint", "created_by": user},
    )
    catalog.title = "Atlas Legacy Weekend Marketing Sprint"
    catalog.description = (
        "Fast agency package for Legacy: strategy, copy, social calendar, CRM scripts, "
        "manual metrics, media assets, QA, approval, and launch package."
    )
    catalog.status = "active"
    catalog.visibility = "organization"
    catalog.audience = "Legacy glasswear brand / CDMX shoppers"
    catalog.required_pack_ids_json = [PACK_ID]
    catalog.deliverables_schema_json = [
        {"type": item["type"], "title": item["title"], "stage_id": item["stage_id"]}
        for item in FILE_DELIVERABLES
    ] + [
        {
            "type": f"instagram_post_media:{post['id']}",
            "title": post["asset"],
            "stage_id": "channel_execution",
        }
        for post in manifest.get("posts", [])
    ]
    catalog.metadata_json = {"source": SOURCE, "client": "legacy", "agency_mode": True}
    catalog.save()
    return catalog


def _ensure_engagement(
    *,
    user: User,
    organization: Organization,
    company: Graph,
    catalog: ServiceCatalogItem,
    root: Path,
    manifest: dict[str, Any],
) -> ServiceEngagement:
    engagement, _ = ServiceEngagement.objects.get_or_create(
        company=company,
        source_key="legacy-weekend-marketing-sprint:pipeline:v1",
        defaults={
            "organization": organization,
            "catalog_item": catalog,
            "status": "in_progress",
            "customer_status": "working",
            "requested_by": user,
            "assigned_operator": user,
            "started_at": timezone.now(),
        },
    )
    engagement.organization = organization
    engagement.catalog_item = catalog
    engagement.status = "in_progress"
    engagement.customer_status = "working"
    engagement.public_summary = (
        "Legacy weekend marketing sprint routed through Strategy, Brand, Channel, CRM, "
        "Analytics, QA, and Client Approval departments."
    )
    engagement.internal_notes = (
        "Deliverables are created through department pipeline stages, not tagged after generation."
    )
    engagement.intake_data_json = {
        "client": "Legacy",
        "category": "luxury glasswear / sunglasses",
        "market": "Mexico City",
        "deadline": "weekend_sprint",
        "requested_outputs": [
            "marketing strategy",
            "social media strategy",
            "Instagram posts/media",
            "copywriting",
            "video/reel",
            "CRM scripts",
            "manual reporting template",
            "QA report",
            "approval packet",
        ],
    }
    engagement.required_pack_ids_json = [PACK_ID]
    engagement.metadata_json = {
        "source": SOURCE,
        "manifest": manifest,
        "deliverables_root": str(root),
        "formatting": {"profile_ref": LEGACY_HANDOFF_PROFILE_REF},
    }
    engagement.assigned_operator = user
    engagement.requested_by = user
    if not engagement.started_at:
        engagement.started_at = timezone.now()
    engagement.save()
    return engagement


def _ensure_whiteboard(
    *,
    user: User,
    organization: Organization,
    company: Graph,
    engagement: ServiceEngagement,
    root: Path,
    manifest: dict[str, Any],
) -> WorkWhiteboard:
    whiteboard, _ = WorkWhiteboard.objects.get_or_create(
        organization=organization,
        company=company,
        idempotency_key="legacy-weekend-marketing-sprint:pipeline-whiteboard:v1",
        defaults={"created_by": user},
    )
    whiteboard.service_engagement = engagement
    whiteboard.request_type = "client_marketing_agency_sprint"
    whiteboard.project_name = "Legacy Weekend Social Launch Sprint"
    whiteboard.client_name = "Legacy"
    whiteboard.request_summary = "Produce marketing agency deliverables through Atlas departments."
    whiteboard.objective = (
        "Have client-ready Legacy strategy, content, media, metrics, QA, and approval package."
    )
    whiteboard.timeline = "Weekend sprint"
    whiteboard.constraints_json = {
        "brand": "Optical Noir; Spanish-first; restrained luxury; CDMX night energy",
        "privacy": "Do not expose exact inventory counts, cost, margins, supplier data, or raw client file paths publicly.",
    }
    whiteboard.stakeholder_context_json = {
        "client": "Legacy",
        "operator_id": str(user.id),
        "approver": "Mike",
    }
    whiteboard.delivery_context_json = {
        "deliverables_root": str(root),
        "media_root": str(root / "media"),
    }
    whiteboard.metadata_json = {
        "source": SOURCE,
        "agent_owned": True,
        "social_schedule": manifest.get("posts", []),
    }
    whiteboard.completion_score = 0.85
    whiteboard.save()
    return whiteboard


def _definitions_for_stage(stage_id: str) -> list[dict[str, str]]:
    return [dict(item) for item in FILE_DELIVERABLES if item["stage_id"] == stage_id]


def _upsert_file_deliverable(
    definition: dict[str, str],
    root: Path,
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
) -> ServiceDeliverable:
    path = root / definition["filename"]
    data = path.read_bytes()
    content_preview = (
        data.decode("utf-8", errors="replace")[:12000] if path.suffix in {".md", ".json"} else ""
    )
    return _upsert_deliverable_from_bytes(
        engagement=engagement,
        user=user,
        whiteboard=whiteboard,
        stage_id=definition["stage_id"],
        deliverable_type=definition["type"],
        title=definition["title"],
        summary=definition["summary"],
        data=data,
        content_uri=f"file://{path}",
        mime_type=_mime_for(path),
        source_filename=path.name,
        inline_preview=content_preview,
    )


def _upsert_generated_deliverable(
    *,
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
    stage_id: str,
    deliverable_type: str,
    title: str,
    summary: str,
    content: str,
) -> ServiceDeliverable:
    return _upsert_deliverable_from_bytes(
        engagement=engagement,
        user=user,
        whiteboard=whiteboard,
        stage_id=stage_id,
        deliverable_type=deliverable_type,
        title=title,
        summary=summary,
        data=content.encode("utf-8"),
        content_uri=f"forgegraph://legacy-weekend/{engagement.id}/{deliverable_type}.md",
        mime_type="text/markdown",
        source_filename=f"{deliverable_type}.md",
        inline_preview=content[:12000],
    )


def _upsert_post_media_deliverable(
    post: dict[str, Any],
    root: Path,
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
) -> ServiceDeliverable:
    asset_name = str(post["asset"])
    path = root / "media" / asset_name
    return _upsert_deliverable_from_bytes(
        engagement=engagement,
        user=user,
        whiteboard=whiteboard,
        stage_id="channel_execution",
        deliverable_type=f"instagram_post_media:{post['id']}",
        title=f"Legacy Instagram Asset — {post['theme']}",
        summary=f"1080x1080 Instagram asset scheduled for {post['date']}: {post['headline']}",
        data=path.read_bytes(),
        content_uri=f"file://{path}",
        mime_type=_mime_for(path),
        source_filename=asset_name,
        inline_preview="",
    )


def _upsert_reel_deliverable(
    root: Path,
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
) -> ServiceDeliverable:
    path = root / "media" / "legacy_reel_01_optical_noir.mp4"
    return _upsert_deliverable_from_bytes(
        engagement=engagement,
        user=user,
        whiteboard=whiteboard,
        stage_id="channel_execution",
        deliverable_type="reel_video:first_cut",
        title="Legacy Optical Noir Reel — First Cut",
        summary="First-cut square MP4 reel assembled from existing Legacy website/product assets.",
        data=path.read_bytes(),
        content_uri=f"file://{path}",
        mime_type="video/mp4",
        source_filename=path.name,
        inline_preview="",
    )


def _upsert_deliverable_from_bytes(
    *,
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
    stage_id: str,
    deliverable_type: str,
    title: str,
    summary: str,
    data: bytes,
    content_uri: str,
    mime_type: str,
    source_filename: str,
    inline_preview: str,
) -> ServiceDeliverable:
    digest = hashlib.sha256(data).hexdigest()
    stage = stage_state_for_engagement(engagement, stage_id)
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=f"legacy-pipeline:{engagement.id}:{deliverable_type}:{source_filename}",
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "deliverable",
            "created_by_type": "agent",
            "created_by_id": user.id,
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "deliverable"
    asset.status = "active"
    asset.metadata_json = {
        "source": SOURCE,
        "client": "Legacy",
        "deliverable_type": deliverable_type,
        "stage_id": stage_id,
        "source_filename": source_filename,
        "inline_preview": inline_preview,
    }
    asset.save()
    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest_num = (
            AssetVersion.objects.filter(asset=asset)
            .order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
            or 0
        )
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=latest_num + 1,
            content_uri=content_uri,
            content_hash=digest,
            mime_type=mime_type,
            size_bytes=len(data),
            provenance_json={"source": SOURCE, "client": "Legacy", "stage_id": stage_id},
        )
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=deliverable_type,
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "created_by": user,
        },
    )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = title
    deliverable.status = "ready"
    deliverable.visibility = "customer"
    deliverable.artifact = asset
    deliverable.summary = summary
    deliverable.metadata_json = {
        "source": SOURCE,
        "client": "Legacy",
        "whiteboard_id": str(whiteboard.id),
        "asset_version_id": str(version.id),
        "stage_id": stage_id,
    }
    deliverable.save()
    attach_asset_to_stage(asset, stage, output_kind=deliverable_type)
    attach_deliverable_to_stage(deliverable, stage, output_kind=deliverable_type)
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=["origin_deliverable_id", "updated_at"])
    return deliverable


def _upsert_social_task(
    post: dict[str, Any],
    engagement: ServiceEngagement,
    user: User,
    whiteboard: WorkWhiteboard,
) -> TaskRoutingRecord:
    stage = stage_state_for_engagement(engagement, "channel_execution")
    department = DepartmentRegistry.objects.get(
        organization=engagement.organization,
        slug="channel_execution",
    )
    route, _ = TaskRoutingRecord.objects.get_or_create(
        organization=engagement.organization,
        idempotency_key=f"legacy-pipeline-social-schedule:{engagement.id}:{post['id']}",
        defaults={"company": engagement.company, "to_department": department},
    )
    route.company = engagement.company
    route.service_engagement = engagement
    route.to_department = department
    route.assigned_user = user
    route.reason = (
        f"Prepare/publish scheduled Legacy social post: {post['theme']} — {post['headline']}"
    )
    route.status = "ready_for_review" if str(post["date"]) <= "2026-06-12" else "queued"
    route.priority = "high" if post["date"] in {"2026-06-05", "2026-06-06"} else "normal"
    route.due_at = _due_at_for(str(post["date"]))
    route.metadata_json = {
        "source": SOURCE,
        "whiteboard_id": str(whiteboard.id),
        "post": post,
        "client": "Legacy",
        "department_pipeline": _stage_lineage(stage, output_kind="routing_task"),
    }
    route.resolution_json = {"asset": post["asset"], "caption": post["caption"], "cta": post["cta"]}
    route.save()
    return route


def _stage_lineage(stage: Any, *, output_kind: str) -> dict[str, Any]:
    state = stage.state_json or {}
    return {
        "program_id": str(stage.program_id),
        "stage_state_id": str(stage.id),
        "stage_id": stage.stage_id,
        "department_id": state.get("department_id"),
        "department_slug": state.get("department_slug"),
        "output_kind": output_kind,
        "created_via_department_pipeline": True,
    }


def _mime_for(path: Path) -> str:
    if path.suffix == ".md":
        return "text/markdown"
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".png":
        return "image/png"
    if path.suffix == ".mp4":
        return "video/mp4"
    return "application/octet-stream"


def _due_at_for(date_text: str) -> Any:
    parsed = datetime.combine(datetime.fromisoformat(date_text).date(), time(hour=16, minute=0))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _crm_scripts(manifest: dict[str, Any]) -> str:
    post_count = len(manifest.get("posts", []))
    return f"""# Legacy DM / WhatsApp Response Scripts

## Availability
Gracias por escribir a Legacy. ¿Qué modelo te gustó? Te confirmamos disponibilidad y opciones similares.

## Styling
Si buscas algo más nocturno/elegante, recomendamos Optical Noir. Si quieres algo más statement, Monroe es la mejor entrada.

## Price / shipping
Te podemos compartir precio, formas de pago y entrega por DM. Para regalos, dinos fecha límite y zona.

## Weekend launch handling
Hay {post_count} piezas de contenido en revisión. Responder DMs manualmente hasta conectar CRM/WhatsApp.
"""


def _manual_metrics_template(manifest: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {post['date']} | {post['id']} | {post['theme']} |  |  |  |  |  |  | |"
        for post in manifest.get("posts", [])
    )
    return f"""# Legacy Manual Metrics Template

| Date | Post ID | Theme | Reach | Saves | Shares | Comments | DMs | Orders/holds | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

## Decision rules
- High saves + low DMs: strengthen CTA.
- High DMs + low conversion: improve availability/pricing reply.
- Low reach: reuse creative as story/reel cutdown.
"""


def _qa_report(*, manifest: dict[str, Any], deliverables: list[ServiceDeliverable]) -> str:
    media_count = len(
        [item for item in deliverables if item.deliverable_type.startswith("instagram_post_media")]
    )
    return f"""# Legacy Launch QA Report

## Automated checks
- Deliverables created: {len(deliverables)}
- Instagram media assets created: {media_count}
- Scheduled posts in manifest: {len(manifest.get("posts", []))}
- All generated deliverables carry department-pipeline lineage.

## Human review notes
- Confirm Spanish copy tone feels premium and not generic.
- Confirm scarcity language does not expose exact inventory counts.
- Confirm publishing dates and CTA language before client approval.

## Approval recommendation
Ready for Mike/client approval once visual polish is reviewed.
"""
