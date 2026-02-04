from __future__ import annotations

from typing import Any

from rest_framework import serializers

from infrastructure.orm.models import APIKey


class APIKeySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    provider = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    key_hint = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class APIKeyCreateSerializer(serializers.Serializer[Any]):
    provider = serializers.ChoiceField(choices=APIKey.PROVIDER_CHOICES)
    name = serializers.CharField(max_length=100)
    api_key = serializers.CharField(write_only=True, trim_whitespace=True)

    def validate_api_key(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("api_key cannot be empty")
        return value
