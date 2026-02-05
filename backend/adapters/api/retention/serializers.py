from __future__ import annotations

from typing import Any

from rest_framework import serializers


class TenantRetentionPolicySerializer(serializers.Serializer[Any]):
    runs_retention_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    run_logs_retention_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    audit_logs_retention_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    usage_retention_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
