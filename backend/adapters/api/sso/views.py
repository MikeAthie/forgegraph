from __future__ import annotations

import secrets
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from adapters.api.auth.views import _set_refresh_cookie
from adapters.api.responses import error_response
from application.services.audit_log import record_audit_log
from application.services.oidc import (
    build_authorize_url,
    exchange_code_for_tokens,
    sign_state,
    verify_id_token,
    verify_state,
)
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import OIDCProvider, Organization, OrganizationMembership, User

from .serializers import OIDCProviderSerializer

UserModel = get_user_model()


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip("@")


def _resolve_provider_by_email(email: str) -> OIDCProvider | None:
    domain = email.split("@")[-1].lower()
    providers = list(OIDCProvider.objects.filter(enabled=True))
    for provider in providers:
        allowed = [_normalize_domain(item) for item in provider.email_domains or []]
        if not allowed:
            continue
        if domain in allowed:
            return provider
    if len(providers) == 1 and not providers[0].email_domains:
        return providers[0]
    return None


def _ensure_admin(user: User) -> Response | None:
    if not (getattr(user, "is_staff", False) or has_min_role(user, "admin")):
        return error_response(
            code="FORBIDDEN",
            message="You don't have permission to manage SSO settings in this organization.",
            status=403,
        )
    return None


def _get_frontend_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _get_sso_callback_url() -> str:
    return f"{_get_frontend_url()}/sso/callback"


def _provider_status_payload(provider: OIDCProvider | None) -> dict[str, str]:
    if provider is None:
        return {
            "state": "unavailable",
            "message": "No SSO provider is configured for this organization yet.",
        }

    missing_fields: list[str] = []
    if not provider.issuer_url:
        missing_fields.append("issuer_url")
    if not provider.client_id:
        missing_fields.append("client_id")
    if not provider.encrypted_client_secret:
        missing_fields.append("client_secret")

    if missing_fields:
        return {
            "state": "partial",
            "message": f"SSO configuration is incomplete. Missing: {', '.join(missing_fields)}.",
        }

    if not provider.enabled:
        return {
            "state": "partial",
            "message": "SSO configuration exists, but sign-in is currently disabled for this organization.",
        }

    return {
        "state": "configured",
        "message": "SSO is configured and enabled for this organization.",
    }


class OIDCProviderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        tenant_id = get_tenant_id_for_user(user)
        provider = OIDCProvider.objects.filter(tenant_id=tenant_id).first()
        if not provider:
            return Response(
                {
                    "issuer_url": "",
                    "client_id": "",
                    "audience": "",
                    "email_domains": [],
                    "default_role": "member",
                    "enabled": False,
                    "status": _provider_status_payload(None),
                }
            )

        return Response(
            {
                "issuer_url": provider.issuer_url,
                "client_id": provider.client_id,
                "audience": provider.audience,
                "email_domains": provider.email_domains,
                "default_role": provider.default_role,
                "enabled": provider.enabled,
                "status": _provider_status_payload(provider),
            }
        )

    def put(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        serializer = OIDCProviderSerializer(data=request.data)
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
        existing = OIDCProvider.objects.filter(tenant_id=tenant_id).first()

        defaults: dict[str, Any] = {
            "issuer_url": data["issuer_url"].rstrip("/"),
            "client_id": data["client_id"].strip(),
            "audience": data.get("audience", ""),
            "email_domains": [_normalize_domain(item) for item in data.get("email_domains", [])],
            "default_role": data.get("default_role", "member"),
            "enabled": data.get("enabled", True),
        }

        client_secret = data.get("client_secret")
        if client_secret:
            defaults["encrypted_client_secret"] = encrypt_api_key(client_secret)
        elif not existing:
            return error_response(
                code="VALIDATION_ERROR",
                message="client_secret is required when creating a provider",
                status=400,
            )

        provider, _ = OIDCProvider.objects.update_or_create(
            tenant_id=tenant_id,
            defaults=defaults,
        )

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="sso.provider_updated",
            resource_type="oidc_provider",
            resource_id=str(provider.id),
            metadata={"provider": provider.provider},
        )

        return Response(
            {
                "issuer_url": provider.issuer_url,
                "client_id": provider.client_id,
                "audience": provider.audience,
                "email_domains": provider.email_domains,
                "default_role": provider.default_role,
                "enabled": provider.enabled,
                "status": _provider_status_payload(provider),
            }
        )


