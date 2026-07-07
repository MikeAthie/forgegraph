"""CareerOps artifact and deliverable persistence."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyOpportunity,
    Run,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRecord,
)


def write_career_ops_deliverable(
    *,
    engagement: ServiceEngagement,
    run: Run,
    task: TaskRecord | None,
    opportunity: CompanyOpportunity,
    deliverable_type: str,
    title: str,
    payload: dict[str, Any],
) -> tuple[ServiceDeliverable, AssetVersion]:
    """Persist a fake-safe CareerOps deliverable and exact content version."""

    content = json.dumps(payload, sort_keys=True, indent=2)
    data = content.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    source_key = f"career_ops:{opportunity.id}:{deliverable_type}"
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=source_key,
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "document",
            "origin_operation": run,
            "origin_task": task,
            "created_by_type": "system",
            "metadata_json": {},
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "document"
    asset.origin_operation = run
    asset.origin_task = task
    asset.metadata_json = {
        "career_ops": {
            "deliverable_type": deliverable_type,
            "opportunity_id": str(opportunity.id),
            "live_ready": False,
            "external_side_effects_allowed": False,
        }
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
            content_uri=f"forgegraph://career-ops/{opportunity.id}/{deliverable_type}.json",
            content_hash=digest,
            mime_type="application/json",
            size_bytes=len(data),
            provenance_json={"career_ops": payload},
        )

    deliverable = ServiceDeliverable.objects.filter(
        engagement=engagement,
        deliverable_type=deliverable_type,
        artifact=asset,
    ).first()
    if deliverable is None:
        deliverable = ServiceDeliverable.objects.create(
            organization=engagement.organization,
            company=engagement.company,
            engagement=engagement,
            deliverable_type=deliverable_type,
            title=title,
            visibility="operator",
        )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = title
    deliverable.status = "in_review"
    deliverable.visibility = "operator"
    deliverable.artifact = asset
    deliverable.summary = f"CareerOps {deliverable_type} for {opportunity.title}."
    deliverable.metadata_json = {
        "career_ops": {
            "asset_version_id": str(version.id),
            "opportunity_id": str(opportunity.id),
            "live_ready": False,
            "external_side_effects_allowed": False,
        }
    }
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=["origin_deliverable_id", "updated_at"])
    return deliverable, version


def write_career_ops_file_deliverable(
    *,
    engagement: ServiceEngagement,
    run: Run,
    task: TaskRecord | None,
    opportunity: CompanyOpportunity,
    deliverable_type: str,
    title: str,
    content_bytes: bytes,
    mime_type: str,
    file_extension: str,
    payload: dict[str, Any],
) -> tuple[ServiceDeliverable, AssetVersion]:
    """Persist a CareerOps exact-version file deliverable with inline provenance bytes."""

    digest = hashlib.sha256(content_bytes).hexdigest()
    clean_extension = file_extension.lstrip(".") or "bin"
    source_key = f"career_ops:{opportunity.id}:{deliverable_type}"
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=source_key,
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "document",
            "origin_operation": run,
            "origin_task": task,
            "created_by_type": "system",
            "metadata_json": {},
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "document"
    asset.origin_operation = run
    asset.origin_task = task
    asset.metadata_json = {
        "career_ops": {
            "deliverable_type": deliverable_type,
            "opportunity_id": str(opportunity.id),
            "live_ready": False,
            "external_side_effects_allowed": False,
        }
    }
    asset.save()

    career_ops_payload = {
        **payload,
        "deliverable_type": deliverable_type,
        "opportunity_id": str(opportunity.id),
        "mime_type": mime_type,
        "content_hash": digest,
        "size_bytes": len(content_bytes),
        "external_side_effects_allowed": False,
    }
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
            content_uri=f"forgegraph://career-ops/{opportunity.id}/{deliverable_type}.{clean_extension}",
            content_hash=digest,
            mime_type=mime_type,
            size_bytes=len(content_bytes),
            provenance_json={
                "career_ops": career_ops_payload,
                "inline_content_base64": base64.b64encode(content_bytes).decode("ascii"),
            },
        )

    deliverable = ServiceDeliverable.objects.filter(
        engagement=engagement,
        deliverable_type=deliverable_type,
        artifact=asset,
    ).first()
    if deliverable is None:
        deliverable = ServiceDeliverable.objects.create(
            organization=engagement.organization,
            company=engagement.company,
            engagement=engagement,
            deliverable_type=deliverable_type,
            title=title,
            visibility="operator",
        )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = title
    deliverable.status = "in_review"
    deliverable.visibility = "operator"
    deliverable.artifact = asset
    deliverable.summary = f"CareerOps {deliverable_type} for {opportunity.title}."
    deliverable.metadata_json = {
        "career_ops": {
            "asset_version_id": str(version.id),
            "opportunity_id": str(opportunity.id),
            "mime_type": mime_type,
            "live_ready": False,
            "external_side_effects_allowed": False,
        }
    }
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=["origin_deliverable_id", "updated_at"])
    return deliverable, version
