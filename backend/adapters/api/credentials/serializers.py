from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from application.services.credential_state import (
    is_credential_revoked,
    is_oauth_credential,
    is_oauth_provider,
    normalize_token_metadata,
)
from application.services.oauth import SUPPORTED_OAUTH_PROVIDERS
from infrastructure.orm.models import APIKey


class APIKeySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    provider = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    key_hint = serializers.CharField(read_only=True)
    token_expires_at = serializers.DateTimeField(read_only=True)
    revoked = serializers.SerializerMethodField()
    revoked_at = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()
    requires_reauth = serializers.SerializerMethodField()
    health_message = serializers.SerializerMethodField()
    is_oauth_connection = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def _health_payload(self, obj: APIKey) -> dict[str, Any]:
        metadata = normalize_token_metadata(obj.token_metadata)
        if is_credential_revoked(metadata):
            return {
                "health_status": "revoked",
                "requires_reauth": True,
                "health_message": "Credential was revoked. Rotate or reconnect this credential.",
            }
        if not is_oauth_provider(obj.provider):
            return {"health_status": "healthy", "requires_reauth": False, "health_message": None}

        if obj.token_expires_at is None:
            return {"health_status": "healthy", "requires_reauth": False, "health_message": None}

        now = timezone.now()
        expires_at = obj.token_expires_at

        if expires_at <= now:
            return {
                "health_status": "expired",
                "requires_reauth": True,
                "health_message": "OAuth access token expired. Reconnect this credential.",
            }

        remaining = expires_at - now
        if remaining <= timedelta(hours=24):
            return {
                "health_status": "expiring_soon",
                "requires_reauth": True,
                "health_message": "OAuth access token expires in less than 24 hours.",
            }
        if remaining <= timedelta(days=7):
            return {
                "health_status": "expiring_soon",
                "requires_reauth": False,
                "health_message": "OAuth access token expires within 7 days.",
            }
        return {"health_status": "healthy", "requires_reauth": False, "health_message": None}

    def get_health_status(self, obj: APIKey) -> str:
        return str(self._health_payload(obj)["health_status"])

    def get_requires_reauth(self, obj: APIKey) -> bool:
        return bool(self._health_payload(obj)["requires_reauth"])

    def get_health_message(self, obj: APIKey) -> str | None:
        value = self._health_payload(obj)["health_message"]
        return None if value is None else str(value)

    def get_is_oauth_connection(self, obj: APIKey) -> bool:
        return is_oauth_credential(
            provider=obj.provider,
            raw_metadata=obj.token_metadata,
            has_refresh_token=bool(obj.encrypted_refresh_token),
            has_token_expiry=obj.token_expires_at is not None,
        )

    def get_revoked(self, obj: APIKey) -> bool:
        return is_credential_revoked(obj.token_metadata)

    def get_revoked_at(self, obj: APIKey) -> str | None:
        metadata = normalize_token_metadata(obj.token_metadata)
        value = metadata.get("revoked_at")
        return str(value) if isinstance(value, str) and value else None


class APIKeyCreateSerializer(serializers.Serializer[Any]):
    provider = serializers.ChoiceField(choices=APIKey.PROVIDER_CHOICES)
    name = serializers.CharField(max_length=100)
    api_key = serializers.CharField(write_only=True, trim_whitespace=True)

    def validate_api_key(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("api_key cannot be empty")
        return value


class CredentialOAuthStartSerializer(serializers.Serializer[Any]):
    provider = serializers.ChoiceField(choices=SUPPORTED_OAUTH_PROVIDERS)
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)


class CredentialOAuthCallbackSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    state = serializers.CharField()


class CredentialRotateSerializer(serializers.Serializer[Any]):
    api_key = serializers.CharField(trim_whitespace=True)
    refresh_token = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    expires_in = serializers.IntegerField(required=False, min_value=1)

    def validate_api_key(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("api_key cannot be empty")
        return value


class CredentialRevokeSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
