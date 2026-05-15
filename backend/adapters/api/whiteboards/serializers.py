"""Serializers for generic WorkWhiteboard APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class WhiteboardQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class WhiteboardPatchSerializer(serializers.Serializer[Any]):
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)
    request_type = serializers.CharField(max_length=80, required=False, allow_blank=True)
    client_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    request_summary = serializers.CharField(required=False, allow_blank=True)
    objective = serializers.CharField(required=False, allow_blank=True)
    budget_limit = serializers.CharField(max_length=120, required=False, allow_blank=True)
    timeline = serializers.CharField(max_length=255, required=False, allow_blank=True)
    constraints = serializers.JSONField(required=False)
    target_audience = serializers.JSONField(required=False)
    brand_context = serializers.JSONField(required=False)
    product_context = serializers.JSONField(required=False)
    channel_context = serializers.JSONField(required=False)
    known_facts = serializers.JSONField(required=False)
    assumptions = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)


class StrategySynthesisSerializer(serializers.Serializer[Any]):
    scores = serializers.JSONField(required=False, default=dict)


class WhiteboardPhaseEvaluationSerializer(serializers.Serializer[Any]):
    scorecard = serializers.JSONField(required=False, default=dict)
    scores = serializers.JSONField(required=False, default=dict)


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
