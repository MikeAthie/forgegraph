"""Serializers for portfolio and company-assignment APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from infrastructure.orm.models import CompanyAssignment


class CrossCompanyQueueQuerySerializer(serializers.Serializer[Any]):
    type = serializers.ChoiceField(
        required=False,
        default="all",
        choices=[
            "all",
            "reviews",
            "approvals",
            "metric_gaps",
            "credentials",
            "tasks",
        ],
    )


class CompanyAssignmentQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)


class CompanyAssignmentCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    user_id = serializers.UUIDField(required=False)
    email = serializers.EmailField(required=False)
    role = serializers.ChoiceField(choices=CompanyAssignment.ROLE_CHOICES, default="viewer")
    status = serializers.ChoiceField(choices=CompanyAssignment.STATUS_CHOICES, default="active")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("user_id") and not attrs.get("email"):
            raise serializers.ValidationError("Either user_id or email is required.")
        return attrs


class CompanyAssignmentPatchSerializer(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=CompanyAssignment.ROLE_CHOICES, required=False)
    status = serializers.ChoiceField(choices=CompanyAssignment.STATUS_CHOICES, required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
