"""
Prompts API serializers.

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import serializers

from domain.value_objects import PromptCategory


class PromptCreateSerializer(serializers.Serializer):
    """Serializer for creating a prompt."""

    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    category = serializers.ChoiceField(choices=[(c.value, c.value) for c in PromptCategory])
    content = serializers.CharField()
    variables_schema = serializers.JSONField(required=False, default=dict)


class PromptUpdateSerializer(serializers.Serializer):
    """Serializer for updating a prompt."""

    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    content = serializers.CharField(required=False)
    variables_schema = serializers.JSONField(required=False)


class PromptPublishSerializer(serializers.Serializer):
    """Serializer for publishing a prompt."""

    license = serializers.CharField(max_length=64, required=False, default="MIT")


class PromptListSerializer(serializers.Serializer):
    """Serializer for prompt list output."""

    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    visibility = serializers.CharField(read_only=True)
    is_builtin = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class PromptDetailSerializer(serializers.Serializer):
    """Serializer for prompt detail output."""

    id = serializers.UUIDField(read_only=True)
    owner_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    content = serializers.CharField(read_only=True)
    variables_schema = serializers.JSONField(read_only=True)
    version = serializers.CharField(read_only=True)
    license = serializers.CharField(read_only=True)
    visibility = serializers.CharField(read_only=True)
    is_builtin = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
