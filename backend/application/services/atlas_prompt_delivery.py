from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import requests
from django.conf import settings
from django.utils import timezone

from application.services.codex_media_worker import CodexMediaWorker, enqueue_codex_image_job
from application.services.codex_session_runtime import build_codex_deliverable_for_stage
from application.services.company_archive import ArchiveService
from application.services.company_run_task_routing import refresh_whiteboard_task_snapshot
from application.services.deliverable_format_renderers import _pdf_document_bytes, _pdf_pages
from application.services.department_pipeline import (
    attach_asset_to_stage,
    attach_deliverable_to_stage,
    complete_stage,
    create_pipeline_for_engagement,
    stage_state_for_engagement,
    start_stage,
)
from application.services.gemini_media import read_media_asset_version_content
from application.services.legacy_weekend_pipeline import (
    DEFAULT_COMPANY_EXTERNAL_REF,
    DEFAULT_TEMPLATE_ID,
    PACK_ID,
    _ensure_catalog,
    _ensure_company,
    _ensure_engagement,
    _ensure_pack,
    _ensure_whiteboard,
    _user_organization,
)
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CommunicationAttachment,
    CommunicationEventReceipt,
    CommunicationMessage,
    CommunicationThread,
    DepartmentRegistry,
    ServiceDeliverable,
    User,
    WorkWhiteboard,
)

SOURCE = "atlas_prompt_delivery.codex_media.v1"
DEPARTMENTS = {
    "strategy_research": "Strategy & Research",
    "brand_content": "Brand & Content",
    "channel_execution": "Channel Execution",
    "crm_lifecycle": "CRM & Lifecycle",
    "analytics_performance": "Analytics & Performance",
    "qa_compliance": "QA & Compliance",
    "client_approval_ops": "Client Approval Ops",
}


@dataclass(frozen=True)
class AtlasPromptDeliveryResult:
    engagement_id: UUID
    whiteboard_id: UUID
    package_path: str
    package_sha256: str
    text_message_id: str
    media_message_id: str
    receipt_id: UUID | None
    media_job_ids: list[str]


