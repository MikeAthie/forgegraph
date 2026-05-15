"""Serializers for routing policy and inbox APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class RoutingPolicyQuerySerializer(serializers.Serializer[Any]):
    department_id = serializers.UUIDField(required=False)
    company_id = serializers.UUIDField(required=False)
    active = serializers.BooleanField(required=False)


class RoutingPolicyCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField()
    trigger_type = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    event_type = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    service_type = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    channel = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    signal_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    entry_conditions = serializers.JSONField(required=False, default=dict)
    priority_rules = serializers.JSONField(required=False, default=dict)
    sla = serializers.JSONField(required=False, default=dict)
    required_approval_types = serializers.ListField(
        child=serializers.CharField(max_length=80),
        required=False,
        default=list,
    )
    fallback_department_id = serializers.UUIDField(required=False, allow_null=True)
    active = serializers.BooleanField(required=False, default=True)
    metadata = serializers.JSONField(required=False, default=dict)


class RoutingPolicyPatchSerializer(RoutingPolicyCreateSerializer):
    department_id = serializers.UUIDField(required=False)
    active = serializers.BooleanField(required=False)


class RoutingInboxQuerySerializer(serializers.Serializer[Any]):
    department_id = serializers.UUIDField(required=False)
    company_id = serializers.UUIDField(required=False)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class RoutingRecordPatchSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[
            "queued",
            "assigned",
            "claimed",
            "in_progress",
            "blocked",
            "completed",
            "cancelled",
        ]
    )
    assigned_user_id = serializers.UUIDField(required=False, allow_null=True)
    resolution = serializers.JSONField(required=False, default=dict)
