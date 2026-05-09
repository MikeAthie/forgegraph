"""Serializers for public storefront APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class StorefrontCheckoutSessionSerializer(serializers.Serializer[Any]):
    product_id = serializers.UUIDField(required=False)
    sku = serializers.CharField(required=False, allow_blank=True, max_length=128)
    quantity = serializers.IntegerField(min_value=1, max_value=10, default=1)
    buyer_alias = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        trim_whitespace=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("product_id") and not str(attrs.get("sku") or "").strip():
            raise serializers.ValidationError("product_id or sku is required.")
        return attrs
