from __future__ import annotations

from typing import Any

from rest_framework import serializers


class AuditLogSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    tenant_id = serializers.UUIDField(read_only=True)
    actor_email = serializers.EmailField(read_only=True, allow_null=True)
    action = serializers.CharField(read_only=True)
    resource_type = serializers.CharField(read_only=True)
    resource_id = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
