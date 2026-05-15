"""Serializers for projected task APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from application.services.task_judges import normalize_judge_criteria


class TaskJudgeSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    criteria = serializers.JSONField(required=True)
    pass_threshold = serializers.IntegerField(
        required=False, min_value=1, max_value=100, default=80
    )
    evidence_snapshot = serializers.JSONField(required=False, default=dict)

    def validate_criteria(self, value: Any) -> list[str]:
        criteria = normalize_judge_criteria(value)
        if not criteria:
            raise serializers.ValidationError("At least one judge criterion is required.")
        return criteria


class TaskRouteSerializer(serializers.Serializer[Any]):
    to_department_id = serializers.UUIDField()
    from_department_id = serializers.UUIDField(required=False, allow_null=True)
    assigned_user_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=[
            "queued",
            "assigned",
            "claimed",
            "in_progress",
            "blocked",
            "completed",
            "cancelled",
        ],
        required=False,
        default="queued",
    )
    priority = serializers.ChoiceField(
        choices=["low", "normal", "high", "urgent"],
        required=False,
        default="normal",
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=255)
    metadata = serializers.JSONField(required=False, default=dict)
    resolution = serializers.JSONField(required=False, default=dict)
    missing_capability = serializers.JSONField(required=False, allow_null=True, default=None)
