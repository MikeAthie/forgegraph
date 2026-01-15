"""
Runs API serializers (stub for Phase 4).

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import serializers


class RunStartSerializer(serializers.Serializer):
    """Serializer for starting a run."""

    graph_version_id = serializers.UUIDField()
    input_json = serializers.JSONField(required=False, default=dict)


class RunResumeSerializer(serializers.Serializer):
    """Serializer for resuming a run."""

    node_id = serializers.CharField()
    input_json = serializers.JSONField(required=False, default=dict)


class RunListSerializer(serializers.Serializer):
    """Serializer for run list output."""

    id = serializers.UUIDField(read_only=True)
    graph_version_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)


class RunDetailSerializer(serializers.Serializer):
    """Serializer for run detail output."""

    id = serializers.UUIDField(read_only=True)
    owner_id = serializers.UUIDField(read_only=True)
    graph_version_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    input_json = serializers.JSONField(read_only=True)
    output_json = serializers.JSONField(read_only=True, allow_null=True)
    error_message = serializers.CharField(read_only=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)


class NodeRunSerializer(serializers.Serializer):
    """Serializer for node run output."""

    id = serializers.UUIDField(read_only=True)
    node_id = serializers.CharField(read_only=True)
    node_type = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    attempt = serializers.IntegerField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_ms = serializers.IntegerField(read_only=True, allow_null=True)
    input_json = serializers.JSONField(read_only=True)
    output_json = serializers.JSONField(read_only=True, allow_null=True)
    error_json = serializers.JSONField(read_only=True, allow_null=True)
