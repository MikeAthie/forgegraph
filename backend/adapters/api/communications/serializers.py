"""Serializers for generic communication APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class CommunicationThreadQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)
    service_engagement_id = serializers.UUIDField(required=False)
    operation_id = serializers.UUIDField(required=False)


class CommunicationThreadCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    service_engagement_id = serializers.UUIDField(required=False, allow_null=True)
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    approval_task_id = serializers.UUIDField(required=False, allow_null=True)
    artifact_id = serializers.UUIDField(required=False, allow_null=True)
    report_run_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255)
    thread_type = serializers.ChoiceField(
        choices=[
            "service_engagement",
            "operation",
            "approval",
            "deliverable",
            "support",
            "internal_handoff",
            "agent_collaboration",
            "capability_gap",
            "quality_gate",
            "system_event",
        ],
        required=False,
        default="support",
    )
    visibility_mode = serializers.ChoiceField(
        choices=["customer", "operator", "internal", "mixed"],
        required=False,
        default="mixed",
    )
    status = serializers.ChoiceField(
        choices=[
            "open",
            "waiting_on_customer",
            "waiting_on_operator",
            "waiting_on_agent",
            "resolved",
            "archived",
        ],
        required=False,
        default="open",
    )
    source_key = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)


class CommunicationAttachmentRefSerializer(serializers.Serializer[Any]):
    type = serializers.ChoiceField(
        choices=[
            "artifact",
            "artifact_revision",
            "report_run",
            "approval_task",
            "decision",
            "company_signal",
            "signal",
            "service_engagement",
            "operation",
            "tool_execution",
            "evaluation_run",
            "service_deliverable",
        ]
    )
    id = serializers.UUIDField()
    metadata = serializers.JSONField(required=False, default=dict)


class CommunicationMessageCreateSerializer(serializers.Serializer[Any]):
    message_kind = serializers.ChoiceField(
        choices=[
            "note",
            "request",
            "response",
            "status_update",
            "approval_request",
            "decision",
            "deliverable",
            "capability_gap",
            "handoff",
            "missing_info_request",
            "system_event",
            "agent_observation",
            "quality_gate_update",
            "tool_result_summary",
        ],
        required=False,
        default="note",
    )
    body = serializers.CharField(required=False, allow_blank=True, default="")
    body_format = serializers.ChoiceField(
        choices=["plain", "markdown", "structured_json"],
        required=False,
        default="plain",
    )
    visibility = serializers.ChoiceField(
        choices=["customer", "operator", "internal"],
        required=False,
        default="customer",
    )
    metadata = serializers.JSONField(required=False, default=dict)
    attachments = CommunicationAttachmentRefSerializer(many=True, required=False, default=list)


class CommunicationAttachmentCreateSerializer(serializers.Serializer[Any]):
    attachments = CommunicationAttachmentRefSerializer(many=True)
