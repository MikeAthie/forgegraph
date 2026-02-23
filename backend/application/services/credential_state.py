from __future__ import annotations

from typing import Any

from django.utils import timezone

OAUTH_PROVIDER_SET = {
    "gmail",
    "google_calendar",
    "google_tasks",
    "notion",
    "slack",
    "jira",
    "linear",
    "hubspot",
    "google_drive",
}


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


def is_oauth_provider(provider: str) -> bool:
    return provider.strip().lower() in OAUTH_PROVIDER_SET


def is_oauth_credential(
    *,
    provider: str,
    raw_metadata: Any,
    has_refresh_token: bool = False,
    has_token_expiry: bool = False,
) -> bool:
    normalized_provider = provider.strip().lower()
    if normalized_provider not in OAUTH_PROVIDER_SET:
        return False

    metadata = normalize_token_metadata(raw_metadata)
    metadata_provider = str(metadata.get("provider") or "").strip().lower()
    if metadata_provider == normalized_provider:
        return True

    if has_refresh_token or has_token_expiry:
        return True

    scope = metadata.get("scope")
    if isinstance(scope, str) and scope.strip():
        return True

    token_type = metadata.get("token_type")
    if isinstance(token_type, str) and token_type.strip():
        return True

    return False
