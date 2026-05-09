"""Serializers for reusable company inventory APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class InventoryOverviewQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()


class ReservationCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    product_id = serializers.UUIDField(required=False)
    sku = serializers.CharField(required=False, allow_blank=True, max_length=128)
    quantity = serializers.IntegerField(min_value=1, max_value=100, default=1)
    buyer_alias = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        trim_whitespace=True,
    )
    channel = serializers.ChoiceField(
        choices=["manual", "instagram", "whatsapp", "dm", "storefront", "other"],
        default="manual",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        trim_whitespace=True,
    )
    ttl_minutes = serializers.IntegerField(min_value=1, max_value=1440, default=30)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("product_id") and not str(attrs.get("sku") or "").strip():
            raise serializers.ValidationError("product_id or sku is required.")
        return attrs


class ReservationReleaseSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        trim_whitespace=True,
    )


class ReservationExtendSerializer(serializers.Serializer[Any]):
    minutes = serializers.IntegerField(min_value=1, max_value=1440, default=30)


class ReservationOrderShellSerializer(serializers.Serializer[Any]):
    pass


class ReservationExpireDueSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
