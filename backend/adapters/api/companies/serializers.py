"""Company API serializers backed by transitional Graph storage."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


def _validate_model_json_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise serializers.ValidationError("model_json must be an object")

    if "nodes" not in value:
        raise serializers.ValidationError("model_json must contain 'nodes'")

    if "edges" not in value:
        raise serializers.ValidationError("model_json must contain 'edges'")

    if not isinstance(value.get("nodes"), list):
        raise serializers.ValidationError("'nodes' must be an array")

    if not isinstance(value.get("edges"), list):
        raise serializers.ValidationError("'edges' must be an array")

    if "metadata" in value and not isinstance(value.get("metadata"), dict):
        raise serializers.ValidationError("'metadata' must be an object")

    if "editor_state" in value and not isinstance(value.get("editor_state"), dict):
        raise serializers.ValidationError("'editor_state' must be an object")

    return value


class CompanyCreateSerializer(serializers.Serializer[Any]):
    """Serializer for creating a company alias row."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)


class CompanyUpdateSerializer(serializers.Serializer[Any]):
    """Serializer for updating company alias metadata."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class CompanySerializer(serializers.Serializer[Any]):
    """Company-facing DTO for the transitional Graph storage row."""

    id = serializers.UUIDField(read_only=True)
    company_id = serializers.UUIDField(read_only=True)
    workflow_definition_id = serializers.UUIDField(read_only=True)
    storage_model = serializers.CharField(read_only=True)
    organization_id = serializers.UUIDField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    setup_version_count = serializers.IntegerField(read_only=True)
    latest_setup_version = serializers.IntegerField(read_only=True, allow_null=True)


class CompanyOperatingModelVersionCreateSerializer(serializers.Serializer[Any]):
    """Create a saved operating model version for a company."""

    model_json = serializers.JSONField()

    def validate_model_json(self, value: Any) -> dict[str, Any]:
        return _validate_model_json_payload(value)


class CompanyOperatingModelVersionSerializer(serializers.Serializer[Any]):
    """Company-facing DTO for GraphVersion rows."""

    id = serializers.UUIDField(read_only=True)
    company_id = serializers.UUIDField(read_only=True)
    workflow_definition_id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    model_json = serializers.JSONField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
