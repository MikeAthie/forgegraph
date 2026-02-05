"""
Template API serializers.
"""

from typing import Any

from rest_framework import serializers


class TemplateListSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    group_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    category = serializers.CharField(read_only=True, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(), read_only=True)
    estimated_minutes = serializers.IntegerField(read_only=True)
    sample_input = serializers.JSONField(read_only=True)
    guide_steps = serializers.ListField(child=serializers.CharField(), read_only=True)
    version = serializers.IntegerField(read_only=True)
    changelog = serializers.CharField(read_only=True, allow_blank=True)
    is_latest = serializers.BooleanField(read_only=True)
    visibility = serializers.CharField(read_only=True)
    owner_organization_id = serializers.UUIDField(read_only=True, allow_null=True)
    rating_average = serializers.FloatField(read_only=True, allow_null=True)
    rating_count = serializers.IntegerField(read_only=True)
    usage_count = serializers.IntegerField(read_only=True)


class TemplateCloneSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False, allow_blank=True)
    credential_id = serializers.UUIDField(required=False, allow_null=True)


class TemplateVersionCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    estimated_minutes = serializers.IntegerField(required=False)
    graph_json = serializers.JSONField(required=False)
    sample_input = serializers.JSONField(required=False)
    guide_steps = serializers.ListField(child=serializers.CharField(), required=False)
    changelog = serializers.CharField(required=False, allow_blank=True)
    visibility = serializers.CharField(required=False, allow_blank=True)


class TemplateRatingSerializer(serializers.Serializer[Any]):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True)


class TemplateShareSerializer(serializers.Serializer[Any]):
    organization_id = serializers.UUIDField()
