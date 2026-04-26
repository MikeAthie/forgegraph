"""LLM access-mode helpers for run dispatch.

The backend owns durable LLM access metadata. Raw BYOK credentials are only
materialized into the engine dispatch input and must not be stored as run input.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError

from application.services.credential_state import is_credential_revoked
from infrastructure.crypto.encryption import EncryptionError, decrypt_api_key
from infrastructure.orm.models import APIKey, User

LLM_ACCESS_METADATA_KEY = "llm_access"
LLM_ACCESS_ENGINE_INPUT_KEY = "_forgegraph_llm_access"

LLM_MODE_MANAGED = "managed"
LLM_MODE_BYOK = "byok"
DEFAULT_LLM_PROVIDER = "openai"

_LLM_MODES = {LLM_MODE_MANAGED, LLM_MODE_BYOK}


class LLMAccessValidationError(ValueError):
    """Raised when an LLM access payload cannot be used safely."""

    def __init__(self, details: list[dict[str, str]]) -> None:
        super().__init__("LLM access configuration is invalid.")
        self.details = details


@dataclass(frozen=True)
class LLMAccessConfig:
    llm_mode: str = LLM_MODE_MANAGED
    provider: str = DEFAULT_LLM_PROVIDER
    credential_id: str = ""
    api_key: str = ""

    @property
    def is_byok(self) -> bool:
        return self.llm_mode == LLM_MODE_BYOK


def allowed_llm_providers() -> set[str]:
    providers = getattr(settings, "ALLOWED_LLM_PROVIDERS", [DEFAULT_LLM_PROVIDER, "anthropic"])
    return {str(provider).strip().lower() for provider in providers if str(provider).strip()}


def llm_access_from_request(payload: dict[str, Any]) -> LLMAccessConfig:
    """Validate and normalize top-level run request LLM access fields."""

    mode = str(payload.get("llm_mode") or LLM_MODE_MANAGED).strip().lower()
    provider = str(payload.get("provider") or DEFAULT_LLM_PROVIDER).strip().lower()
    credential_id = str(payload.get("credential_id") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    if mode == LLM_MODE_BYOK and api_key:
        raise LLMAccessValidationError(
            [
                {
                    "field": "api_key",
                    "message": "Raw API keys are not accepted on run requests. Store the key as an organization credential and pass credential_id.",
                }
            ]
        )
    return validate_llm_access_config(
        LLMAccessConfig(
            llm_mode=mode,
            provider=provider,
            credential_id=credential_id,
            api_key=api_key,
        )
    )


def validate_llm_access_config(config: LLMAccessConfig) -> LLMAccessConfig:
    errors: list[dict[str, str]] = []

    mode = str(config.llm_mode or LLM_MODE_MANAGED).strip().lower()
    if mode not in _LLM_MODES:
        errors.append(
            {
                "field": "llm_mode",
                "message": "llm_mode must be either 'managed' or 'byok'.",
            }
        )
        mode = LLM_MODE_MANAGED

    provider = str(config.provider or DEFAULT_LLM_PROVIDER).strip().lower()
    if not provider:
        provider = DEFAULT_LLM_PROVIDER

    allowed = allowed_llm_providers()
    if allowed and provider not in allowed:
        errors.append(
            {
                "field": "provider",
                "message": f"Provider '{provider}' is not supported.",
            }
        )

    credential_id = str(config.credential_id or "").strip()
    api_key = str(config.api_key or "").strip()
    if mode == LLM_MODE_BYOK:
        if not credential_id:
            errors.append(
                {
                    "field": "credential_id",
                    "message": "credential_id is required when llm_mode is 'byok'.",
                }
            )
        if api_key and not _looks_like_api_key(api_key):
            errors.append(
                {
                    "field": "api_key",
                    "message": "api_key is malformed.",
                }
            )
    else:
        credential_id = ""
        api_key = ""

    if errors:
        raise LLMAccessValidationError(errors)

    return LLMAccessConfig(
        llm_mode=mode,
        provider=provider,
        credential_id=credential_id,
        api_key=api_key,
    )


def managed_llm_access(provider: str = DEFAULT_LLM_PROVIDER) -> LLMAccessConfig:
    return validate_llm_access_config(
        LLMAccessConfig(
            llm_mode=LLM_MODE_MANAGED,
            provider=provider,
            credential_id="",
            api_key="",
        )
    )


def resolve_llm_access_for_dispatch(
    config: LLMAccessConfig,
    user: User,
) -> LLMAccessConfig:
    """Resolve run-level access into the transient dispatch credential payload."""

    config = validate_llm_access_config(config)
    if not config.is_byok:
        return config

    if user.default_organization_id is None:
        raise LLMAccessValidationError(
            [
                {
                    "field": "credential_id",
                    "message": "User has no organization for BYOK credentials.",
                }
            ]
        )

    try:
        credential = APIKey.objects.get(
            id=config.credential_id,
            organization=user.default_organization,
        )
    except (APIKey.DoesNotExist, ValueError, DjangoValidationError) as exc:
        raise LLMAccessValidationError(
            [
                {
                    "field": "credential_id",
                    "message": "BYOK credential was not found or is not accessible.",
                }
            ]
        ) from exc

    credential_provider = str(credential.provider or "").strip().lower()
    if config.provider and credential_provider and config.provider != credential_provider:
        raise LLMAccessValidationError(
            [
                {
                    "field": "credential_id",
                    "message": "BYOK credential provider does not match the requested provider.",
                }
            ]
        )

    if is_credential_revoked(credential.token_metadata):
        raise LLMAccessValidationError(
            [
                {
                    "field": "credential_id",
                    "message": "BYOK credential has been revoked. Rotate or reconnect it before use.",
                }
            ]
        )

    try:
        api_key = decrypt_api_key(bytes(credential.encrypted_key))
    except EncryptionError as exc:
        raise LLMAccessValidationError(
            [{"field": "credential_id", "message": "BYOK credential cannot be decrypted."}]
        ) from exc

    return validate_llm_access_config(
        LLMAccessConfig(
            llm_mode=LLM_MODE_BYOK,
            provider=credential_provider or config.provider,
            credential_id=str(credential.id),
            api_key=api_key,
        )
    )


def attach_llm_access_to_graph(
    graph_json: dict[str, Any],
    config: LLMAccessConfig,
) -> dict[str, Any]:
    """Attach durable, sanitized access metadata to a prepared graph."""

    prepared = copy.deepcopy(graph_json) if isinstance(graph_json, dict) else {}
    metadata_raw = prepared.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    metadata[LLM_ACCESS_METADATA_KEY] = llm_access_storage_payload(config)
    prepared["metadata"] = metadata
    return prepared


def llm_access_storage_payload(config: LLMAccessConfig) -> dict[str, Any]:
    config = validate_llm_access_config(config)
    payload: dict[str, Any] = {
        "llm_mode": config.llm_mode,
        "provider": config.provider,
        "api_key_present": config.is_byok,
    }
    if config.is_byok:
        payload["credential_id"] = config.credential_id
    return payload


def public_llm_access_from_graph(graph_json: dict[str, Any] | None) -> dict[str, Any]:
    metadata = graph_json.get("metadata") if isinstance(graph_json, dict) else {}
    access = metadata.get(LLM_ACCESS_METADATA_KEY) if isinstance(metadata, dict) else {}
    if not isinstance(access, dict):
        return {
            "llm_mode": LLM_MODE_MANAGED,
            "provider": DEFAULT_LLM_PROVIDER,
            "api_key_present": False,
        }
    mode = str(access.get("llm_mode") or LLM_MODE_MANAGED).strip().lower()
    provider = str(access.get("provider") or DEFAULT_LLM_PROVIDER).strip().lower()
    return {
        "llm_mode": mode if mode in _LLM_MODES else LLM_MODE_MANAGED,
        "provider": provider or DEFAULT_LLM_PROVIDER,
        "api_key_present": bool(access.get("api_key_present")),
        "credential_id": (
            str(access.get("credential_id") or "") if access.get("credential_id") else None
        ),
    }


def engine_llm_access_payload(config: LLMAccessConfig) -> dict[str, Any]:
    config = validate_llm_access_config(config)
    payload: dict[str, Any] = {
        "llm_mode": config.llm_mode,
        "provider": config.provider,
    }
    if config.is_byok:
        payload["credential_id"] = config.credential_id
        payload["api_key"] = config.api_key
    return payload


def engine_llm_access_from_graph(
    graph_json: dict[str, Any] | None,
    user: User,
) -> LLMAccessConfig:
    """Recover engine dispatch credentials from backend-owned graph metadata."""

    metadata = graph_json.get("metadata") if isinstance(graph_json, dict) else {}
    access = metadata.get(LLM_ACCESS_METADATA_KEY) if isinstance(metadata, dict) else {}
    if not isinstance(access, dict):
        return managed_llm_access()

    mode = str(access.get("llm_mode") or LLM_MODE_MANAGED).strip().lower()
    provider = str(access.get("provider") or DEFAULT_LLM_PROVIDER).strip().lower()
    if mode != LLM_MODE_BYOK:
        return managed_llm_access(provider=provider)

    credential_id = str(access.get("credential_id") or "").strip()
    if not credential_id:
        raise LLMAccessValidationError(
            [
                {
                    "field": "credential_id",
                    "message": "Stored BYOK credential reference is unavailable.",
                }
            ]
        )

    return resolve_llm_access_for_dispatch(
        LLMAccessConfig(
            llm_mode=LLM_MODE_BYOK,
            provider=provider,
            credential_id=credential_id,
        ),
        user,
    )


def engine_input_with_llm_access(
    input_json: dict[str, Any] | None,
    config: LLMAccessConfig,
) -> dict[str, Any]:
    """Attach raw BYOK credentials to the transient engine input only."""

    payload = copy.deepcopy(input_json) if isinstance(input_json, dict) else {}
    config = validate_llm_access_config(config)
    if not config.is_byok:
        payload.pop(LLM_ACCESS_ENGINE_INPUT_KEY, None)
        return payload
    payload[LLM_ACCESS_ENGINE_INPUT_KEY] = engine_llm_access_payload(config)
    return payload


def _looks_like_api_key(value: str) -> bool:
    if len(value) < 8:
        return False
    return not any(character.isspace() or ord(character) < 32 for character in value)
