"""
Approvals API serializers.

Clean Architecture: Interface Adapters layer.
"""

from typing import Any

from rest_framework import serializers


class ApprovalTaskSerializer(serializers.Serializer[Any]):
    """Serializer for approval task output."""

    id = serializers.UUIDField(read_only=True)
    run_id = serializers.UUIDField(read_only=True)
    run_name = serializers.CharField(read_only=True)
    graph_name = serializers.CharField(read_only=True)
    node_id = serializers.CharField(read_only=True)
    node_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    payload = serializers.JSONField(read_only=True)
    result = serializers.JSONField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    resolved_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ApprovalTaskListSerializer(serializers.Serializer[Any]):
    """Serializer for approval task list output (minimal fields)."""

    id = serializers.UUIDField(read_only=True)
    run_id = serializers.UUIDField(read_only=True)
    run_name = serializers.CharField(read_only=True)
    graph_name = serializers.CharField(read_only=True)
    node_id = serializers.CharField(read_only=True)
    node_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    prompt_message = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ApprovalResolveSerializer(serializers.Serializer[Any]):
    approved = serializers.BooleanField(required=False, default=True)
    result = serializers.JSONField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True)
