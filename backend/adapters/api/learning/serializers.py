"""Serializers for company learning APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class PreferenceEventQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)


class OutcomeReviewQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField(required=False, allow_null=True)
    deliverable_id = serializers.UUIDField(required=False, allow_null=True)


class OutcomeReviewCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    task_id = serializers.UUIDField(required=False, allow_null=True)
    node_run_id = serializers.UUIDField(required=False, allow_null=True)
    decision_id = serializers.UUIDField(required=False, allow_null=True)
    deliverable_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField(required=False, allow_null=True)
    success_score = serializers.FloatField(
        required=False, allow_null=True, min_value=0.0, max_value=1.0
    )
    success_metrics = serializers.JSONField(required=False, default=dict)
    human_feedback = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    issues = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )
    root_cause = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PolicyRuleQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    status = serializers.CharField(required=False, allow_blank=True)


class PolicyRuleCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255, trim_whitespace=True)
    condition = serializers.JSONField(required=False, default=dict)
    recommendation = serializers.JSONField(required=False, default=dict)
    confidence = serializers.FloatField(required=False, default=0.5, min_value=0.0, max_value=1.0)
    scope_type = serializers.CharField(required=False, default="company")
    scope_id = serializers.CharField(required=False, allow_blank=True, default="")
    supporting_preference_event_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    supporting_outcome_review_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
