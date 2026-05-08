"""Generic encrypted provider credential import helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import APIKey, Organization, User


class ProviderCredentialImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderCredentialImportResult:
    user_id: str
    organization_id: str
    credential_id: str
    provider: str
    key_present: bool
    created_credential: bool
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "credential_id": self.credential_id,
            "provider": self.provider,
            "key_present": self.key_present,
            "created_credential": self.created_credential,
            "warnings": self.warnings,
        }


def import_provider_credential(
    *,
    organization: Organization,
    user: User,
    provider: str,
    name: str,
    api_key: str | None = None,
    env_var: str = "",
    purpose: str = "",
    token_metadata: dict[str, Any] | None = None,
) -> tuple[APIKey, ProviderCredentialImportResult]:
    raw_key = (api_key if api_key is not None else os.environ.get(env_var, "")).strip()
    if not raw_key:
        source = env_var or "api_key"
        raise ProviderCredentialImportError(f"{source} is required to import the provider key.")

    selected_provider = provider.strip().lower()
    metadata = {
        "provider": selected_provider,
        "source_env": env_var,
        "purpose": purpose,
        "imported_at": timezone.now().isoformat(),
        "revoked": False,
        **(token_metadata or {}),
    }

    with transaction.atomic():
        credential, created = APIKey.objects.update_or_create(
            organization=organization,
            provider=selected_provider,
            name=name.strip()[:255],
            defaults={
                "user": user,
                "encrypted_key": encrypt_api_key(raw_key),
                "token_metadata": metadata,
            },
        )

    result = ProviderCredentialImportResult(
        user_id=str(user.id),
        organization_id=str(organization.id),
        credential_id=str(credential.id),
        provider=selected_provider,
        key_present=True,
        created_credential=created,
        warnings=[
            f"Imported {selected_provider} credential."
            if created
            else f"Rotated existing {selected_provider} credential."
        ],
    )
    return credential, result
