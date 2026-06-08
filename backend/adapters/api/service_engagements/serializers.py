"""Serializers for generic service catalog and engagement APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from application.services.agency_deliverable_catalog import get_deliverable_definition


class ServiceCatalogQuerySerializer(serializers.Serializer[Any]):
    status = serializers.CharField(max_length=16, required=False, allow_blank=True)
    visibility = serializers.CharField(max_length=16, required=False, allow_blank=True)


class ServiceCatalogCreateSerializer(serializers.Serializer[Any]):
    slug = serializers.SlugField(max_length=160)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["draft", "active", "disabled", "archived"],
        required=False,
        default="draft",
    )
    visibility = serializers.ChoiceField(
        choices=["internal", "organization", "customer", "public"],
        required=False,
        default="organization",
    )
    audience = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    required_pack_ids = serializers.ListField(
        child=serializers.CharField(max_length=160),
        required=False,
        default=list,
    )
    optional_pack_ids = serializers.ListField(
        child=serializers.CharField(max_length=160),
        required=False,
        default=list,
    )
    intake_schema = serializers.JSONField(required=False, default=dict)
    deliverables_schema = serializers.ListField(required=False, default=list)
    default_operation_templates = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
        default=list,
    )
    default_report_template_id = serializers.CharField(
        max_length=160,
        required=False,
        allow_blank=True,
        default="",
    )
    pricing_metadata = serializers.JSONField(required=False, default=dict)
    metadata = serializers.JSONField(required=False, default=dict)


class ServiceCatalogPatchSerializer(ServiceCatalogCreateSerializer):
    slug = serializers.SlugField(max_length=160, required=False)
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=["draft", "active", "disabled", "archived"],
        required=False,
    )
    visibility = serializers.ChoiceField(
        choices=["internal", "organization", "customer", "public"],
        required=False,
    )


class ServiceEngagementQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ServiceEngagementCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    catalog_item_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=[
            "requested",
            "intake",
            "in_progress",
            "waiting_on_customer",
            "in_review",
            "delivered",
            "completed",
            "cancelled",
            "archived",
        ],
        required=False,
        default="requested",
    )
    customer_status = serializers.ChoiceField(
        choices=[
            "requested",
            "intake_needed",
            "working",
            "waiting_on_you",
            "review_ready",
            "delivered",
            "completed",
            "cancelled",
        ],
        required=False,
        default="requested",
    )
    intake_data = serializers.JSONField(required=False, default=dict)
    public_summary = serializers.CharField(required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(required=False, allow_blank=True, default="")
    source_key = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    required_pack_ids = serializers.ListField(
        child=serializers.CharField(max_length=160),
        required=False,
    )
    operation_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    assigned_operator_id = serializers.UUIDField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class ServiceEngagementPatchSerializer(ServiceEngagementCreateSerializer):
    company_id = serializers.UUIDField(required=False)
    catalog_item_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(
        choices=[
            "requested",
            "intake",
            "in_progress",
            "waiting_on_customer",
            "in_review",
            "delivered",
            "completed",
            "cancelled",
            "archived",
        ],
        required=False,
    )
    customer_status = serializers.ChoiceField(
        choices=[
            "requested",
            "intake_needed",
            "working",
            "waiting_on_you",
            "review_ready",
            "delivered",
            "completed",
            "cancelled",
        ],
        required=False,
    )


class ServiceDeliverableCreateSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=255)
    deliverable_type = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(
        choices=["draft", "in_review", "ready", "delivered", "accepted", "archived"],
        required=False,
        default="draft",
    )
    visibility = serializers.ChoiceField(
        choices=["customer", "operator", "internal"],
        required=False,
        default="customer",
    )
    artifact_id = serializers.UUIDField(required=False, allow_null=True)
    report_run_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)


class ServiceDeliverableActionSerializer(serializers.Serializer[Any]):
    action = serializers.ChoiceField(
        choices=[
            "mark_ready",
            "submit_for_approval",
            "deliver_to_client",
            "accept",
        ]
    )

class DepartmentPipelineCreateSerializer(serializers.Serializer[Any]):
    template_id = serializers.CharField(
        max_length=160,
        required=False,
        allow_blank=True,
        default="digital_marketing_pro.weekend_social_launch.v1",
    )


class DepartmentPipelineCompleteStageSerializer(serializers.Serializer[Any]):
    outputs = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        default=list,
    )


class DepartmentPipelineReasonSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AtlasDeliverableAssembleSerializer(serializers.Serializer[Any]):
    deliverable_type = serializers.CharField(max_length=80, required=False)

    def validate_deliverable_type(self, value: str) -> str:
        if get_deliverable_definition(value) is None:
            raise serializers.ValidationError("Unknown Atlas deliverable type.")
        return value


class AtlasLaunchReadinessSerializer(serializers.Serializer[Any]):
    mode = serializers.ChoiceField(
        choices=["dry_run", "live"],
        required=False,
        default="dry_run",
    )
    dry_run = serializers.BooleanField(required=False, default=True)
    live_mode = serializers.BooleanField(required=False, default=False)
    create_receipt = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