def run_atlas_prompt_delivery(
    *,
    user: User,
    prompt: str,
    phone_e164: str,
    send: bool = True,
    whatsapp_bridge_url: str = "http://127.0.0.1:3008",
) -> AtlasPromptDeliveryResult:
    """Run an Atlas/Legacy delivery from one prompt inside ForgeGraph."""

    started = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_id = f"atlas_prompt_codex_media_{started}"
    artifacts_root = Path(
        getattr(settings, "ATLAS_PROMPT_DELIVERY_ARTIFACTS_ROOT", "")
        or Path(settings.BASE_DIR) / ".hermes" / "forgegraph_atlas_prompt_runs"
    )
    root = artifacts_root / run_id
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "client": "Legacy",
        "source": SOURCE,
        "run_id": run_id,
        "started_at": timezone.now().isoformat(),
        "operator_prompt": prompt,
        "posts": [],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    organization = _user_organization(user)
    _ensure_departments(organization)
    company = _ensure_company(
        user=user,
        organization=organization,
        company_name="Legacy",
        external_ref=DEFAULT_COMPANY_EXTERNAL_REF,
    )
    _ensure_pack(company=company, user=user)
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
        run_context={
            "source": SOURCE,
            "single_prompt_boundary": True,
            "media_worker": "codex_media_worker",
        },
    )

    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)
    strategy_deliverable = build_codex_deliverable_for_stage(
        engagement=engagement,
        stage_state=strategy,
        user=user,
        deliverable_type="codex_strategy_brief",
        title="Legacy Optical Noir Strategy Brief",
        prompt=_stage_prompt(prompt, "strategy_research"),
    )
    complete_stage(strategy, actor=user)

    brand = stage_state_for_engagement(engagement, "brand_content")
    start_stage(brand, actor=user)
    brand_deliverable = _generated_deliverable(
        engagement=engagement,
        stage_id="brand_content",
        user=user,
        deliverable_type="message_house",
        title="Legacy Optical Noir Message House",
        content=_message_house(prompt),
    )
    complete_stage(brand, actor=user)

    crm = stage_state_for_engagement(engagement, "crm_lifecycle")
    start_stage(crm, actor=user)
    crm_deliverable = _generated_deliverable(
        engagement=engagement,
        stage_id="crm_lifecycle",
        user=user,
        deliverable_type="crm_scripts",
        title="Legacy WhatsApp / DM Response Scripts",
        content=_crm_scripts(),
    )
    complete_stage(crm, actor=user)

    analytics = stage_state_for_engagement(engagement, "analytics_performance")
    start_stage(analytics, actor=user)
    analytics_deliverable = _generated_deliverable(
        engagement=engagement,
        stage_id="analytics_performance",
        user=user,
        deliverable_type="measurement_plan",
        title="Legacy Manual Measurement Plan",
        content=_measurement_plan(),
    )
    complete_stage(analytics, actor=user)

    channel = stage_state_for_engagement(engagement, "channel_execution")
    start_stage(channel, actor=user)
    media_jobs = []
    for index, media_prompt in enumerate(_media_prompts(prompt), start=1):
        job = enqueue_codex_image_job(
            user=user,
            company=company,
            prompt=media_prompt,
            idempotency_key=f"{run_id}:optical-noir-post-{index:02d}",
            metadata={
                "run_id": run_id,
                "engagement_id": str(engagement.id),
                "stage_id": "channel_execution",
                "post_index": index,
            },
        )
        media_jobs.append(job)
    worker_results = CodexMediaWorker().process_batch(limit=len(media_jobs), company=company)
    media_jobs = [type(job).objects.get(id=job.id) for job in media_jobs]
    failed = [job for job in media_jobs if job.status != "succeeded"]
    if failed:
        raise RuntimeError(
            "ForgeGraph Codex media worker failed jobs: "
            + ", ".join(f"{job.id}:{job.error_code}" for job in failed)
        )
    for job in media_jobs:
        if job.output_asset is not None:
            attach_asset_to_stage(job.output_asset, channel, output_kind="codex_media_asset")
    channel_deliverable = _generated_deliverable(
        engagement=engagement,
        stage_id="channel_execution",
        user=user,
        deliverable_type="channel_asset_map",
        title="Legacy Channel Asset Map",
        content=_channel_asset_map(media_jobs),
    )
    complete_stage(
        channel,
        outputs=[
            {"kind": "media_generation_job", "type": "media_generation_job", "id": str(job.id)}
            for job in media_jobs
        ],
        actor=user,
    )

    qa = stage_state_for_engagement(engagement, "qa_compliance")
    start_stage(qa, actor=user)
    qa_deliverable = _generated_deliverable(
        engagement=engagement,
        stage_id="qa_compliance",
        user=user,
        deliverable_type="qa_report",
        title="Legacy Launch QA Report",
        content=_qa_report(media_jobs),
    )
    complete_stage(qa, actor=user)

    approval = stage_state_for_engagement(engagement, "client_approval_ops")
    start_stage(approval, actor=user)
    package = _build_client_package(
        root=root,
        run_id=run_id,
        engagement=engagement,
        whiteboard=whiteboard,
        prompt=prompt,
        media_jobs=media_jobs,
        deliverables=[
            strategy_deliverable,
            brand_deliverable,
            crm_deliverable,
            analytics_deliverable,
            channel_deliverable,
            qa_deliverable,
        ],
    )
    package_deliverable = _package_deliverable(
        engagement=engagement,
        user=user,
        package=package,
        stage_id="client_approval_ops",
    )
    complete_stage(
        approval,
        outputs=[
            {
                "kind": "client_package",
                "type": "service_deliverable",
                "id": str(package_deliverable.id),
            }
        ],
        actor=user,
    )

    engagement.status = "delivered" if send else "in_progress"
    engagement.customer_status = "ready_for_review"
    engagement.metadata_json = {
        **dict(engagement.metadata_json or {}),
        "atlas_prompt_delivery": True,
        "source": SOURCE,
        "single_prompt_boundary": True,
        "codex_media_worker_results": [
            {
                "job_id": str(result.job_id),
                "status": result.status,
                "error_code": result.error_code,
            }
            for result in worker_results
        ],
        "package_sha256": package["sha256"],
    }
    engagement.save(update_fields=["status", "customer_status", "metadata_json", "updated_at"])
    whiteboard.status = WorkWhiteboard.STATUS_IN_APPROVAL
    whiteboard.work_status = (
        WorkWhiteboard.WORK_STATUS_DELIVERY if send else WorkWhiteboard.WORK_STATUS_REVIEW
    )
    whiteboard.save(update_fields=["status", "work_status", "updated_at"])
    refresh_whiteboard_task_snapshot(whiteboard, program)

    if (
        send
        and not package["gate_report"]["ready"]
        and not _truthy_env("FORGEGRAPH_ATLAS_ALLOW_CLIENT_GATE_OVERRIDE")
    ):
        issue_codes = ", ".join(issue["code"] for issue in package["gate_report"]["issues"])
        raise RuntimeError(
            "Client package quality gates failed; run dry/revision before WhatsApp send: "
            + issue_codes
        )

    text_message_id = ""
    media_message_id = ""
    receipt = None
    if send:
        text_message_id, media_message_id = _send_whatsapp(
            bridge_url=whatsapp_bridge_url,
            phone_e164=phone_e164,
            package_path=package["zip_path"],
            package_filename=Path(package["zip_path"]).name,
        )
        receipt = _persist_delivery_receipt(
            engagement=engagement,
            package_deliverable=package_deliverable,
            package_asset=package["asset"],
            package_version=package["version"],
            phone_e164=phone_e164,
            text_message_id=text_message_id,
            media_message_id=media_message_id,
            package_sha256=package["sha256"],
        )

    return AtlasPromptDeliveryResult(
        engagement_id=engagement.id,
        whiteboard_id=whiteboard.id,
        package_path=package["zip_path"],
        package_sha256=package["sha256"],
        text_message_id=text_message_id,
        media_message_id=media_message_id,
        receipt_id=receipt.id if receipt else None,
        media_job_ids=[str(job.id) for job in media_jobs],
    )


def _ensure_departments(organization) -> None:
    for slug, name in DEPARTMENTS.items():
        department, _ = DepartmentRegistry.objects.get_or_create(
            organization=organization,
            slug=slug,
            defaults={"name": name, "department_type": "atlas_agency"},
        )
        department.name = name
        department.department_type = "atlas_agency"
        department.active = True
        department.service_tags_json = ["atlas", "digital_marketing_pro", "codex_media"]
        department.metadata_json = {
            **dict(department.metadata_json or {}),
            "source": SOURCE,
            "pack_id": PACK_ID,
        }
        department.save()


def _stage_prompt(prompt: str, stage_id: str) -> str:
    return (
        "Create the strategy brief for a client-facing Atlas agency run. "
        "No markdown files will be sent to the client; this content becomes internal lineage and source for HTML/PDF packaging. "
        f"Stage: {stage_id}. User prompt: {prompt}"
    )


