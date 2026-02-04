from __future__ import annotations

from typing import Any

from rest_framework import serializers


class TenantPolicySerializer(serializers.Serializer[Any]):
    http_allowlist = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    http_denylist = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    http_default_deny = serializers.BooleanField(required=False)
    allowed_providers = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    allowed_models = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
