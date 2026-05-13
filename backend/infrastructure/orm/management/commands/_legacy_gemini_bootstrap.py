"""Legacy Glasswear Gemini BYOK bootstrap helper for management commands."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Q

from application.services.llm_access import LLMAccessConfig, llm_access_storage_payload
from application.services.provider_credentials import (
    ProviderCredentialImportError,
    import_provider_credential,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    DEFAULT_GEMINI_MODEL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
    _graph_checksum,
)
from infrastructure.orm.models import APIKey, Graph, GraphVersion, OrganizationMembership, User

LEGACY_GEMINI_ENV = "GEMINI_LEGACY"
LEGACY_GEMINI_CREDENTIAL_NAME = "Legacy Gemini BYOK"


class LegacyGeminiBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyGeminiCredentialResult:
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


def import_legacy_gemini_credential(
    *,
    email: str = DEFAULT_EMAIL,
    api_key: str | None = None,
    env_var: str = LEGACY_GEMINI_ENV,
) -> LegacyGeminiCredentialResult:
    raw_key = (api_key if api_key is not None else os.environ.get(env_var, "")).strip()
    if not raw_key:
        raise LegacyGeminiBootstrapError(f"{env_var} is required to import the Legacy Gemini key.")

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
                "Legacy user must have exactly one organization membership before Phase 1."
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
                "Legacy user must see exactly one company before Phase 1."
            )

        try:
            credential, credential_result = import_provider_credential(
                provider="google",
                organization=organization,
                user=user,
                name=LEGACY_GEMINI_CREDENTIAL_NAME,
                api_key=raw_key,
                env_var=env_var,
                purpose="legacy_gemini_phase_1",
            )
        except ProviderCredentialImportError as exc:
            raise LegacyGeminiBootstrapError(str(exc)) from exc
        created_credential = credential_result.created_credential

        graph_version, created_graph_version = _ensure_graph_uses_gemini_credential(
            graph=graph,
            credential=credential,
        )
        if created_credential:
            warnings.append("Imported Legacy Gemini credential.")
        else:
            warnings.append("Rotated existing Legacy Gemini credential from environment.")
        if created_graph_version:
            warnings.append(
                f"Created graph version {graph_version.version} with Gemini BYOK credential metadata."
            )

    return LegacyGeminiCredentialResult(
        user_id=str(user.id),
        organization_id=str(organization.id),
        company_id=str(graph.id),
        graph_version_id=str(graph_version.id),
        credential_id=str(credential.id),
        provider="google",
        key_present=True,
        created_credential=created_credential,
        created_graph_version=created_graph_version,
        warnings=warnings,
    )


def _ensure_graph_uses_gemini_credential(
    *,
    graph: Graph,
    credential: APIKey,
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
    _apply_gemini_metadata(metadata, credential)
    graph_json["metadata"] = metadata

    _apply_gemini_node_credentials(graph_json, credential)

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


def _apply_gemini_metadata(metadata: dict[str, Any], credential: APIKey) -> None:
    metadata["llm_access"] = llm_access_storage_payload(
        LLMAccessConfig(
            llm_mode="byok",
            provider="google",
            credential_id=str(credential.id),
        )
    )
    profile = metadata.get("company_profile")
    if isinstance(profile, dict):
        profile["aiAccessMode"] = "byok"
        profile["intelligenceProvider"] = "google"
        profile["intelligenceModel"] = DEFAULT_GEMINI_MODEL
        profile["byokCredentialId"] = str(credential.id)
        profile["companyStatus"] = "Phase 1 Gemini BYOK credential imported"
    legacy = metadata.get("legacy_glasswear")
    if isinstance(legacy, dict):
        legacy["phase"] = "phase-1-gemini-byok-media-proof"
        legacy["gemini_credential_id"] = str(credential.id)
    metadata["phase_1_gemini_byok"] = {
        "provider": "google",
        "text_model": DEFAULT_GEMINI_MODEL,
        "credential_id": str(credential.id),
        "api_key_present": True,
        "durable_secret_owner": "backend_api_key_store",
    }


def _apply_gemini_node_credentials(graph_json: dict[str, Any], credential: APIKey) -> None:
    for node in graph_json.get("nodes", []):
        if not isinstance(node, dict):
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        if str(config.get("provider") or "").strip().lower() == "google":
            config["credential_id"] = str(credential.id)
            config.setdefault("model", DEFAULT_GEMINI_MODEL)


def safe_json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
