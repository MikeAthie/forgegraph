"""Serializers for company archive APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class AssetListQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    asset_type = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    operation_id = serializers.UUIDField(required=False, allow_null=True)


class EvidenceLinkQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    task_id = serializers.UUIDField(required=False, allow_null=True)
    decision_id = serializers.UUIDField(required=False, allow_null=True)


class MediaGenerationCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    credential_id = serializers.UUIDField()
    modality = serializers.ChoiceField(choices=["image", "video"])
    prompt = serializers.CharField(max_length=4000, trim_whitespace=True)
    idempotency_key = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
        trim_whitespace=True,
    )
    model = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
        trim_whitespace=True,
    )