def _generated_deliverable(
    *, engagement, stage_id: str, user, deliverable_type: str, title: str, content: str
) -> ServiceDeliverable:
    stage = stage_state_for_engagement(engagement, stage_id)
    data = content.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    asset = ArchiveService().create_asset(
        company=engagement.company,
        title=title,
        asset_type="internal_deliverable",
        source_key=f"{SOURCE}:{engagement.id}:{deliverable_type}",
        created_by_type="system",
        created_by_id=user.id if user else None,
        metadata={"source": SOURCE, "stage_id": stage_id, "client_facing": False},
    )
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri=f"forgegraph://atlas-prompt-delivery/{engagement.id}/{deliverable_type}.txt",
        content=data,
        mime_type="text/plain",
        provenance={
            "source": SOURCE,
            "stage_id": stage_id,
            "content_hash": digest,
            "inline_content": content,
        },
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
    deliverable.visibility = "operator"
    deliverable.artifact = asset
    deliverable.summary = content[:900]
    deliverable.metadata_json = {
        "source": SOURCE,
        "stage_id": stage_id,
        "asset_version_id": str(version.id),
    }
    deliverable.save()
    attach_asset_to_stage(asset, stage, output_kind=deliverable_type)
    attach_deliverable_to_stage(deliverable, stage, output_kind=deliverable_type)
    return deliverable


def _message_house(prompt: str) -> str:
    _ = prompt
    return "\n".join(
        [
            "Legacy Optical Noir Message House",
            "Strategic rationale: Optical Noir is a premium contrast system for product photography, not a literal night-use claim for sunglasses.",
            "Why it works: black, ivory, copper, and controlled reflections make frames and lenses feel sharper, more editorial, and easier to remember in-feed.",
            "Positioning: lujo usable para CDMX; editorial, sobrio, accesible-premium.",
            "Brand presence: every social post should carry a Legacy logo or approved brand mark treatment unless the client explicitly requests clean product-only assets.",
            "Primary CTA: revisar estilos y aprobar piezas antes de publicar.",
            "Tone: Spanish-first, concrete, low-hype, confident.",
        ]
    )


def _crm_scripts() -> str:
    return "\n".join(
        [
            "WhatsApp / DM scripts",
            "Disponibilidad: Te confirmo modelo/color y te comparto alternativas si ya se movió.",
            "Precio: Son piezas premium; te ayudo a elegir el par que mejor se vea y más uses.",
            "Cierre: ¿Quieres que te aparte este modelo o prefieres ver dos opciones más?",
        ]
    )


def _measurement_plan() -> str:
    return (
        "Track the weekend social rollout and posting cadence: post saves, replies, profile visits, "
        "link clicks, DMs, holds, sold/blocked status, and next action every 24h. This is a posting "
        "and review cadence, not a shipping or fulfillment timeline unless the client provides logistics "
        "details. Hold live claims until connector evidence exists."
    )


def _media_prompts(prompt: str) -> list[str]:
    base = (
        "Legacy Optical Noir, premium editorial sunglasses asset, square mobile crop, "
        "deep black, warm ivory, aged copper, subtle green lens reflections, approved Legacy logo "
        "or brand mark in a clean corner lockup, no unrelated visible words, no people, "
        "no fake brand marks. Source prompt: " + prompt
    )
    angles = [
        "Hero frame on smoked glass with cinematic negative space.",
        "Product pair on ivory stone and black lacquer surface.",
        "Three silhouettes arranged as a limited archive.",
        "Rain-window CDMX night bokeh mood with sunglasses foreground.",
        "Buyer-guide modular layout with varied lens tones, no labels.",
        "Gold/copper frame on ivory background with black vertical panel.",
    ]
    return [f"{base} Composition: {angle}" for angle in angles]


def _channel_asset_map(media_jobs: list) -> str:
    return "\n".join(
        ["Channel Asset Map"]
        + [
            f"Post {idx:02d}: media_job={job.id}, asset={job.output_asset_id}, status={job.status}"
            for idx, job in enumerate(media_jobs, start=1)
        ]
    )


def _qa_report(media_jobs: list) -> str:
    all_ready = all(job.status == "succeeded" and job.output_asset_version_id for job in media_jobs)
    return "\n".join(
        [
            "QA Report",
            f"Media jobs succeeded: {sum(job.status == 'succeeded' for job in media_jobs)}/{len(media_jobs)}",
            "Client package formats: HTML, PDF, PNG, JSON manifest, ZIP; no Markdown files.",
            "Policy: no live publishing claim; approval required before production launch.",
            f"Decision: {'ready for review' if all_ready else 'hold'}",
        ]
    )