class Auth0LoginView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        email = request.query_params.get("email", "").strip().lower()
        if not email:
            return error_response(
                code="VALIDATION_ERROR",
                message="email is required for SSO",
                status=400,
            )

        provider = _resolve_provider_by_email(email)
        if not provider:
            return error_response(
                code="NOT_FOUND",
                message="No SSO provider configured for this email domain.",
                status=404,
            )

        nonce = secrets.token_urlsafe(16)
        state_payload = {"tenant_id": str(provider.tenant_id), "nonce": nonce, "email": email}
        state = sign_state(state_payload)

        authorize_url = build_authorize_url(
            provider,
            redirect_uri=_get_sso_callback_url(),
            state=state,
            nonce=nonce,
            login_hint=email,
        )

        return Response({"authorize_url": authorize_url})


class Auth0CallbackView(APIView):
    permission_classes = [AllowAny]

    def _verified_state(self, state: str) -> dict[str, Any] | Response:
        try:
            state_payload = verify_state(state)
        except ValueError as exc:
            return error_response(
                code="INVALID_SSO_STATE",
                message=str(exc),
                status=400,
            )

        tenant_id = state_payload.get("tenant_id")
        nonce = state_payload.get("nonce")
        if not tenant_id or not nonce:
            return error_response(
                code="INVALID_SSO_STATE",
                message="state is missing required fields",
                status=400,
            )
        return state_payload

    def _provider_for_state(self, tenant_id: str) -> OIDCProvider | Response:
        provider = OIDCProvider.objects.filter(tenant_id=tenant_id, enabled=True).first()
        if not provider:
            return error_response(
                code="NOT_FOUND",
                message="SSO provider not configured for this tenant.",
                status=404,
            )
        return provider

    def _claims_for_code(
        self,
        *,
        provider: OIDCProvider,
        code: object,
        nonce: object,
    ) -> dict[str, Any] | Response:
        try:
            tokens = exchange_code_for_tokens(
                provider, code=str(code), redirect_uri=_get_sso_callback_url()
            )
            id_token = tokens.get("id_token")
            if not id_token:
                raise ValueError("id_token missing in token response")
            claims = verify_id_token(provider, id_token=id_token, nonce=str(nonce))
        except Exception as exc:
            return error_response(
                code="SSO_FAILED",
                message=f"SSO login failed: {exc}",
                status=400,
            )
        return claims

    def _active_user_for_claims(self, claims: dict[str, Any]) -> tuple[Any, str] | Response:
        email = (claims.get("email") or claims.get("preferred_username") or "").lower()
        if not email:
            return error_response(
                code="SSO_FAILED",
                message="SSO login failed: email claim missing",
                status=400,
            )

        user = UserModel.objects.filter(email=email).first()
        if not user:
            user = UserModel(email=email)
            user.set_unusable_password()
            user.first_name = claims.get("given_name", "")
            user.last_name = claims.get("family_name", "")
            user.save()

        if not user.is_active:
            return error_response(
                code="USER_DISABLED",
                message="Your account has been disabled. Contact an administrator.",
                status=403,
            )
        return user, email

    def post(self, request: Request) -> Response:
        code = request.data.get("code")
        state = request.data.get("state")
        if not code or not state:
            return error_response(
                code="VALIDATION_ERROR",
                message="code and state are required",
                status=400,
            )
        code = str(code)
        state = str(state)

        state_payload = self._verified_state(state)
        if isinstance(state_payload, Response):
            return state_payload

        tenant_id = str(state_payload.get("tenant_id") or "")
        nonce = str(state_payload.get("nonce") or "")
        provider = self._provider_for_state(tenant_id)
        if isinstance(provider, Response):
            return provider

        claims = self._claims_for_code(provider=provider, code=code, nonce=nonce)
        if isinstance(claims, Response):
            return claims

        user_response = self._active_user_for_claims(claims)
        if isinstance(user_response, Response):
            return user_response
        user, email = user_response

        organization = Organization.objects.filter(id=tenant_id).first()
        if not organization:
            return error_response(
                code="NOT_FOUND",
                message="Organization not found.",
                status=404,
            )

        membership, created = OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=user,
            defaults={"role": provider.default_role, "is_default": True},
        )
        if created and not user.default_organization_id:
            user.default_organization = organization
            user.save(update_fields=["default_organization"])

        refresh = RefreshToken.for_user(user)
        response = Response({"access": str(refresh.access_token)})
        _set_refresh_cookie(response, str(refresh))
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="sso.login",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"provider": provider.provider, "email": email},
        )

        return response
