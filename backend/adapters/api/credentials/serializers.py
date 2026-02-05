from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from application.services.oauth import SUPPORTED_OAUTH_PROVIDERS
from infrastructure.orm.models import APIKey

OAUTH_PROVIDER_SET = set(SUPPORTED_OAUTH_PROVIDERS)


class APIKeySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    provider = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    key_hint = serializers.CharField(read_only=True)
    token_expires_at = serializers.DateTimeField(read_only=True)
    health_status = serializers.SerializerMethodField()
    requires_reauth = serializers.SerializerMethodField()
    health_message = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def _health_payload(self, obj: APIKey) -> dict[str, Any]:
        if obj.provider not in OAUTH_PROVIDER_SET:
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


class CredentialOAuthProviderConfigSerializer(serializers.Serializer[Any]):
    client_id = serializers.CharField(max_length=255)
    client_secret = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    authorize_url = serializers.URLField(required=False, allow_blank=True)
    token_url = serializers.URLField(required=False, allow_blank=True)
    redirect_uri = serializers.URLField(required=False, allow_blank=True)
    scopes = serializers.ListField(child=serializers.CharField(), required=False)
    authorize_extra_params = serializers.JSONField(required=False)
    token_extra_params = serializers.JSONField(required=False)
    enabled = serializers.BooleanField(required=False)

    def validate_authorize_extra_params(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("authorize_extra_params must be an object.")
        return value

    def validate_token_extra_params(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("token_extra_params must be an object.")
        return value