def _build_client_package(
    *,
    root: Path,
    run_id: str,
    engagement,
    whiteboard,
    prompt: str,
    media_jobs: list,
    deliverables: list,
) -> dict[str, Any]:
    client_dir = root / "client_package"
    assets_dir = client_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    media_manifest = []
    for idx, job in enumerate(media_jobs, start=1):
        assert job.output_asset_version is not None
        content, source_metadata = _client_package_media_content(job=job, index=idx)
        filename = f"legacy_optical_noir_post_{idx:02d}.png"
        (assets_dir / filename).write_bytes(content)
        media_manifest.append(
            {
                "post": idx,
                "filename": f"assets/{filename}",
                "media_generation_job_id": str(job.id),
                "asset_id": str(job.output_asset_id),
                "asset_version_id": str(job.output_asset_version_id),
                **source_metadata,
            }
        )
    brand_requirements = _legacy_brand_requirements()
    asset_quality_gate = _asset_quality_gate_status(
        media_manifest,
        logo_required=brand_requirements["logo_required_on_posts"],
    )
    package_manifest = {
        "run_id": run_id,
        "source": SOURCE,
        "engagement_id": str(engagement.id),
        "whiteboard_id": str(whiteboard.id),
        "client": "Legacy",
        "prompt_boundary": "Hermes/operator supplied one prompt; ForgeGraph executed departments, Codex media worker, package, and delivery.",
        "media": media_manifest,
        "brand_requirements": brand_requirements,
        "asset_quality_gate": asset_quality_gate,
        "deliverables": [
            {"id": str(d.id), "type": d.deliverable_type, "title": d.title} for d in deliverables
        ],
        "client_files_policy": "No Markdown files included.",
    }
    deliverable_sections = _deliverable_sections(deliverables)
    package_manifest["quality_gate_report"] = _client_package_gate_report(
        manifest=package_manifest,
        deliverable_sections=deliverable_sections,
    )
    html_text = _client_html(
        prompt=prompt,
        manifest=package_manifest,
        deliverable_sections=deliverable_sections,
    )
    html_path = client_dir / "Legacy_Optical_Noir_Handoff.html"
    html_path.write_text(html_text, encoding="utf-8")
    fallback_text = _client_package_text(
        prompt=prompt,
        manifest=package_manifest,
        deliverable_sections=deliverable_sections,
    )
    pdf_bytes = _client_pdf_bytes(html_path=html_path, fallback_text=fallback_text)
    (client_dir / "Legacy_Optical_Noir_Handoff.pdf").write_bytes(pdf_bytes)
    (client_dir / "manifest.json").write_text(
        json.dumps(package_manifest, indent=2), encoding="utf-8"
    )
    zip_path = root / "Legacy_Optical_Noir_FORGEGRAPH_CLIENT.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(client_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(client_dir).as_posix()
                if rel.lower().endswith((".md", ".markdown")):
                    raise ValueError("Client package cannot include Markdown files.")
                zf.write(path, rel)
    data = zip_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    asset = ArchiveService().create_asset(
        company=engagement.company,
        title="Legacy Optical Noir Client ZIP Package",
        asset_type="client_package_zip",
        source_key=f"{SOURCE}:{engagement.id}:client_zip",
        created_by_type="system",
        metadata={"source": SOURCE, "client_facing": True, "sha256": sha, "no_markdown": True},
    )
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri=str(zip_path),
        content=data,
        mime_type="application/zip",
        provenance={
            "source": SOURCE,
            "path": str(zip_path),
            "sha256": sha,
            "manifest": package_manifest,
        },
    )
    return {
        "zip_path": str(zip_path),
        "sha256": sha,
        "asset": asset,
        "version": version,
        "gate_report": package_manifest["quality_gate_report"],
    }


def _client_package_media_content(*, job, index: int) -> tuple[bytes, dict[str, Any]]:
    override_dir = os.environ.get("FORGEGRAPH_ATLAS_REVIEW_ASSETS_DIR", "").strip()
    filename = f"legacy_optical_noir_post_{index:02d}.png"
    if override_dir:
        candidate = Path(override_dir) / filename
        if candidate.exists() and candidate.is_file():
            return candidate.read_bytes(), {
                "asset_source": "operator_review_assets_override",
                "asset_source_path": str(candidate),
                "quality_tier": "review_ready_ai_generated",
                "production_quality": True,
                "brand_mark_applied": _truthy_env("FORGEGRAPH_ATLAS_BRAND_MARK_APPLIED"),
            }
    content, _mime_type, _filename = read_media_asset_version_content(job.output_asset_version)
    return content, {
        "asset_source": "forgegraph_media_generation_job",
        "quality_tier": "placeholder_review_asset",
        "production_quality": False,
        "brand_mark_applied": False,
    }


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _legacy_brand_requirements() -> dict[str, Any]:
    return {
        "logo_required_on_posts": True,
        "logo_policy": "approved_legacy_logo_or_operator_supplied_brand_mark_required",
        "block_production_without_logo_asset": True,
    }


