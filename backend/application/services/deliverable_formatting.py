"""Backend-owned orchestration for formatting deliverables into derived artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any

from application.services.company_archive import ArchiveService
from application.services.deliverable_format_profiles import (
    FormatProfile,
    load_format_profile_registry,
)
from application.services.deliverable_format_quality import (
    QualityGateResult,
    evaluate_render_quality,
)
from application.services.deliverable_format_renderers import (
    FormatRenderContext,
    FormatSource,
    RenderedArtifact,
    render_manifest_json,
    render_markdown_report,
    render_pdf_report,
    render_zip_package,
)
from infrastructure.orm.models import Asset, AssetVersion, ServiceDeliverable

DEFERRED_FORMATS = ("pdf_report", "email_handoff")


class DeliverableFormattingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class FormatDeliverablesRequest:
    request_id: str
    company: Any
    source_deliverables: list[ServiceDeliverable] | tuple[ServiceDeliverable, ...]
    requested_formats: tuple[str, ...] = ("markdown_report", "manifest", "zip_package")
    engagement: Any | None = None
    program: Any | None = None
    program_stage_state: Any | None = None
    profile_ref: str | None = None
    requested_by: Any | None = None
    idempotency_key: str = ""
    dry_run: bool = False


@dataclass(frozen=True)
class FormattedDeliverablesResult:
    request_id: str
    profile: FormatProfile
    artifacts: tuple[RenderedArtifact, ...]
    quality_result: QualityGateResult
    persisted: bool
    deferred_formats: tuple[str, ...] = DEFERRED_FORMATS

    def artifact_by_format(self, format_id: str) -> RenderedArtifact:
        for artifact in self.artifacts:
            if artifact.format == format_id:
                return artifact
        raise DeliverableFormattingError(
            "artifact_not_found",
            f"Formatted artifact not found: {format_id}",
        )


def format_service_deliverables(request: FormatDeliverablesRequest) -> FormattedDeliverablesResult:
    registry = load_format_profile_registry()
    profile = registry.resolve(
        profile_ref=request.profile_ref,
        engagement=request.engagement,
        program=request.program,
        company=request.company,
    )
    requested_formats = _requested_formats(request, profile)
    sources = tuple(_source_from_deliverable(deliverable) for deliverable in request.source_deliverables)
    context = FormatRenderContext(
        request_id=request.request_id,
        profile=profile,
        sources=sources,
        idempotency_key=request.idempotency_key,
    )

    rendered: list[RenderedArtifact] = []
    persisted = not request.dry_run

    report = render_markdown_report(context)
    quality_result = evaluate_render_quality(
        profile=profile,
        rendered_text=report.text,
        sections=report.sections,
        source_metadata=[source.metadata for source in sources],
    )
    if quality_result.status != "passed":
        raise DeliverableFormattingError(
            "quality_blocked",
            "Formatted deliverable failed blocking quality gates.",
        )

    report = _with_quality(report, quality_result)
    if "markdown_report" in requested_formats:
        report = _persist_artifact(request=request, profile=profile, artifact=report) if persisted else report
        rendered.append(report)

    if "pdf_report" in requested_formats:
        pdf = render_pdf_report(context, markdown_report=report, quality_result=quality_result)
        pdf = _persist_artifact(request=request, profile=profile, artifact=pdf) if persisted else pdf
        rendered.append(pdf)

    if "manifest" in requested_formats:
        manifest = render_manifest_json(context, outputs=tuple(rendered), quality_result=quality_result)
        manifest = _persist_artifact(request=request, profile=profile, artifact=manifest) if persisted else manifest
        rendered.append(manifest)

    if "zip_package" in requested_formats:
        package = render_zip_package(context, outputs=tuple(rendered), quality_result=quality_result)
        package = _persist_artifact(request=request, profile=profile, artifact=package) if persisted else package
        rendered.append(package)

    return FormattedDeliverablesResult(
        request_id=request.request_id,
        profile=profile,
        artifacts=tuple(rendered),
        quality_result=quality_result,
        persisted=persisted,
        deferred_formats=_deferred_formats(profile=profile, artifacts=tuple(rendered)),
    )


def _requested_formats(
    request: FormatDeliverablesRequest,
    profile: FormatProfile,
) -> tuple[str, ...]:
    requested = request.requested_formats or profile.formats
    unsupported = tuple(format_id for format_id in requested if format_id not in profile.formats)
    if unsupported:
        raise DeliverableFormattingError(
            "unsupported_format",
            f"Requested format is not enabled by the selected profile: {unsupported[0]}",
        )
    return tuple(requested)


def _source_from_deliverable(deliverable: ServiceDeliverable) -> FormatSource:
    metadata = dict(deliverable.metadata_json or {})
    version = _asset_version_for_deliverable(deliverable, metadata)
    content = _inline_content(version, fallback=deliverable.summary)
    return FormatSource(
        service_deliverable_id=str(deliverable.id),
        asset_version_id=str(version.id) if version else "",
        title=deliverable.title,
        source_role=_source_role(deliverable, metadata),
        content=content,
        content_hash=_source_hash(version, content),
        metadata=metadata,
    )


def _deferred_formats(
    *,
    profile: FormatProfile,
    artifacts: tuple[RenderedArtifact, ...],
) -> tuple[str, ...]:
    produced = {artifact.format for artifact in artifacts}
    deferred: list[str] = []
    if "pdf_report" in profile.formats and "pdf_report" not in produced:
        deferred.append("pdf_report")
    deferred.append("email_handoff")
    return tuple(deferred)


def _asset_version_for_deliverable(
    deliverable: ServiceDeliverable,
    metadata: dict[str, Any],
) -> AssetVersion | None:
    if deliverable.artifact_id is None:
        return None
    version_id = str(metadata.get("asset_version_id") or "").strip()
    if version_id:
        version = AssetVersion.objects.filter(id=version_id, asset=deliverable.artifact).first()
        if version is not None:
            return version
    return AssetVersion.objects.filter(asset=deliverable.artifact).order_by("-version_number").first()


def _inline_content(version: AssetVersion | None, *, fallback: str) -> str:
    if version is None:
        return fallback
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    inline = provenance.get("inline_content")
    if isinstance(inline, str):
        return inline
    if inline is not None:
        return json.dumps(inline, sort_keys=True, default=str)
    encoded = provenance.get("inline_content_base64")
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return fallback
    return fallback


def _source_hash(version: AssetVersion | None, content: str) -> str:
    if version is not None and version.content_hash:
        return version.content_hash
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _source_role(deliverable: ServiceDeliverable, metadata: dict[str, Any]) -> str:
    formatting = metadata.get("formatting")
    if isinstance(formatting, dict) and str(formatting.get("source_role") or "").strip():
        return str(formatting["source_role"]).strip()
    return str(metadata.get("source_role") or deliverable.deliverable_type or "source").strip()


def _with_quality(
    artifact: RenderedArtifact,
    quality_result: QualityGateResult,
) -> RenderedArtifact:
    provenance = dict(artifact.provenance)
    provenance["quality"] = {
        "gate_result_id": quality_result.gate_result_id,
        "status": quality_result.status,
    }
    return replace(artifact, provenance=provenance)


def _persist_artifact(
    *,
    request: FormatDeliverablesRequest,
    profile: FormatProfile,
    artifact: RenderedArtifact,
) -> RenderedArtifact:
    archive = ArchiveService()
    source_key = _asset_source_key(request=request, profile=profile, artifact=artifact)
    asset = archive.create_asset(
        company=request.company,
        title=artifact.filename,
        asset_type="deliverable",
        source_key=source_key,
        created_by_type="user" if request.requested_by is not None else "system",
        created_by_id=getattr(request.requested_by, "id", None),
        metadata=_asset_metadata(request=request, profile=profile, artifact=artifact),
    )
    _sync_asset_metadata(asset, request=request, profile=profile, artifact=artifact)

    provenance = _version_provenance(artifact)
    version = archive.create_asset_version(
        asset=asset,
        content_uri=f"forgegraph://deliverable-formatting/{artifact.format}/{source_key}",
        content=artifact.content_bytes,
        mime_type=artifact.mime_type,
        provenance=provenance,
    )
    final_provenance = _provenance_with_output_ids(
        artifact.provenance,
        asset_id=str(asset.id),
        asset_version_id=str(version.id),
    )
    stored_provenance = {
        **provenance,
        "render_provenance": final_provenance,
    }
    if version.provenance_json != stored_provenance:
        version.provenance_json = stored_provenance
        version.save(update_fields=["provenance_json"])
    inline_uri = f"forgegraph://assets/{version.id}/inline"
    if version.content_uri != inline_uri:
        version.content_uri = inline_uri
        version.save(update_fields=["content_uri"])

    return replace(
        artifact,
        asset_id=str(asset.id),
        asset_version_id=str(version.id),
        provenance=final_provenance,
    )


def _asset_source_key(
    *,
    request: FormatDeliverablesRequest,
    profile: FormatProfile,
    artifact: RenderedArtifact,
) -> str:
    material = {
        "request": request.idempotency_key or request.request_id,
        "profile_ref": profile.profile_ref,
        "format": artifact.format,
        "source_hashes": artifact.provenance["sources"]["source_hashes"],
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    key_base = _safe_key(request.idempotency_key or request.request_id)
    return f"deliverable_formatting:{key_base}:{artifact.format}:{digest}"[:512]


def _asset_metadata(
    *,
    request: FormatDeliverablesRequest,
    profile: FormatProfile,
    artifact: RenderedArtifact,
) -> dict[str, Any]:
    return {
        "source": "deliverable_formatting",
        "request_id": request.request_id,
        "format": artifact.format,
        "profile_ref": profile.profile_ref,
        "profile_sha256": profile.profile_sha256,
        "derived": True,
    }


def _sync_asset_metadata(
    asset: Asset,
    *,
    request: FormatDeliverablesRequest,
    profile: FormatProfile,
    artifact: RenderedArtifact,
) -> None:
    expected = _asset_metadata(request=request, profile=profile, artifact=artifact)
    changed: list[str] = []
    if asset.title != artifact.filename:
        asset.title = artifact.filename
        changed.append("title")
    if asset.metadata_json != expected:
        asset.metadata_json = expected
        changed.append("metadata_json")
    if asset.status != "active":
        asset.status = "active"
        changed.append("status")
    if changed:
        asset.save(update_fields=[*changed, "updated_at"])


def _version_provenance(artifact: RenderedArtifact) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "source": "deliverable_formatting",
        "format": artifact.format,
        "filename": artifact.filename,
        "render_provenance": artifact.provenance,
    }
    if artifact.text:
        provenance["inline_content"] = artifact.text
    else:
        provenance["inline_content_base64"] = base64.b64encode(artifact.content_bytes).decode("ascii")
    return provenance


def _provenance_with_output_ids(
    provenance: dict[str, Any],
    *,
    asset_id: str,
    asset_version_id: str,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(provenance, sort_keys=True, default=str))
    output = dict(updated.get("output") or {})
    output["asset_id"] = asset_id
    output["asset_version_id"] = asset_version_id
    updated["output"] = output
    return updated


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip()).strip("_") or "request"
