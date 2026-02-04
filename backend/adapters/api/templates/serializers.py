"""
Template API serializers.
"""

from typing import Any

from rest_framework import serializers


class TemplateListSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    category = serializers.CharField(read_only=True, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(), read_only=True)
    estimated_minutes = serializers.IntegerField(read_only=True)
    sample_input = serializers.JSONField(read_only=True)


class TemplateCloneSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False, allow_blank=True)
    credential_id = serializers.UUIDField(required=False, allow_null=True)
