"""Serializers for company blueprint APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from application.services.company_blueprints import DEFAULT_BLUEPRINT_ID

AUTONOMY_MODES = ("manual", "assisted", "autonomous")
AI_ACCESS_MODES = ("managed", "byok")


class CompanyBlueprintCompileSerializer(serializers.Serializer[Any]):
    company_name = serializers.CharField(max_length=255)
    objective = serializers.CharField(max_length=2000)
    blueprint_id = serializers.CharField(max_length=64, default=DEFAULT_BLUEPRINT_ID)
    services = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )
    regions = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )
    autonomy_mode = serializers.ChoiceField(choices=AUTONOMY_MODES)
    ai_access_mode = serializers.ChoiceField(choices=AI_ACCESS_MODES)
    intelligence_provider = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        default="openai",
    )


class CompanyFromBlueprintSerializer(CompanyBlueprintCompileSerializer):
    launch_first_operation = serializers.BooleanField(default=False, required=False)
    operation_brief = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default="",
    )
    credential_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs.get("ai_access_mode") == "byok" and not attrs.get("credential_id"):
            raise serializers.ValidationError(
                {"credential_id": ["credential_id is required when ai_access_mode is 'byok'."]}
            )
        return attrs
