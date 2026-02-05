from __future__ import annotations

from typing import Any

from rest_framework import serializers


class OIDCProviderSerializer(serializers.Serializer[Any]):
    issuer_url = serializers.URLField()
    client_id = serializers.CharField(max_length=255)
    client_secret = serializers.CharField(max_length=255, required=False, allow_blank=False)
    audience = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email_domains = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    default_role = serializers.ChoiceField(choices=["owner", "admin", "member", "viewer"])
    enabled = serializers.BooleanField(required=False)
