from __future__ import annotations

from datetime import datetime, timedelta
import logging
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.credential_state import is_credential_revoked, is_oauth_provider
from application.services.oauth import (
    exchange_refresh_token_for_access_token,
    get_oauth_provider_config,
)
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import decrypt_api_key, encrypt_api_key
from infrastructure.orm.models import APIKey
from infrastructure.security import s2s

logger = logging.getLogger(__name__)
_REFRESH_SKEW = timedelta(minutes=5)


def _parse_expires_at(token_payload: dict[str, object]) -> datetime | None:
    raw_expires_in = token_payload.get("expires_in")
    if raw_expires_in is None:
        return None
    try:
        expires_in = int(raw_expires_in)
        if expires_in > 0:
            return timezone.now() + timedelta(seconds=expires_in)
    except (TypeError, ValueError):
        return None
    return None


def _refresh_oauth_access_token_if_needed(key: APIKey, tenant_id: str) -> APIKey:
    if not is_oauth_provider(key.provider):
        return key
    if key.encrypted_refresh_token is None:
        return key
    if key.token_expires_at is None:
        return key
    if key.token_expires_at > timezone.now() + _REFRESH_SKEW:
        return key

    with transaction.atomic():
        locked = APIKey.objects.select_for_update().get(id=key.id)
        if locked.encrypted_refresh_token is None:
            return locked
        if locked.token_expires_at is None:
            return locked
        if locked.token_expires_at > timezone.now() + _REFRESH_SKEW:
            return locked

        refresh_token = decrypt_api_key(bytes(locked.encrypted_refresh_token)).strip()
        if not refresh_token:
            return locked

        config, missing_fields = get_oauth_provider_config(tenant_id, locked.provider)
        if config is None:
            raise ValueError(
                f"OAuth provider '{locked.provider}' is not configured ({', '.join(missing_fields)})."
            )

        refreshed = exchange_refresh_token_for_access_token(
            config,
            refresh_token=refresh_token,
        )
        new_access_token = str(refreshed.get("access_token") or "").strip()
        if not new_access_token:
            raise ValueError("OAuth refresh did not return an access_token.")

        update_fields = ["encrypted_key", "token_expires_at", "token_metadata"]
        locked.encrypted_key = encrypt_api_key(new_access_token)
        locked.token_expires_at = _parse_expires_at(refreshed)

        rotated_refresh_token = str(refreshed.get("refresh_token") or "").strip()
        if rotated_refresh_token:
            locked.encrypted_refresh_token = encrypt_api_key(rotated_refresh_token)
            update_fields.append("encrypted_refresh_token")

        metadata = dict(locked.token_metadata) if isinstance(locked.token_metadata, dict) else {}
        metadata["provider"] = locked.provider
        token_type = str(refreshed.get("token_type") or "").strip()
        if token_type:
            metadata["token_type"] = token_type
        scope = refreshed.get("scope")
        if isinstance(scope, str) and scope.strip():
            metadata["scope"] = scope.strip()
        locked.token_metadata = metadata
        locked.save(update_fields=sorted(set(update_fields)))
        return locked


class EngineCredentialDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, credential_id: UUID) -> Response:
        timestamp_header = request.headers.get("X-Forgegraph-Timestamp", "")
        signature_header = request.headers.get("X-Forgegraph-Signature", "")
        ok, reason = s2s.verify_request(
            timestamp_ms=timestamp_header,
            signature=signature_header,
            body=request.body or b"",
        )
        if not ok:
            return Response({"detail": "Unauthorized", "reason": reason}, status=401)

        tenant_id = request.query_params.get("tenant_id", "")
        if not tenant_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="tenant_id is required",
                status=400,
            )

        try:
            key = APIKey.objects.select_related("user", "organization").get(id=credential_id)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        owner_tenant_id = get_tenant_id_for_user(key.user)
        if key.organization_id and str(key.organization_id) != tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Credential does not belong to tenant",
                status=403,
            )
        if not key.organization_id and owner_tenant_id != tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Credential does not belong to tenant",
                status=403,
            )
        if is_credential_revoked(key.token_metadata):
            return error_response(
                code="CREDENTIAL_REVOKED",
                message="Credential has been revoked. Rotate or reconnect it before use.",
                status=410,
            )

        try:
            key = _refresh_oauth_access_token_if_needed(key, tenant_id)
            api_key = decrypt_api_key(bytes(key.encrypted_key))
        except ValueError as exc:
            logger.warning(
                "oauth_credential_refresh_failed",
                extra={
                    "credential_id": str(key.id),
                    "provider": key.provider,
                    "tenant_id": tenant_id,
                    "error": str(exc),
                },
            )
            return error_response(
                code="CREDENTIAL_REFRESH_FAILED",
                message=(
                    "OAuth access token refresh failed. Reconnect this credential in the Credentials page."
                ),
                status=401,
            )
        except Exception:
            return error_response(
                code="DECRYPTION_ERROR",
                message="Failed to decrypt credential",
                status=500,
            )

        return success_response(
            {
                "credential_id": str(key.id),
                "provider": key.provider,
                "api_key": api_key,
            }
        )
