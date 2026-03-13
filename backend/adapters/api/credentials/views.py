from __future__ import annotations

import secrets
from datetime import timedelta
from typing import cast
from uuid import UUID

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.credentials.serializers import (
    APIKeyCreateSerializer,
    APIKeySerializer,
    CredentialOAuthCallbackSerializer,
    CredentialOAuthStartSerializer,
    CredentialRevokeSerializer,
    CredentialRotateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.credential_state import (
    build_revoked_metadata,
    build_rotated_metadata,
    is_credential_revoked,
)
from application.services.oauth import (
    build_oauth_authorize_url,
    exchange_code_for_tokens,
    get_oauth_provider_config,
    get_oauth_provider_status,
)
from application.services.oidc import sign_state, verify_state
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import APIKey, User


class CredentialsListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        keys = APIKey.objects.filter(organization=organization).order_by("-created_at")
        data = [APIKeySerializer(key).data for key in keys]
        return success_response(data)

    def post(self, request: Request) -> Response:
        serializer = APIKeyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        provider = serializer.validated_data["provider"]
        name = serializer.validated_data["name"]
        api_key = serializer.validated_data["api_key"]

        try:
            key = APIKey.objects.create(
                organization=organization,
                user=user,
                provider=provider,
                name=name,
                encrypted_key=encrypt_api_key(api_key),
            )
        except IntegrityError:
            return error_response(
                code="DUPLICATE_KEY",
                message="A credential with this provider and name already exists",
                status=400,
            )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.created",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={"provider": provider, "name": name},
        )

        return success_response(APIKeySerializer(key).data)


class CredentialsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, credential_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to delete credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        try:
            key = APIKey.objects.get(id=credential_id, organization=organization)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.deleted",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={"provider": key.provider, "name": key.name},
        )

        key.delete()
        return success_response({"deleted": True})


class CredentialRotateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, credential_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to rotate credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )

        serializer = CredentialRotateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        try:
            key = APIKey.objects.get(id=credential_id, organization=user.default_organization)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        validated = serializer.validated_data
        was_revoked = is_credential_revoked(key.token_metadata)
        key.encrypted_key = encrypt_api_key(validated["api_key"])
        update_fields = ["encrypted_key"]

        if "refresh_token" in validated:
            refresh_token = str(validated.get("refresh_token") or "").strip()
            key.encrypted_refresh_token = encrypt_api_key(refresh_token) if refresh_token else None
            update_fields.append("encrypted_refresh_token")

        expires_in = validated.get("expires_in")
        if expires_in is not None:
            key.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            update_fields.append("token_expires_at")

        key.token_metadata = build_rotated_metadata(key.token_metadata)
        update_fields.append("token_metadata")
        key.save(update_fields=sorted(set(update_fields)))

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.rotated",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={
                "provider": key.provider,
                "name": key.name,
                "was_revoked": was_revoked,
            },
        )

        return success_response(APIKeySerializer(key).data)


class CredentialRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, credential_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to revoke credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )

        serializer = CredentialRevokeSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        try:
            key = APIKey.objects.get(id=credential_id, organization=user.default_organization)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        reason = str(serializer.validated_data.get("reason") or "").strip()
        key.encrypted_key = encrypt_api_key(f"revoked:{key.id}:{secrets.token_urlsafe(16)}")
        key.encrypted_refresh_token = None
        key.token_expires_at = timezone.now()
        key.token_metadata = build_revoked_metadata(key.token_metadata, reason=reason)
        key.save(
            update_fields=[
                "encrypted_key",
                "encrypted_refresh_token",
                "token_expires_at",
                "token_metadata",
            ]
        )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.revoked",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={
                "provider": key.provider,
                "name": key.name,
                "reason": reason,
            },
        )

        revoked_at = ""
        if isinstance(key.token_metadata, dict):
            revoked_at = str(key.token_metadata.get("revoked_at") or "")
        return success_response(
            {
                "revoked": True,
                "credential_id": str(key.id),
                "revoked_at": revoked_at,
            }
        )


def _ensure_credential_admin(user: User) -> Response | None:
    if not has_min_role(user, "admin"):
        return error_response(
            code="FORBIDDEN",
            message="You don't have permission to manage credentials in this organization.",
            status=403,
        )
    if not user.default_organization:
        return error_response(
            code="NOT_FOUND",
            message="No default organization found for this user.",
            status=404,
        )
    return None


def _oauth_missing_config_error(provider: str, missing_fields: list[str]) -> Response:
    provider_name = provider.replace("_", " ").title()
    return error_response(
        code="CONFIG_ERROR",
        message=(
            f"{provider_name} OAuth is not configured. Missing configuration fields: "
            f"{', '.join(missing_fields)}."
        ),
        status=503,
        details=[{"field": "config", "issue": name} for name in missing_fields],
    )


def _next_credential_name(*, organization_id: UUID, provider: str, base_name: str) -> str:
    existing = set(
        APIKey.objects.filter(organization_id=organization_id, provider=provider).values_list(
            "name", flat=True
        )
    )
    if base_name not in existing:
        return base_name
    suffix = 2
    while True:
        candidate = f"{base_name}-{suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1


class CredentialOAuthProvidersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied
        return success_response(get_oauth_provider_status(get_tenant_id_for_user(user)))


class CredentialOAuthProviderConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, provider: str) -> Response:
        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied

        provider_name = provider.strip().lower()
        tenant_id = get_tenant_id_for_user(user)
        for item in get_oauth_provider_status(tenant_id):
            if item["provider"] == provider_name:
                return success_response(item)
        return error_response(
            code="NOT_FOUND",
            message=f"OAuth provider '{provider_name}' is not supported.",
            status=404,
        )

    def put(self, request: Request, provider: str) -> Response:
        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied

        provider_name = provider.strip().lower()
        statuses = {
            item["provider"]: item
            for item in get_oauth_provider_status(get_tenant_id_for_user(user))
        }
        if provider_name not in statuses:
            return error_response(
                code="NOT_FOUND",
                message=f"OAuth provider '{provider_name}' is not supported.",
                status=404,
            )
        return error_response(
            code="CONFIG_READ_ONLY",
            message=(
                "OAuth provider configuration is managed at the service level via environment variables. "
                "Update backend env settings and restart the service."
            ),
            status=409,
        )


class CredentialOAuthStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CredentialOAuthStartSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied

        provider = serializer.validated_data["provider"]
        try:
            config, missing_fields = get_oauth_provider_config(
                get_tenant_id_for_user(user), provider
            )
        except ValueError as exc:
            return error_response(code="VALIDATION_ERROR", message=str(exc), status=400)
        if config is None:
            return _oauth_missing_config_error(provider, missing_fields)

        state_payload = {
            "provider": provider,
            "tenant_id": str(user.default_organization_id),
            "user_id": str(user.id),
            "name": serializer.validated_data.get("name") or "",
            "nonce": secrets.token_urlsafe(16),
        }
        state = sign_state(state_payload, salt="credential-oauth")

        authorize_url = build_oauth_authorize_url(config, state=state)
        return success_response(
            {
                "provider": provider,
                "authorize_url": authorize_url,
                "redirect_uri": config.redirect_uri,
            }
        )


class CredentialOAuthCallbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CredentialOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied

        code = serializer.validated_data["code"]
        state = serializer.validated_data["state"]
        try:
            state_payload = verify_state(state, max_age=900, salt="credential-oauth")
        except ValueError as exc:
            return error_response(
                code="INVALID_OAUTH_STATE",
                message=str(exc),
                status=400,
            )

        provider = str(state_payload.get("provider") or "").strip().lower()
        state_user_id = str(state_payload.get("user_id") or "")
        state_tenant_id = str(state_payload.get("tenant_id") or "")
        if (
            not provider
            or state_user_id != str(user.id)
            or state_tenant_id != str(user.default_organization_id)
        ):
            return error_response(
                code="INVALID_OAUTH_STATE",
                message="OAuth state is invalid for this user or organization.",
                status=400,
            )

        try:
            config, missing_fields = get_oauth_provider_config(
                get_tenant_id_for_user(user), provider
            )
        except ValueError as exc:
            return error_response(code="VALIDATION_ERROR", message=str(exc), status=400)
        if config is None:
            return _oauth_missing_config_error(provider, missing_fields)

        try:
            token_response = exchange_code_for_tokens(config, code=code)
        except ValueError as exc:
            return error_response(
                code="OAUTH_EXCHANGE_FAILED",
                message=str(exc),
                status=400,
            )

        access_token = str(token_response.get("access_token") or "").strip()
        if not access_token:
            return error_response(
                code="OAUTH_EXCHANGE_FAILED",
                message="OAuth token exchange did not return an access_token.",
                status=400,
            )
        refresh_token = str(token_response.get("refresh_token") or "").strip()
        raw_expires_in = token_response.get("expires_in")
        expires_at = None
        if raw_expires_in is not None:
            try:
                expires_in = int(raw_expires_in)
                if expires_in > 0:
                    expires_at = timezone.now() + timedelta(seconds=expires_in)
            except (TypeError, ValueError):
                expires_at = None

        base_name = str(state_payload.get("name") or "").strip() or f"{provider}-oauth"
        organization = user.default_organization
        if organization is None:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        credential_name = _next_credential_name(
            organization_id=cast(UUID, user.default_organization_id),
            provider=provider,
            base_name=base_name,
        )

        key = APIKey.objects.create(
            organization=organization,
            user=user,
            provider=provider,
            name=credential_name,
            encrypted_key=encrypt_api_key(access_token),
            encrypted_refresh_token=encrypt_api_key(refresh_token) if refresh_token else None,
            token_expires_at=expires_at,
            token_metadata={
                "scope": token_response.get("scope"),
                "token_type": token_response.get("token_type"),
                "provider": provider,
            },
        )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.oauth_connected",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={"provider": provider, "name": key.name},
        )

        return success_response(APIKeySerializer(key).data, status=201)
