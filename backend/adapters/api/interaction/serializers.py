"""Serializers for the interaction layer API."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class CurrentBriefQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)


class InteractionEventCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    brief_id = serializers.UUIDField(required=False, allow_null=True)
    input = serializers.CharField(max_length=8000, trim_whitespace=True)

    def validate_input(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("input cannot be blank")
        return normalized
