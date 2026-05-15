"""Serializers for department registry and membership APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class DepartmentCreateSerializer(serializers.Serializer[Any]):
    slug = serializers.SlugField(max_length=160)
    name = serializers.CharField(max_length=255)
    department_type = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        default="",
    )
    lead_user_id = serializers.UUIDField(required=False, allow_null=True)
    service_tags = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        default=list,
    )
    active = serializers.BooleanField(required=False, default=True)
    metadata = serializers.JSONField(required=False, default=dict)


class DepartmentPatchSerializer(DepartmentCreateSerializer):
    slug = serializers.SlugField(max_length=160, required=False)
    name = serializers.CharField(max_length=255, required=False)
    active = serializers.BooleanField(required=False)


class DepartmentMembershipSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["viewer", "member", "lead"], default="viewer")
    status = serializers.ChoiceField(choices=["active", "inactive"], default="active")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)