def _asset_quality_gate_status(
    media_manifest: list[dict[str, Any]], *, logo_required: bool
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for item in media_manifest:
        post = item.get("post")
        if not item.get("production_quality"):
            issues.append({"post": post, "code": "not_production_quality"})
        if logo_required and not item.get("brand_mark_applied"):
            issues.append({"post": post, "code": "missing_brand_mark"})
        if item.get("client_flagged_bad"):
            issues.append({"post": post, "code": "client_flagged_bad"})
    return {"ready": not issues, "issues": issues}


def _client_package_gate_report(
    *, manifest: dict[str, Any], deliverable_sections: list[dict[str, str]]
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    combined_text = "\n".join(str(section.get("content") or "") for section in deliverable_sections)
    lowered = combined_text.lower()
    if not _has_strategy_rationale(lowered):
        issues.append(
            {
                "code": "missing_strategy_rationale",
                "department_slug": "strategy_research",
                "severity": "revision",
            }
        )
    if _has_ambiguous_distribution_copy(lowered):
        issues.append(
            {
                "code": "ambiguous_distribution_copy",
                "department_slug": "channel_execution",
                "severity": "revision",
            }
        )
    brand_requirements = dict(manifest.get("brand_requirements") or {})
    asset_gate = _asset_quality_gate_status(
        list(manifest.get("media") or []),
        logo_required=bool(brand_requirements.get("logo_required_on_posts")),
    )
    issues.extend(asset_gate["issues"])
    return {
        "ready": not issues,
        "issues": issues,
        "required_gates": [
            "strategy_rationale",
            "brand_logo_requirement",
            "asset_visual_qa",
            "copy_ambiguity_review",
        ],
    }


def _has_strategy_rationale(lowered: str) -> bool:
    return (
        "strategic rationale" in lowered
        and "product photography" in lowered
        and "not a literal night-use claim" in lowered
    )


def _has_ambiguous_distribution_copy(lowered: str) -> bool:
    if "distribution" not in lowered:
        return False
    clarifiers = (
        "social rollout",
        "posting cadence",
        "not a shipping",
        "not shipping",
        "fulfillment timeline",
    )
    return not any(clarifier in lowered for clarifier in clarifiers)


def _deliverable_sections(deliverables: list) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for deliverable in deliverables:
        title = str(
            getattr(deliverable, "title", "") or getattr(deliverable, "deliverable_type", "")
        )
        content = _deliverable_content(deliverable)
        if not content:
            continue
        sections.append(
            {
                "title": title,
                "type": str(getattr(deliverable, "deliverable_type", "source")),
                "content": content,
            }
        )
    return sections


def _deliverable_content(deliverable) -> str:
    metadata = dict(getattr(deliverable, "metadata_json", {}) or {})
    version_id = str(metadata.get("asset_version_id") or "").strip()
    if version_id and getattr(deliverable, "artifact_id", None):
        version = AssetVersion.objects.filter(id=version_id, asset=deliverable.artifact).first()
        content = _asset_version_inline_text(version)
        if content:
            return content
    summary = str(getattr(deliverable, "summary", "") or "").strip()
    if summary:
        return summary
    return ""


def _asset_version_inline_text(version: AssetVersion | None) -> str:
    if version is None:
        return ""
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    inline = provenance.get("inline_content")
    if isinstance(inline, str):
        return inline.strip()
    if inline is not None:
        return json.dumps(inline, sort_keys=True, default=str)
    return ""


def _client_section_body_html(content: str) -> str:
    """Render markdown-ish department output as polished client-visible HTML.

    Codex/department source deliverables may be Markdown because they double as
    internal lineage. The client handoff must not display raw Markdown markers or
    internal IDs, so this deliberately implements a small safe subset instead of
    dumping escaped source text.
    """

    renderer = _ClientSectionRenderer()
    for raw_line in str(content or "").splitlines():
        renderer.add_line(raw_line)
    return renderer.render()


@dataclass
class _ClientSectionRenderer:
    blocks: list[str] | None = None
    paragraph: list[str] | None = None
    bullets: list[str] | None = None
    table_headers: list[str] | None = None

    def __post_init__(self) -> None:
        self.blocks = [] if self.blocks is None else self.blocks
        self.paragraph = [] if self.paragraph is None else self.paragraph
        self.bullets = [] if self.bullets is None else self.bullets
        self.table_headers = [] if self.table_headers is None else self.table_headers

    def add_line(self, raw_line: str) -> None:
        line = raw_line.strip()
        if not line:
            self.flush()
            return
        if _is_internal_client_line(line):
            return
        if self._append_heading(line):
            return
        if self._append_table_row(line):
            return
        if self._append_bullet(line):
            return
        self.table_headers = []
        assert self.paragraph is not None
        self.paragraph.append(line)

    def _append_heading(self, line: str) -> bool:
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if not heading:
            return False
        self.flush()
        assert self.blocks is not None
        title = html.escape(_strip_markdown_emphasis(heading.group(1).strip()))
        self.blocks.append(f"<h3>{title}</h3>")
        return True

    def _append_bullet(self, line: str) -> bool:
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)$", line)
        if not bullet:
            return False
        self.flush_paragraph()
        assert self.bullets is not None
        self.bullets.append(bullet.group(1).strip())
        return True

    def _append_table_row(self, line: str) -> bool:
        cells = _parse_markdown_table_cells(line)
        if cells is None:
            return False
        if _is_markdown_table_separator(cells):
            return True
        assert self.table_headers is not None
        if not self.table_headers:
            self.flush_paragraph()
            self.table_headers = cells
            return True
        formatted = _format_markdown_table_row(self.table_headers, cells)
        if formatted:
            self.flush_paragraph()
            assert self.bullets is not None
            self.bullets.append(formatted)
        return True

    def flush(self) -> None:
        self.flush_paragraph()
        self.flush_bullets()
        self.table_headers = []

    def flush_paragraph(self) -> None:
        assert self.blocks is not None
        assert self.paragraph is not None
        if self.paragraph:
            self.blocks.append(f"<p>{_inline_client_markup(' '.join(self.paragraph))}</p>")
            self.paragraph = []

    def flush_bullets(self) -> None:
        assert self.blocks is not None
        assert self.bullets is not None
        if self.bullets:
            items = "".join(f"<li>{_inline_client_markup(item)}</li>" for item in self.bullets)
            self.blocks.append(f"<ul>{items}</ul>")
            self.bullets = []

    def render(self) -> str:
        self.flush()
        assert self.blocks is not None
        if not self.blocks:
            return "<p>Review-ready department output is archived in the package manifest.</p>"
        return "\n".join(self.blocks)


def _parse_markdown_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < 2:
        return None
    return cells


def _is_markdown_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells if cell.strip())


def _format_markdown_table_row(headers: list[str], cells: list[str]) -> str:
    pairs = [
        (header.strip(), cell.strip())
        for header, cell in zip(headers, cells, strict=False)
        if header.strip() and cell.strip()
    ]
    return "; ".join(f"**{header}:** {cell}" for header, cell in pairs)


def _is_internal_client_line(line: str) -> bool:
    lowered = line.lower().lstrip("#*->•0123456789. )\t")
    internal_tokens = (
        "run context",
        "intended use:",
        "internal lineage",
        "asset_version_id",
        "service_deliverable_id",
        "whiteboard_id",
        "engagement_id",
        "trace_id",
        "run_id:",
        "stage:",
        "department stage:",
        "department slug:",
        "run owner:",
        "delivery recipient:",
        "client file rule:",
        "source prompt:",
        "media_job=",
        " asset=",
    )
    return any(token in lowered for token in internal_tokens)


def _inline_client_markup(value: str) -> str:
    cleaned = _strip_markdown_links(value.strip()).replace("`", "")
    escaped = html.escape(cleaned)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def _strip_markdown_links(value: str) -> str:
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", value)


def _strip_markdown_emphasis(value: str) -> str:
    return re.sub(r"[*_`]+", "", _strip_markdown_links(value)).strip()


