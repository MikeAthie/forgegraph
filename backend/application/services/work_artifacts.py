"""Generic work artifact services backed by Asset and AssetVersion."""

from __future__ import annotations

import json
import re
from typing import Any

from django.db import transaction

from application.services.audit_log import record_audit_log
from application.services.company_archive import ArchiveService, AssetExtractionService
from infrastructure.orm.models import (
    Asset,
    AssetDependency,
    AssetVersion,
    CompanyProgram,
    Graph,
    User,
)


class WorkArtifactError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def create_work_artifact(
    *,
    company: Graph,
    user: User,
    title: str,
    artifact_type: str,
    content: Any,
    program: CompanyProgram | None = None,
    metadata: dict[str, Any] | None = None,
    source_key: str = "",
) -> tuple[Asset, AssetVersion]:
    archive = ArchiveService()
    with transaction.atomic():
        asset = archive.create_asset(
            company=company,
            title=_safe_text(title, 255) or "Work Artifact",
            asset_type="deliverable",
            source_key=_safe_text(source_key, 512),
            created_by_type="user",
            created_by_id=user.id,
            metadata={
                **(metadata or {}),
                "artifact_type": _safe_key(artifact_type) or "other",
                "program_id": str(program.id) if program else None,
            },
        )
        version = _create_inline_version(asset=asset, content=content, label="v1")
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "canonical_asset_version_id": str(version.id),
        }
        asset.save(update_fields=["metadata_json", "updated_at"])
        AssetExtractionService().extract_asset_version(version)
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="work_artifact.created",
        resource_type="work_artifact",
        resource_id=str(asset.id),
        metadata={"company_id": str(company.id), "artifact_type": artifact_type},
    )
    return asset, version


def create_artifact_revision(
    *,
    asset: Asset,
    user: User,
    content: Any,
    parent_version: AssetVersion | None = None,
    label: str = "",
    metadata: dict[str, Any] | None = None,
) -> AssetVersion:
    parent = parent_version or canonical_version(asset) or latest_version(asset)
    with transaction.atomic():
        version = _create_inline_version(
            asset=asset,
            content=content,
            label=label or _next_label(asset),
            metadata=metadata,
        )
        if parent is not None and parent.id != version.id:
            AssetDependency.objects.get_or_create(
                organization=asset.organization,
                company=asset.company,
                source_asset=asset,
                source_asset_version=parent,
                target_asset=asset,
                target_asset_version=version,
                dependency_type="derived_from",
                defaults={"reason": "Artifact revision derived from prior canonical revision."},
            )
        AssetExtractionService().extract_asset_version(version)
    record_audit_log(
        actor=user,
        tenant_id=str(asset.organization_id),
        action="work_artifact.revision_created",
        resource_type="artifact_revision",
        resource_id=str(version.id),
        metadata={"asset_id": str(asset.id), "version_number": version.version_number},
    )
    return version


def set_canonical_revision(*, asset: Asset, version: AssetVersion, user: User) -> Asset:
    if version.asset_id != asset.id:
        raise WorkArtifactError("revision_not_found", "Revision does not belong to artifact.")
    asset.metadata_json = {
        **(asset.metadata_json or {}),
        "canonical_asset_version_id": str(version.id),
    }
    asset.save(update_fields=["metadata_json", "updated_at"])
    record_audit_log(
        actor=user,
        tenant_id=str(asset.organization_id),
        action="work_artifact.canonical_revision_updated",
        resource_type="work_artifact",
        resource_id=str(asset.id),
        metadata={"canonical_asset_version_id": str(version.id)},
    )
    return asset


def canonical_version(asset: Asset) -> AssetVersion | None:
    canonical_id = (asset.metadata_json or {}).get("canonical_asset_version_id")
    if not canonical_id:
        return None
    return AssetVersion.objects.filter(asset=asset, id=canonical_id).first()


def latest_version(asset: Asset) -> AssetVersion | None:
    return AssetVersion.objects.filter(asset=asset).order_by("-version_number").first()


def artifact_payload(asset: Asset, *, include_versions: bool = False) -> dict[str, Any]:
    canonical = canonical_version(asset)
    payload: dict[str, Any] = {
        "id": str(asset.id),
        "company_id": str(asset.company_id),
        "title": asset.title,
        "artifact_type": (asset.metadata_json or {}).get("artifact_type") or asset.asset_type,
        "program_id": (asset.metadata_json or {}).get("program_id"),
        "status": asset.status,
        "metadata": asset.metadata_json,
        "canonical_revision_id": str(canonical.id) if canonical else None,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }
    if include_versions:
        payload["revisions"] = [
            revision_payload(version)
            for version in AssetVersion.objects.filter(asset=asset).order_by("version_number")
        ]
    return payload


def revision_payload(version: AssetVersion) -> dict[str, Any]:
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    return {
        "id": str(version.id),
        "asset_id": str(version.asset_id),
        "version_number": version.version_number,
        "label": provenance.get("label") or f"v{version.version_number}",
        "content_uri": version.content_uri,
        "content_hash": version.content_hash,
        "mime_type": version.mime_type,
        "metadata": provenance.get("metadata")
        if isinstance(provenance.get("metadata"), dict)
        else {},
        "created_at": version.created_at.isoformat(),
    }


def lineage_payload(asset: Asset) -> dict[str, Any]:
    dependencies = AssetDependency.objects.filter(company=asset.company).filter(
        source_asset=asset
    ) | AssetDependency.objects.filter(company=asset.company).filter(target_asset=asset)
    return {
        "artifact": artifact_payload(asset, include_versions=True),
        "dependencies": [
            {
                "id": str(dep.id),
                "source_asset_id": str(dep.source_asset_id),
                "source_revision_id": str(dep.source_asset_version_id)
                if dep.source_asset_version_id
                else None,
                "target_asset_id": str(dep.target_asset_id),
                "target_revision_id": str(dep.target_asset_version_id)
                if dep.target_asset_version_id
                else None,
                "dependency_type": dep.dependency_type,
                "reason": dep.reason,
                "metadata": dep.metadata_json,
                "created_at": dep.created_at.isoformat(),
            }
            for dep in dependencies.order_by("created_at")
        ],
    }


def _create_inline_version(
    *,
    asset: Asset,
    content: Any,
    label: str,
    metadata: dict[str, Any] | None = None,
) -> AssetVersion:
    payload_bytes = _canonical_payload(content)
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri="forgegraph://pending/inline",
        content=payload_bytes,
        mime_type=_mime_type_for_value(content),
        provenance={
            "source": "work_artifact",
            "label": label,
            "inline_content": content,
            "metadata": metadata or {},
        },
    )
    content_uri = f"forgegraph://assets/{version.id}/inline"
    if version.content_uri != content_uri:
        version.content_uri = content_uri
        version.save(update_fields=["content_uri"])
    return version


def _next_label(asset: Asset) -> str:
    latest = latest_version(asset)
    if latest is None:
        return "v1"
    return f"v{latest.version_number + 1}"


def _canonical_payload(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _mime_type_for_value(value: Any) -> str:
    if isinstance(value, str):
        return "text/markdown" if value.lstrip().startswith("#") else "text/plain"
    if isinstance(value, (dict, list)):
        return "application/json"
    return "application/octet-stream"


def _safe_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip().lower()).strip("_")
