from __future__ import annotations

from typing import Any

from django.utils import timezone


def normalize_token_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    return {}


def is_credential_revoked(raw_metadata: Any) -> bool:
    metadata = normalize_token_metadata(raw_metadata)
    return bool(metadata.get("revoked") is True)


def build_revoked_metadata(raw_metadata: Any, *, reason: str = "") -> dict[str, Any]:
    metadata = normalize_token_metadata(raw_metadata)
    metadata["revoked"] = True
    metadata["revoked_at"] = timezone.now().isoformat()
    if reason:
        metadata["revocation_reason"] = reason
    return metadata


def build_rotated_metadata(raw_metadata: Any) -> dict[str, Any]:
    metadata = normalize_token_metadata(raw_metadata)
    metadata["rotated_at"] = timezone.now().isoformat()
    metadata.pop("revoked", None)
    metadata.pop("revoked_at", None)
    metadata.pop("revocation_reason", None)
    return metadata
