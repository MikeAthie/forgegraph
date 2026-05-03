from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from application.services.scim import hash_scim_token
from infrastructure.orm.models import SCIMToken


@dataclass
class SCIMServiceUser:
    tenant_id: str

    @property
    def pk(self) -> str:
        return f"scim:{self.tenant_id}"

    @property
    def id(self) -> str:
        return self.pk

    @property
    def is_authenticated(self) -> bool:
        return True


class ScimTokenAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SCIMServiceUser, SCIMToken] | None:
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None

        raw_token = auth.split(" ", 1)[1].strip()
        if not raw_token:
            raise AuthenticationFailed("Missing SCIM token")

        token_hash = hash_scim_token(raw_token)
        token = SCIMToken.objects.filter(token_hash=token_hash).first()
        if not token:
            raise AuthenticationFailed("Invalid SCIM token")

        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])

        cast(Any, request).scim_tenant_id = str(token.tenant_id)
        return SCIMServiceUser(str(token.tenant_id)), token
