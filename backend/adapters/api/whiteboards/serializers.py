"""Serializers for generic WorkWhiteboard APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class WhiteboardQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class WhiteboardPatchSerializer(serializers.Serializer[Any]):
    work_status = serializers.CharField(max_length=32, required=False, allow_blank=True)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)
    request_type = serializers.CharField(max_length=80, required=False, allow_blank=True)
    project_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    client_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    request_summary = serializers.CharField(required=False, allow_blank=True)
    objective = serializers.CharField(required=False, allow_blank=True)
    budget_limit = serializers.CharField(max_length=120, required=False, allow_blank=True)
    timeline = serializers.CharField(max_length=255, required=False, allow_blank=True)
    constraints = serializers.JSONField(required=False)
    stakeholder_context = serializers.JSONField(required=False)
    resource_context = serializers.JSONField(required=False)
    delivery_context = serializers.JSONField(required=False)
    target_audience = serializers.JSONField(required=False)
    brand_context = serializers.JSONField(required=False)
    product_context = serializers.JSONField(required=False)
    channel_context = serializers.JSONField(required=False)
    known_facts = serializers.JSONField(required=False)
    assumptions = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)


class WhiteboardBoardCardCreateSerializer(serializers.Serializer[Any]):
    department_id = serializers.UUIDField()
    title = serializers.CharField(max_length=240)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=[
            "queued",
            "assigned",
            "in_progress",
            "blocked",
            "ready_for_review",
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
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    assigned_user_id = serializers.UUIDField(required=False, allow_null=True)
    customer_visible = serializers.BooleanField(required=False, default=False)
    links = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class WhiteboardBoardCardPatchSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[
            "queued",
            "assigned",
            "in_progress",
            "blocked",
            "ready_for_review",
            "completed",
            "cancelled",
        ],
        required=False,
    )
    department_id = serializers.UUIDField(required=False)
    assigned_user_id = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=["low", "normal", "high", "urgent"], required=False)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    blocker_reason = serializers.CharField(
        max_length=600, required=False, allow_blank=True, default=""
    )
    title = serializers.CharField(max_length=240, required=False, allow_blank=True)
    customer_visible = serializers.BooleanField(required=False)
    expected_updated_at = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    idempotency_key = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class WhiteboardBoardEvidenceSerializer(serializers.Serializer[Any]):
    evidence_type = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default="note"
    )
    target_id = serializers.UUIDField(required=False, allow_null=True)
    summary = serializers.CharField(max_length=600, required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class StrategySynthesisSerializer(serializers.Serializer[Any]):
    scores = serializers.JSONField(required=False, default=dict)


class WhiteboardPhaseEvaluationSerializer(serializers.Serializer[Any]):
    scorecard = serializers.JSONField(required=False, default=dict)
    scores = serializers.JSONField(required=False, default=dict)


class WhiteboardPhaseWorkstreamCompleteSerializer(serializers.Serializer[Any]):
    result = serializers.JSONField(required=False, default=dict)


class WhiteboardDeploymentPrepareSerializer(serializers.Serializer[Any]):
    policy_id = serializers.CharField(max_length=160, required=False, allow_blank=True)


class WhiteboardDeploymentExecuteSerializer(serializers.Serializer[Any]):
    policy_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    dry_run = serializers.BooleanField(required=False, default=True)
    inputs = serializers.JSONField(required=False, default=dict)


class WhiteboardPerformanceStartSerializer(serializers.Serializer[Any]):
    policy_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)


class WhiteboardPerformanceReportSerializer(serializers.Serializer[Any]):
    policy_id = serializers.CharField(max_length=160, required=False, allow_blank=True)


class WhiteboardPerformanceEvaluationSerializer(serializers.Serializer[Any]):
    policy_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    scorecard = serializers.JSONField(required=False, default=dict)
    scores = serializers.JSONField(required=False, default=dict)
