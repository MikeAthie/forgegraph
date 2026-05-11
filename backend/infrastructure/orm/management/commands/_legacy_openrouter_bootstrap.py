"""Legacy Glasswear OpenRouter BYOK bootstrap helper for management commands."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Q

from application.services.llm_access import LLMAccessConfig, llm_access_storage_payload
from application.services.provider_credentials import (
    ProviderCredentialImportError,
    import_provider_credential,
)
from infrastructure.orm.management.commands._legacy_gemini_bootstrap import (
    LegacyGeminiBootstrapError,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
    _graph_checksum,
)
from infrastructure.orm.models import APIKey, Graph, GraphVersion, OrganizationMembership, User

LEGACY_OPENROUTER_ENV = "OPENROUTER"
LEGACY_OPENROUTER_ENV_FALLBACK = "OPENROUTER_API_KEY"
LEGACY_OPENROUTER_CREDENTIAL_NAME = "Legacy OpenRouter BYOK"
DEFAULT_OPENROUTER_TEXT_MODEL = "google/gemini-2.5-flash"
DEFAULT_OPENROUTER_IMAGE_MODEL = "black-forest-labs/flux.2-klein-4b"


@dataclass(frozen=True)
class LegacyOpenRouterCredentialResult:
    user_id: str
    organization_id: str
    company_id: str
    graph_version_id: str
    credential_id: str
    provider: str
    key_present: bool
    created_credential: bool
    created_graph_version: bool
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "company_id": self.company_id,
            "graph_version_id": self.graph_version_id,
            "credential_id": self.credential_id,
            "provider": self.provider,
            "key_present": self.key_present,
            "created_credential": self.created_credential,
            "created_graph_version": self.created_graph_version,
            "warnings": self.warnings,
        }


def import_legacy_openrouter_credential(
    *,
    email: str = DEFAULT_EMAIL,
    api_key: str | None = None,
    env_var: str = LEGACY_OPENROUTER_ENV,
    fallback_env_var: str = LEGACY_OPENROUTER_ENV_FALLBACK,
    text_model: str = DEFAULT_OPENROUTER_TEXT_MODEL,
    image_model: str = DEFAULT_OPENROUTER_IMAGE_MODEL,
) -> LegacyOpenRouterCredentialResult:
    import os

    selected_env_var = env_var
    raw_key = (api_key if api_key is not None else os.environ.get(env_var, "")).strip()
    if not raw_key and fallback_env_var:
        selected_env_var = fallback_env_var
        raw_key = os.environ.get(fallback_env_var, "").strip()
    if not raw_key:
        raise LegacyGeminiBootstrapError(
            f"{env_var} or {fallback_env_var} is required to import the Legacy OpenRouter key."
        )

    email = email.strip().lower() or DEFAULT_EMAIL
    warnings: list[str] = []

    with transaction.atomic():
        user = User.objects.select_related("default_organization").filter(email=email).first()
        if user is None or user.default_organization_id is None:
            raise LegacyGeminiBootstrapError(
                "Legacy Phase 0 workspace is missing. Run seed_legacy_glasswear_phase0 first."
            )
        memberships = OrganizationMembership.objects.filter(user=user)
        if memberships.count() != 1:
            raise LegacyGeminiBootstrapError(
                "Legacy user must have exactly one organization membership before OpenRouter import."
            )
        organization = user.default_organization
        if organization is None:
            raise LegacyGeminiBootstrapError(
                "Legacy Phase 0 organization is missing. Run seed_legacy_glasswear_phase0 first."
            )
        graph = (
            Graph.objects.filter(
                organization=organization,
                external_source=EXTERNAL_SOURCE,
                external_ref=EXTERNAL_REF,
            )
            .select_related("organization")
            .first()
        )
        if graph is None:
            raise LegacyGeminiBootstrapError(
                "Legacy company graph is missing. Run seed_legacy_glasswear_phase0 first."
            )
        visible_company_count = (
            Graph.objects.filter(
                Q(owner=user) | Q(organization=organization),
                external_source=EXTERNAL_SOURCE,
                external_ref=EXTERNAL_REF,
            )
            .distinct()
            .count()
        )
        if visible_company_count != 1:
            raise LegacyGeminiBootstrapError(
                "Legacy user must see exactly one company before OpenRouter import."
            )

        try:
            credential, credential_result = import_provider_credential(
                provider="openrouter",
                organization=organization,
                user=user,
                name=LEGACY_OPENROUTER_CREDENTIAL_NAME,
                api_key=raw_key,
                env_var=selected_env_var,
                purpose="legacy_openrouter_phase_1",
                token_metadata={
                    "text_model": text_model,
                    "image_model": image_model,
                },
            )
        except ProviderCredentialImportError as exc:
            raise LegacyGeminiBootstrapError(str(exc)) from exc
        created_credential = credential_result.created_credential

        graph_version, created_graph_version = _ensure_graph_uses_openrouter_credential(
            graph=graph,
            credential=credential,
            text_model=text_model,
            image_model=image_model,
        )
        warnings.extend(credential_result.warnings)
        if created_graph_version:
            warnings.append(
                f"Created graph version {graph_version.version} with OpenRouter BYOK credential metadata."
            )

    return LegacyOpenRouterCredentialResult(
        user_id=str(user.id),
        organization_id=str(organization.id),
        company_id=str(graph.id),
        graph_version_id=str(graph_version.id),
        credential_id=str(credential.id),
        provider="openrouter",
        key_present=True,
        created_credential=created_credential,
        created_graph_version=created_graph_version,
        warnings=warnings,
    )


def _ensure_graph_uses_openrouter_credential(
    *,
    graph: Graph,
    credential: APIKey,
    text_model: str,
    image_model: str,
) -> tuple[GraphVersion, bool]:
    latest = graph.versions.order_by("-version").first()
    if latest is None:
        raise LegacyGeminiBootstrapError("Legacy company graph has no graph version.")

    graph_json = copy.deepcopy(latest.graph_json)
    if not isinstance(graph_json, dict):
        raise LegacyGeminiBootstrapError("Legacy graph version JSON is invalid.")

    metadata = graph_json.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["llm_access"] = llm_access_storage_payload(
        LLMAccessConfig(
            llm_mode="byok",
            provider="openrouter",
            credential_id=str(credential.id),
        )
    )
    profile = metadata.get("company_profile")
    if isinstance(profile, dict):
        profile["aiAccessMode"] = "byok"
        profile["intelligenceProvider"] = "openrouter"
        profile["intelligenceModel"] = text_model
        profile["byokCredentialId"] = str(credential.id)
        profile["companyStatus"] = "Phase 1 OpenRouter BYOK credential imported"
    legacy = metadata.get("legacy_glasswear")
    if isinstance(legacy, dict):
        legacy["phase"] = "phase-1-openrouter-media-proof"
        legacy["openrouter_credential_id"] = str(credential.id)
    metadata["phase_1_openrouter_byok"] = {
        "provider": "openrouter",
        "text_model": text_model,
        "image_model": image_model,
        "credential_id": str(credential.id),
        "api_key_present": True,
        "durable_secret_owner": "backend_api_key_store",
    }
    graph_json["metadata"] = metadata

    for node in graph_json.get("nodes", []):
        if not isinstance(node, dict):
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        if str(config.get("provider") or "").strip().lower() in {"", "google", "openrouter"}:
            config["provider"] = "openrouter"
            config["credential_id"] = str(credential.id)
            config["model"] = text_model

    incoming_checksum = _graph_checksum(graph_json)
    if latest.checksum == incoming_checksum:
        return latest, False

    version = GraphVersion.objects.create(
        graph=graph,
        version=latest.version + 1,
        graph_json=graph_json,
    )
    graph.save()
    return version, True
