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
    CredentialOAuthProviderConfigSerializer,
    CredentialOAuthStartSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.oauth import (
    PROVIDER_DEFAULTS,
    build_oauth_authorize_url,
    exchange_code_for_tokens,
    get_oauth_provider_config,
    get_oauth_provider_status,
)
from application.services.oidc import sign_state, verify_state
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import APIKey, IntegrationOAuthProviderConfig, User


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

        tenant_id = get_tenant_id_for_user(user)
        for item in get_oauth_provider_status(tenant_id):
            if item["provider"] == provider:
                return success_response(item)
        return error_response(
            code="NOT_FOUND",
            message=f"OAuth provider '{provider}' is not supported.",
            status=404,
        )

    def put(self, request: Request, provider: str) -> Response:
        user = cast(User, request.user)
        denied = _ensure_credential_admin(user)
        if denied:
            return denied

        if provider not in PROVIDER_DEFAULTS:
            return error_response(
                code="NOT_FOUND",
                message=f"OAuth provider '{provider}' is not supported.",
                status=404,
            )

        serializer = CredentialOAuthProviderConfigSerializer(data=request.data)
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

        tenant_id = get_tenant_id_for_user(user)
        data = serializer.validated_data
        existing = IntegrationOAuthProviderConfig.objects.filter(
            tenant_id=tenant_id,
            provider=provider,
        ).first()
        if existing is None and not data.get("client_secret"):
            return error_response(
                code="VALIDATION_ERROR",
                message="client_secret is required when creating OAuth provider config.",
                status=400,
            )

        defaults = PROVIDER_DEFAULTS[provider]
        scopes = (
            [str(item).strip() for item in data["scopes"] if str(item).strip()]
            if "scopes" in data
            else (existing.scopes if existing else [str(item) for item in defaults["scopes"]])
        )

        update_defaults: dict[str, object] = {
            "client_id": data.get("client_id", existing.client_id if existing else ""),
            "authorize_url": data.get(
                "authorize_url",
                existing.authorize_url if existing else str(defaults["authorize_url"]),
            ),
            "token_url": data.get(
                "token_url",
                existing.token_url if existing else str(defaults["token_url"]),
            ),
            "redirect_uri": data.get(
                "redirect_uri",
                existing.redirect_uri if existing else "",
            ),
            "scopes": scopes,
            "authorize_extra_params": data.get(
                "authorize_extra_params",
                existing.authorize_extra_params if existing else defaults["authorize_extra_params"],
            ),
            "token_extra_params": data.get(
                "token_extra_params",
                existing.token_extra_params if existing else defaults["token_extra_params"],
            ),
            "enabled": data.get("enabled", existing.enabled if existing else True),
        }
        if data.get("client_secret"):
            update_defaults["encrypted_client_secret"] = encrypt_api_key(str(data["client_secret"]))
        elif existing:
            update_defaults["encrypted_client_secret"] = existing.encrypted_client_secret

        IntegrationOAuthProviderConfig.objects.update_or_create(
            tenant_id=tenant_id,
            provider=provider,
            defaults=update_defaults,
        )

        record_audit_log(
            actor=user,
            tenant_id=tenant_id,
            action="credential.oauth_provider_updated",
            resource_type="oauth_provider_config",
            resource_id=provider,
            metadata={"provider": provider},
        )

        for item in get_oauth_provider_status(tenant_id):
            if item["provider"] == provider:
                return success_response(item)
        return error_response(
            code="INTERNAL_ERROR",
            message="Failed to load saved OAuth provider configuration.",
            status=500,
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
