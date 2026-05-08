"""Serializers for authenticated commerce checkout APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class OperatorCheckoutSessionSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    reservation_id = serializers.UUIDField(required=False)
    order_shell_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if bool(attrs.get("reservation_id")) == bool(attrs.get("order_shell_id")):
            raise serializers.ValidationError(
                "Provide exactly one of reservation_id or order_shell_id."
            )
        return attrs


class CommerceCompanyQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()


class FulfillmentBlockSerializer(serializers.Serializer[Any]):
    reason_code = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class FulfillmentReadySerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class FulfillmentShipSerializer(serializers.Serializer[Any]):
    carrier = serializers.CharField(required=False, allow_blank=True, max_length=120)
    tracking_number = serializers.CharField(required=False, allow_blank=True, max_length=120)
    tracking_url = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class FulfillmentDeliverSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class OperatorNoteSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(max_length=1000, allow_blank=False)