def _client_html(
    *,
    prompt: str,
    manifest: dict[str, Any],
    deliverable_sections: list[dict[str, str]] | None = None,
) -> str:
    _ = prompt  # Prompt remains archived in manifest.json, not visible client copy.
    sections = deliverable_sections or []
    asset_cards = "\n".join(
        f"""
        <article class=\"asset\">
          <img src=\"{html.escape(item["filename"])}\" alt=\"Legacy Optical Noir post {item["post"]:02d}\">
          <div><strong>Post {item["post"]:02d}</strong><span>{html.escape(item["filename"])}</span></div>
        </article>"""
        for item in manifest["media"]
    )
    section_cards = "\n".join(
        f"""
        <section class=\"card source-card\">
          <p class=\"eyebrow\">{html.escape(section.get("type", "department")).replace("_", " ").title()}</p>
          <h2>{html.escape(section["title"])}</h2>
          {_client_section_body_html(section["content"])}
        </section>"""
        for section in sections
    )
    return f"""<!doctype html>
<html lang=\"es\"><head><meta charset=\"utf-8\"><title>Legacy Optical Noir</title>
<style>
:root{{color-scheme:dark;--bg:#070605;--panel:#15110e;--ink:#f7ecd6;--muted:#cbb99c;--line:#a66a2a66;--accent:#d39a4c;--green:#123f38}}
*{{box-sizing:border-box}}body{{font-family:Inter,Arial,sans-serif;background:radial-gradient(circle at 20% 0%,#22170f 0,#070605 42%,#030303 100%);color:var(--ink);margin:0;line-height:1.58}}
main{{max-width:1120px;margin:0 auto;padding:56px 40px 72px}}.hero{{border:1px solid var(--line);border-radius:28px;padding:36px;background:linear-gradient(135deg,#17110d,#090807 60%,#0d241f);box-shadow:0 24px 80px #0008}}
h1{{font-size:42px;line-height:1.05;margin:0 0 14px}}.dek{{font-size:18px;color:var(--muted);max-width:820px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:24px}}
.card{{background:color-mix(in srgb,var(--panel) 88%,#000);border:1px solid var(--line);border-radius:22px;padding:24px}}.card h2{{margin:4px 0 12px;color:#ffe4bd}}.eyebrow{{letter-spacing:.12em;text-transform:uppercase;font-size:12px;color:var(--accent);margin:0 0 8px}}
.assets{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:18px}}.asset{{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#0b0908}}.asset img{{display:block;width:100%;aspect-ratio:1/1;object-fit:cover;background:#111}}.asset div{{padding:12px 14px;display:flex;flex-direction:column;gap:2px}}.asset span{{color:var(--muted);font-size:12px;word-break:break-all}}
ul{{padding-left:20px}}code{{color:#f0b869;white-space:nowrap}}.source-card p:last-child{{white-space:normal}}.footer{{color:var(--muted);font-size:13px;margin-top:24px}}
@page{{size:Letter;margin:0}}@media print{{*{{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}}body{{background:#070605!important}}main{{max-width:none;width:100%;padding:28px 26px 36px}}h1{{font-size:31px}}.dek{{font-size:13px}}.hero{{padding:24px;border-radius:18px;break-inside:avoid}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:16px}}.card{{padding:16px;border-radius:16px;break-inside:avoid;page-break-inside:avoid}}.card h2{{font-size:17px;margin-bottom:8px}}.asset-gallery{{break-before:page;page-break-before:always}}.assets{{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.asset{{border-radius:12px;break-inside:avoid}}.asset div{{padding:8px 10px}}.asset span{{display:none}}.source-card{{margin-top:12px}}}}
</style></head>
<body><main>
<header class=\"hero\"><p class=\"eyebrow\">ForgeGraph client handoff</p><h1>Legacy Optical Noir — entrega para revisión</h1>
<p class=\"dek\">Paquete armado desde el prompt operativo, con estrategia, contenido, assets, medición, QA y evidencia de linaje listos para aprobación. No se afirma publicación en vivo: el lanzamiento queda condicionado a aprobación y conectores reales.</p></header>
<div class=\"grid\">
<section class=\"card\"><p class=\"eyebrow\">Approval checkpoint</p><h2>Decisión solicitada</h2><ul><li>Dirección visual Optical Noir</li><li>Uso de los assets incluidos como borradores de campaña</li><li>Tono Spanish-first, concreto y de baja exageración</li><li>Launch posterior sólo con aprobación y recibos de canal</li></ul></section>
<section class=\"card\"><p class=\"eyebrow\">Artifact Index</p><h2>ForgeGraph archived run</h2><p>Engagement, whiteboard, asset checksums, source deliverables, and media provenance are archived in <code>manifest.json</code>. The visible handoff keeps internal IDs out of client copy.</p><p>{html.escape(str(manifest.get("client_files_policy", "No Markdown files included.")))}</p></section>
</div>
<section class=\"card asset-gallery\"><p class=\"eyebrow\">Assets</p><h2>Posts incluidos</h2><div class=\"assets\">{asset_cards}</div></section>
{section_cards}
<p class=\"footer\">Paquete generado por ForgeGraph para revisión interna/client-facing. Requiere aprobación antes de producción. La solicitud operacional completa queda archivada en manifest.json.</p>
</main></body></html>"""


def _client_plain_text(content: str) -> str:
    lines: list[str] = []
    table_headers: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line or _is_internal_client_line(line):
            table_headers = []
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            table_headers = []
            lines.append(_strip_markdown_emphasis(heading.group(1).strip()))
            continue
        table_cells = _parse_markdown_table_cells(line)
        if table_cells is not None:
            if _is_markdown_table_separator(table_cells):
                continue
            if not table_headers:
                table_headers = table_cells
                continue
            formatted = _format_markdown_table_row(table_headers, table_cells)
            if formatted:
                lines.append(_strip_markdown_emphasis(formatted))
            continue
        table_headers = []
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)$", line)
        if bullet:
            lines.append(f"- {_strip_markdown_emphasis(bullet.group(1).strip())}")
            continue
        lines.append(_strip_markdown_emphasis(line))
    return "\n".join(lines).strip()


