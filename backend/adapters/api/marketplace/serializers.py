"""Marketplace API serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

SEMVER_REGEX = r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"


class MarketplaceInstallSerializer(serializers.Serializer[Any]):
    version = serializers.RegexField(regex=SEMVER_REGEX, required=False)


class MarketplaceReleaseCreateSerializer(serializers.Serializer[Any]):
    package_slug = serializers.SlugField(max_length=100)
    package_name = serializers.CharField(required=False, allow_blank=False, max_length=120)
    package_summary = serializers.CharField(required=False, allow_blank=True)
    package_category = serializers.ChoiceField(
        choices=["communication", "productivity", "crm", "storage", "developer", "other"],
        required=False,
    )
    package_icon = serializers.CharField(required=False, allow_blank=True, max_length=32)
    version = serializers.RegexField(regex=SEMVER_REGEX)
    changelog = serializers.CharField(required=False, allow_blank=True)
    execution_node_type = serializers.ChoiceField(choices=["http", "prompt", "tool", "transform"])
    ui_schema = serializers.JSONField(required=False)
    config_schema = serializers.JSONField(required=False)
    config_defaults = serializers.JSONField(required=False)

    def validate_ui_schema(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("ui_schema must be an object.")
        return value

    def validate_config_schema(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_schema must be an object.")
        return value

    def validate_config_defaults(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_defaults must be an object.")
        return value


class MarketplaceReleaseReviewSerializer(serializers.Serializer[Any]):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
