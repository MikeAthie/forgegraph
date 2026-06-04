"""Backend-owned gateway media normalization and sanitized evidence."""

from __future__ import annotations

import hashlib
from typing import Any

from django.db import transaction

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.redaction import redact_text
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    GatewayConnection,
    GatewayInboundReceipt,
    GatewayMediaArtifact,
    MemoryObservation,
    Organization,
    ToolExecution,
)

_SENSITIVE_ATTACHMENT_KEYS = {
    "url",
    "download_url",
    "media_url",
    "signed_url",
    "token",
    "authorization",
    "secret",
    "password",
    "raw",
    "payload",
}


def normalize_gateway_attachments(
    *,
    organization: Organization,
    platform: str,
    provider: str,
    direction: str,
    attachments: list[dict[str, Any]],
    connection: GatewayConnection | None = None,
    inbound_receipt: GatewayInboundReceipt | None = None,
    tool_execution: ToolExecution | None = None,
) -> list[GatewayMediaArtifact]:
    artifacts: list[GatewayMediaArtifact] = []
    with transaction.atomic():
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            artifacts.append(
                GatewayMediaArtifact.objects.create(
                    organization=organization,
                    connection=connection,
                    inbound_receipt=inbound_receipt,
                    tool_execution=tool_execution,
                    asset=_resolve_asset(attachment.get("asset_id")),
                    asset_version=_resolve_asset_version(attachment.get("asset_version_id")),
                    platform=platform[:64],
                    provider=provider[:64],
                    direction="outbound" if direction == "outbound" else "inbound",
                    media_kind=_media_kind(attachment),
                    content_type=_content_type(attachment),
                    size_bytes=_size_bytes(attachment),
                    source_id_hash=_source_hash(attachment),
                    content_sha256=_content_hash(attachment),
                    filename_hint=_filename_hint(attachment),
                    storage_ref=_storage_ref(attachment),
                    external_media_id=_external_media_id(attachment),
                    metadata_json=_safe_attachment_metadata(attachment),
                )
            )
    return artifacts


def link_media_transcript(
    artifact: GatewayMediaArtifact,
    observation: MemoryObservation,
) -> GatewayMediaArtifact:
    artifact.transcript_observation = observation
    artifact.save(update_fields=["transcript_observation"])
    return artifact


def media_artifact_payload(artifact: GatewayMediaArtifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "organization_id": str(artifact.organization_id),
        "connection_id": str(artifact.connection_id) if artifact.connection_id else None,
        "inbound_receipt_id": (
            str(artifact.inbound_receipt_id) if artifact.inbound_receipt_id else None
        ),
        "tool_execution_id": str(artifact.tool_execution_id) if artifact.tool_execution_id else None,
        "asset_id": str(artifact.asset_id) if artifact.asset_id else None,
        "asset_version_id": str(artifact.asset_version_id) if artifact.asset_version_id else None,
        "transcript_observation_id": (
            str(artifact.transcript_observation_id)
            if artifact.transcript_observation_id
            else None
        ),
        "platform": artifact.platform,
        "provider": artifact.provider,
        "direction": artifact.direction,
        "media_kind": artifact.media_kind,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "source_id_hash": artifact.source_id_hash,
        "content_sha256": artifact.content_sha256,
        "filename_hint": artifact.filename_hint,
        "storage_ref": artifact.storage_ref,
        "external_media_id": artifact.external_media_id,
        "metadata": sanitize_outbox_payload(artifact.metadata_json or {}),
        "created_at": artifact.created_at.isoformat(),
    }


def media_ids(artifacts: list[GatewayMediaArtifact]) -> list[str]:
    return [str(artifact.id) for artifact in artifacts]


def attachment_refs_for_receipt(artifacts: list[GatewayMediaArtifact]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(artifact.id),
            "media_kind": artifact.media_kind,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "source_id_hash": artifact.source_id_hash,
            "content_sha256": artifact.content_sha256,
        }
        for artifact in artifacts
    ]


def _resolve_asset(value: Any) -> Asset | None:
    if not value:
        return None
    try:
        return Asset.objects.filter(id=value).first()
    except (TypeError, ValueError):
        return None


def _resolve_asset_version(value: Any) -> AssetVersion | None:
    if not value:
        return None
    try:
        return AssetVersion.objects.filter(id=value).first()
    except (TypeError, ValueError):
        return None


def _media_kind(attachment: dict[str, Any]) -> str:
    value = (
        attachment.get("media_kind")
        or attachment.get("kind")
        or attachment.get("type")
        or attachment.get("mime_type")
        or ""
    )
    text = str(value or "").lower()
    if "/" in text:
        text = text.split("/", 1)[0]
    if text not in {"image", "video", "audio", "file", "document", "text"}:
        text = "file" if text else ""
    return text[:32]


def _content_type(attachment: dict[str, Any]) -> str:
    return str(
        attachment.get("content_type")
        or attachment.get("mime_type")
        or attachment.get("mimetype")
        or ""
    ).strip()[:128]


def _size_bytes(attachment: dict[str, Any]) -> int | None:
    raw = attachment.get("size_bytes") or attachment.get("size") or attachment.get("file_size")
    if raw in (None, ""):
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


def _source_hash(attachment: dict[str, Any]) -> str:
    source = (
        attachment.get("id")
        or attachment.get("media_id")
        or attachment.get("file_id")
        or attachment.get("url")
        or attachment.get("download_url")
        or attachment.get("media_url")
        or ""
    )
    return _hash(str(source or "")) if source else ""


def _content_hash(attachment: dict[str, Any]) -> str:
    value = attachment.get("sha256") or attachment.get("content_sha256") or ""
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        return text[:96]
    if len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text):
        return f"sha256:{text.lower()}"
    return ""


def _filename_hint(attachment: dict[str, Any]) -> str:
    value = attachment.get("filename") or attachment.get("name") or attachment.get("title") or ""
    return redact_text(str(value or "").strip())[:255]


def _storage_ref(attachment: dict[str, Any]) -> str:
    value = (
        attachment.get("storage_ref")
        or attachment.get("asset_id")
        or attachment.get("asset_version_id")
        or ""
    )
    return str(value or "").strip()[:255]


def _external_media_id(attachment: dict[str, Any]) -> str:
    value = attachment.get("id") or attachment.get("media_id") or attachment.get("file_id") or ""
    return redact_text(str(value or "").strip())[:255]


def _safe_attachment_metadata(attachment: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in attachment.items():
        key_text = str(key)[:80]
        if key_text.lower() in _SENSITIVE_ATTACHMENT_KEYS:
            metadata[f"{key_text}_hash"] = _hash(str(value or "")) if value else ""
            metadata[f"{key_text}_configured"] = bool(value)
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            metadata[key_text] = redact_text(str(value))[:500] if isinstance(value, str) else value
    return sanitize_outbox_payload(metadata)


def _hash(value: str) -> str:
    if not value:
        return ""
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
