"""HTTP node run-test integration adapters."""

from __future__ import annotations

import base64
from typing import Any, cast

import requests
from django.core.exceptions import ValidationError
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.credential_state import is_credential_revoked
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.models import APIKey, User


class HttpNodeTestSerializer(serializers.Serializer[Any]):
    method = serializers.ChoiceField(
        choices=["GET", "POST", "PUT", "PATCH", "DELETE"], required=False
    )
    url = serializers.URLField()
    headers = serializers.DictField(child=serializers.CharField(), required=False)
    body = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    credential_id = serializers.CharField(required=False, allow_blank=True)
    account_sid = serializers.CharField(required=False, allow_blank=True)
    timeout_seconds = serializers.IntegerField(required=False, min_value=1, max_value=30)


def _resolve_credential(
    *,
    user: User,
    provider: str,
    credential_id: str,
) -> tuple[str, str]:
    if not credential_id:
        return provider, ""
    if not user.default_organization_id:
        raise ValueError("No default organization found for this user.")

    try:
        credential = APIKey.objects.filter(
            id=credential_id,
            organization_id=user.default_organization_id,
        ).first()
    except (ValidationError, ValueError):
        credential = None
    if credential is None:
        raise ValueError("Credential not found or inaccessible.")
    if is_credential_revoked(credential.token_metadata):
        raise ValueError("Credential has been revoked. Rotate or reconnect it before testing.")

    resolved_provider = str(credential.provider).strip().lower()
    normalized_provider = provider.strip().lower() if provider else ""
    if normalized_provider and normalized_provider != resolved_provider:
        raise ValueError(
            f"Credential provider mismatch. Expected '{normalized_provider}', got '{resolved_provider}'."
        )

    try:
        token = decrypt_api_key(bytes(credential.encrypted_key)).strip()
    except Exception as exc:
        raise ValueError("Failed to decrypt credential.") from exc
    return (resolved_provider if not normalized_provider else normalized_provider, token)


def _inject_auth_header(
    *,
    headers: dict[str, str],
    provider: str,
    token: str,
    account_sid: str,
) -> dict[str, str]:
    if not token:
        return headers
    if any(key.lower() == "authorization" for key in headers):
        return headers

    normalized_provider = provider.strip().lower()
    result = dict(headers)
    if normalized_provider == "telegram":
        return result
    if normalized_provider == "twilio" and account_sid.strip():
        basic = base64.b64encode(f"{account_sid.strip()}:{token}".encode()).decode()
        result["Authorization"] = f"Basic {basic}"
        return result
    result["Authorization"] = f"Bearer {token}"
    return result


class HttpNodeTestView(APIView):
    """Run ad-hoc HTTP node test requests from node configuration dialog."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = HttpNodeTestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        data = serializer.validated_data
        method = str(data.get("method") or "GET").upper()
        url = str(data["url"])
        headers = dict(data.get("headers") or {})
        body = str(data.get("body") or "")
        provider = str(data.get("provider") or "").strip().lower()
        credential_id = str(data.get("credential_id") or "").strip()
        account_sid = str(data.get("account_sid") or "").strip()
        timeout_seconds = int(data.get("timeout_seconds") or 15)

        user = cast(User, request.user)
        try:
            provider, token = _resolve_credential(
                user=user,
                provider=provider,
                credential_id=credential_id,
            )
        except ValueError as exc:
            return error_response(
                code="INVALID_CREDENTIALS",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_headers = _inject_auth_header(
            headers=headers,
            provider=provider,
            token=token,
            account_sid=account_sid,
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers,
                data=body if body else None,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            return error_response(
                code="HTTP_TEST_FAILED",
                message=f"HTTP test request failed: {exc}",
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_headers = dict(response.headers.items())
        content_type = response_headers.get("Content-Type", "")
        parsed_body: Any
        if "application/json" in content_type:
            try:
                parsed_body = response.json()
            except ValueError:
                parsed_body = response.text
        else:
            parsed_body = response.text

        return success_response(
            {
                "status_code": response.status_code,
                "ok": response.ok,
                "headers": response_headers,
                "body": parsed_body,
            }
        )