def _client_package_text(
    *,
    prompt: str,
    manifest: dict[str, Any],
    deliverable_sections: list[dict[str, str]],
) -> str:
    _ = prompt  # Prompt remains archived in manifest.json, not visible client copy.
    lines = [
        "Legacy Optical Noir — client handoff",
        "",
        "Decision requested: approve the Optical Noir direction, draft assets, Spanish-first copy tone, and approval-gated launch path.",
        "No live publishing claim is made; production launch requires approval and connector receipts.",
        "",
        "Run evidence: manifest.json includes archived engagement, whiteboard, asset checksum, source deliverable, and media provenance records.",
        "",
        "Assets included:",
    ]
    lines.extend(f"- Post {item['post']:02d}: {item['filename']}" for item in manifest["media"])
    lines.extend(["", "Department deliverables:"])
    for section in deliverable_sections:
        body = _client_plain_text(section["content"])
        if body:
            lines.extend(["", section["title"], body])
    return "\n".join(lines).strip() + "\n"


def _client_pdf_bytes(
    body_text: str | None = None,
    *,
    html_path: Path | None = None,
    fallback_text: str | None = None,
) -> bytes:
    """Create the client PDF.

    Preferred path mirrors Hermes/browser artifacts: render the exact HTML handoff
    through Chromium/Playwright so the PDF preserves layout, colors, cards, and
    images. If Playwright is unavailable in a local/dev environment, keep the
    old text renderer as a deterministic fallback instead of failing package
    generation.
    """

    if html_path is not None:
        try:
            return _render_html_pdf_with_playwright(html_path)
        except RuntimeError:
            pass
    text = fallback_text or body_text or ""
    return _pdf_document_bytes(_pdf_pages(text))


def _render_html_pdf_with_playwright(html_path: Path) -> bytes:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node executable not found for HTML-to-PDF rendering")
    playwright_cwd = _playwright_module_cwd()
    if playwright_cwd is None:
        raise RuntimeError("playwright module not found for HTML-to-PDF rendering")
    html_path = html_path.resolve()
    if not html_path.exists():
        raise RuntimeError(f"HTML handoff not found: {html_path}")

    script_path = _html_pdf_playwright_script_path()
    with tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="forgegraph-client-handoff-", dir=html_path.parent, delete=False
    ) as output_file:
        output_path = Path(output_file.name)
    try:
        env = os.environ.copy()
        env["NODE_PATH"] = str(playwright_cwd / "node_modules")
        result = subprocess.run(
            [node, str(script_path), str(html_path), str(output_path)],
            cwd=str(playwright_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown Playwright failure").strip()
            raise RuntimeError(f"Playwright HTML-to-PDF failed: {detail[:1000]}")
        pdf_bytes = output_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF-") or not pdf_bytes.rstrip().endswith(b"%%EOF"):
            raise RuntimeError("Playwright HTML-to-PDF produced invalid PDF bytes")
        return pdf_bytes
    finally:
        output_path.unlink(missing_ok=True)


def _playwright_module_cwd() -> Path | None:
    explicit = os.environ.get("FORGEGRAPH_PLAYWRIGHT_NODE_CWD", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    backend_root = Path(__file__).resolve().parents[2]
    project_root = backend_root.parent
    candidates.extend(
        [
            project_root / "frontend",
            backend_root,
            project_root,
            Path.cwd(),
            Path.cwd() / "frontend",
            Path.cwd().parent / "frontend",
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "node_modules" / "playwright").exists():
            return resolved
    return None


def _html_pdf_playwright_script_path() -> Path:
    script_path = Path(tempfile.gettempdir()) / "forgegraph_html_to_pdf_playwright.cjs"
    script_path.write_text(_HTML_TO_PDF_PLAYWRIGHT_SCRIPT, encoding="utf-8")
    return script_path


_HTML_TO_PDF_PLAYWRIGHT_SCRIPT = r"""
const { chromium } = require('playwright');
const path = require('path');
const { pathToFileURL } = require('url');

const inputPath = process.argv[2];
const outputPath = process.argv[3];

function chromiumLaunchArgs() {
  const rawArgs = process.env.FORGEGRAPH_PLAYWRIGHT_CHROMIUM_ARGS || '';
  const configured = rawArgs.split(',').map((item) => item.trim()).filter(Boolean);
  if (configured.length > 0) {
    return configured;
  }
  if (process.getuid && process.getuid() === 0) {
    return ['--no-sandbox', '--disable-dev-shm-usage'];
  }
  return [];
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: chromiumLaunchArgs() });
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 1800 },
      deviceScaleFactor: 1,
    });
    await page.goto(pathToFileURL(path.resolve(inputPath)).href, {
      waitUntil: 'load',
      timeout: 30000,
    });
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
    await page.emulateMedia({ media: 'print' });
    await page.addStyleTag({
      content: `
        @page { size: Letter; margin: 0; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
      `,
    });
    await page.pdf({
      path: path.resolve(outputPath),
      format: 'Letter',
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
    });
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""


def _pdf_escape(value: str) -> str:
    return re.sub(r"[()\\]", lambda m: "\\" + m.group(0), value)[:120]


def _package_deliverable(
    *, engagement, user, package: dict[str, Any], stage_id: str
) -> ServiceDeliverable:
    stage = stage_state_for_engagement(engagement, stage_id)
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type="client_zip_package",
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "created_by": user,
        },
    )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = "Legacy Optical Noir Client Package"
    deliverable.status = "ready"
    deliverable.visibility = "customer"
    deliverable.artifact = package["asset"]
    deliverable.summary = (
        "Client-ready ZIP containing HTML, PDF, six PNG assets, and manifest; no Markdown files."
    )
    deliverable.metadata_json = {
        "source": SOURCE,
        "stage_id": stage_id,
        "asset_version_id": str(package["version"].id),
        "sha256": package["sha256"],
    }
    deliverable.save()
    attach_asset_to_stage(package["asset"], stage, output_kind="client_zip_package")
    attach_deliverable_to_stage(deliverable, stage, output_kind="client_zip_package")
    return deliverable


def _send_whatsapp(
    *, bridge_url: str, phone_e164: str, package_path: str, package_filename: str
) -> tuple[str, str]:
    chat_id = _phone_to_chat_id(phone_e164)
    text_payload = {
        "chatId": chat_id,
        "message": "Hola Mike — ForgeGraph corrió la entrega de Legacy completa: estrategia, worker Codex para assets, QA y ZIP final. Te lo mando para revisión.",
    }
    request_headers = _bridge_request_headers(bridge_url)
    text_response = requests.post(
        f"{bridge_url.rstrip('/')}/send",
        json=text_payload,
        headers=request_headers,
        timeout=30,
    )
    text_response.raise_for_status()
    media_payload = {
        "chatId": chat_id,
        "filePath": _bridge_visible_file_path(bridge_url, package_path),
        "mediaType": "document",
        "caption": "Legacy Optical Noir — entrega ForgeGraph para revisión.",
        "fileName": package_filename,
    }
    media_response = requests.post(
        f"{bridge_url.rstrip('/')}/send-media",
        json=media_payload,
        headers=request_headers,
        timeout=120,
    )
    media_response.raise_for_status()
    return _message_id(text_response.json()), _message_id(media_response.json())


def _bridge_request_headers(bridge_url: str) -> dict[str, str]:
    parsed = urlparse(bridge_url)
    if parsed.hostname == "host.docker.internal":
        port = f":{parsed.port}" if parsed.port else ""
        return {"Host": f"127.0.0.1{port}"}
    return {}


def _bridge_visible_file_path(bridge_url: str, package_path: str) -> str:
    parsed = urlparse(bridge_url)
    if parsed.hostname != "host.docker.internal":
        return package_path
    host_backend_path = os.environ.get("FORGEGRAPH_HOST_BACKEND_PATH", "").strip()
    if not host_backend_path:
        return package_path
    normalized = package_path.replace("\\", "/")
    if normalized == "/app":
        return host_backend_path
    if normalized.startswith("/app/"):
        relative = normalized[len("/app/") :]
        clean_host_backend_path = host_backend_path.rstrip("/\\")
        return f"{clean_host_backend_path}/{relative}"
    return package_path


def _phone_to_chat_id(phone_e164: str) -> str:
    digits = re.sub(r"\D+", "", phone_e164)
    return f"{digits}@c.us"


def _message_id(payload: dict[str, Any]) -> str:
    return str(payload.get("messageId") or payload.get("id") or payload.get("message_id") or "")


def _persist_delivery_receipt(
    *,
    engagement,
    package_deliverable,
    package_asset: Asset,
    package_version: AssetVersion,
    phone_e164: str,
    text_message_id: str,
    media_message_id: str,
    package_sha256: str,
) -> CommunicationEventReceipt:
    thread, _ = CommunicationThread.objects.get_or_create(
        organization=engagement.organization,
        company=engagement.company,
        source_key=f"{SOURCE}:{engagement.id}:whatsapp",
        defaults={
            "service_engagement": engagement,
            "artifact": package_asset,
            "title": "Legacy Optical Noir WhatsApp Delivery",
            "thread_type": "deliverable",
            "visibility_mode": "customer",
            "status": "waiting_on_customer",
        },
    )
    message, _ = CommunicationMessage.objects.get_or_create(
        thread=thread,
        idempotency_key=f"{SOURCE}:{engagement.id}:package-message",
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "sender_kind": "company",
            "sender_company": engagement.company,
            "message_kind": "handoff",
            "body": "ForgeGraph delivered Legacy Optical Noir package by WhatsApp for review.",
            "body_format": "plain",
            "visibility": "customer",
        },
    )
    message.organization = engagement.organization
    message.company = engagement.company
    message.sender_kind = "company"
    message.sender_company = engagement.company
    message.message_kind = "handoff"
    message.body = "ForgeGraph delivered Legacy Optical Noir package by WhatsApp for review."
    message.body_format = "plain"
    message.visibility = "customer"
    message.metadata_json = {
        **(message.metadata_json or {}),
        "text_message_id": text_message_id,
        "media_message_id": media_message_id,
        "phone_e164": phone_e164,
        "package_sha256": package_sha256,
    }
    message.save(
        update_fields=[
            "organization",
            "company",
            "sender_kind",
            "sender_company",
            "message_kind",
            "body",
            "body_format",
            "visibility",
            "metadata_json",
            "updated_at",
        ]
    )
    CommunicationAttachment.objects.get_or_create(message=message, artifact=package_asset)
    CommunicationAttachment.objects.get_or_create(
        message=message, artifact_revision=package_version
    )
    CommunicationAttachment.objects.get_or_create(
        message=message, service_deliverable=package_deliverable
    )
    receipt, _ = CommunicationEventReceipt.objects.get_or_create(
        consumer_group="atlas_prompt_delivery.whatsapp",
        idempotency_key=f"{SOURCE}:{engagement.id}:whatsapp:{media_message_id}",
        defaults={
            "event_id": media_message_id,
            "topic": "whatsapp.local_bridge.send_media",
            "organization": engagement.organization,
            "company": engagement.company,
            "event_type": "client_package.delivered",
            "schema_version": "1.0",
            "aggregate_type": "service_engagement",
            "aggregate_id": str(engagement.id),
            "status": "handled",
            "handled_at": timezone.now(),
            "payload_json": {
                "text_message_id": text_message_id,
                "media_message_id": media_message_id,
                "phone_e164": phone_e164,
                "package_sha256": package_sha256,
                "package_asset_id": str(package_asset.id),
                "package_asset_version_id": str(package_version.id),
            },
        },
    )
    return receipt
