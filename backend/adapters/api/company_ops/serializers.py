"""Serializers for company operating-loop APIs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from application.services.atlas_onboarding import forbidden_key, safe_metadata
from application.services.company_ops import OPERATION_TEMPLATES
from infrastructure.orm.models import (
    CompanyOperationObjective,
    CompanyOpportunity,
    CompanySignal,
)


class CompanyOpsCompanyQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()


class AtlasOnboardingIntakeSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    client_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    contact_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    contact_email = serializers.EmailField(required=False, allow_blank=True, max_length=255)
    website_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    business_summary = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    goals = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=500),
        required=False,
    )
    target_audience = serializers.JSONField(required=False)
    brand_voice = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    constraints = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=500),
        required=False,
    )
    approved_channels = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=64),
        required=False,
    )
    blocked_channels = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=64),
        required=False,
    )
    success_metrics = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=255),
        required=False,
    )
    budget_range = serializers.CharField(required=False, allow_blank=True, max_length=120)
    timeline = serializers.CharField(required=False, allow_blank=True, max_length=255)
    service_slug = serializers.SlugField(required=False, allow_blank=True, max_length=160)
    service_package = serializers.CharField(required=False, allow_blank=True, max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    source: Any = serializers.CharField(required=False, allow_blank=True, max_length=64)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        initial = self.initial_data if isinstance(self.initial_data, dict) else {}
        allowed_fields = set(self.fields)
        unknown_fields = sorted(str(key) for key in initial if key not in allowed_fields)
        if unknown_fields:
            errors = {}
            for field in unknown_fields:
                if forbidden_key(field):
                    errors[field] = ["Credential-like fields are forbidden."]
                else:
                    errors[field] = ["Unknown fields are not accepted by this contract."]
            raise serializers.ValidationError(errors)
        normalized = dict(attrs)
        for field in (
            "client_name",
            "contact_name",
            "website_url",
            "business_summary",
            "brand_voice",
            "budget_range",
            "timeline",
            "service_slug",
            "service_package",
            "notes",
            "source",
        ):
            if field in normalized:
                normalized[field] = str(normalized.get(field) or "").strip()
        if "contact_email" in normalized:
            normalized["contact_email"] = str(normalized.get("contact_email") or "").strip().lower()
        if "metadata" in normalized:
            raw_metadata = normalized.get("metadata")
            normalized["metadata"] = (
                safe_metadata(raw_metadata) if isinstance(raw_metadata, dict) else {}
            )
        return normalized


class CompanySignalCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    signal_type = serializers.ChoiceField(
        choices=[item[0] for item in CompanySignal.SIGNAL_TYPE_CHOICES]
    )
    signal_kind = serializers.ChoiceField(
        required=False,
        choices=[item[0] for item in CompanySignal.SIGNAL_KIND_CHOICES],
    )
    domain_context = serializers.CharField(required=False, allow_blank=True, max_length=64)
    title = serializers.CharField(max_length=255)
    summary = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    source = serializers.CharField(required=False, allow_blank=True, max_length=64)  # type: ignore[assignment]
    external_key = serializers.CharField(required=False, allow_blank=True, max_length=255)
    channel = serializers.CharField(required=False, allow_blank=True, max_length=64)
    contact_alias = serializers.CharField(required=False, allow_blank=True, max_length=120)
    product_id = serializers.UUIDField(required=False, allow_null=True)
    order_id = serializers.UUIDField(required=False, allow_null=True)
    fulfillment_id = serializers.UUIDField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class CompanySignalQualifySerializer(serializers.Serializer[Any]):
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    summary = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    next_action = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CompanyOpportunityStatusSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[item[0] for item in CompanyOpportunity.STATUS_CHOICES]
    )
    next_action = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PublicationDraftCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    channel = serializers.CharField(required=False, allow_blank=True, max_length=64)
    audience = serializers.CharField(required=False, allow_blank=True, max_length=255)
    body = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    call_to_action = serializers.CharField(required=False, allow_blank=True, max_length=255)
    signal_id = serializers.UUIDField(required=False, allow_null=True)
    opportunity_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField(required=False, allow_null=True)
    asset_version_id = serializers.UUIDField(required=False, allow_null=True)
    media_job_id = serializers.UUIDField(required=False, allow_null=True)


class ApprovalRequestSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ProcurementDraftLineSerializer(serializers.Serializer[Any]):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    sku = serializers.CharField(required=False, allow_blank=True, max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    quantity = serializers.IntegerField(required=False, min_value=1, default=1)
    unit_cost_amount = serializers.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = serializers.CharField(required=False, allow_blank=True, max_length=8)
    metadata = serializers.JSONField(required=False, default=dict)


class ProcurementDraftCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    rationale = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    budget_amount = serializers.DecimalField(
        required=False, max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    currency = serializers.CharField(required=False, allow_blank=True, max_length=8)
    lines = ProcurementDraftLineSerializer(required=False, many=True)


class CompanyOperationLaunchSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_type = serializers.ChoiceField(choices=sorted(OPERATION_TEMPLATES.keys()))
    operation_family = serializers.ChoiceField(
        required=False,
        choices=[item[0] for item in CompanyOperationObjective.OPERATION_FAMILY_CHOICES],
    )
    domain_context = serializers.CharField(required=False, allow_blank=True, max_length=64)
    source_signal_id = serializers.UUIDField(required=False, allow_null=True)
    context_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    run_type = serializers.ChoiceField(
        required=False,
        choices=["rehearsal", "demand", "commerce", "live_selling"],
    )
    run_goal = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    hypothesis = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    target_signal = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class CompanyOperationObjectiveEvaluationSerializer(serializers.Serializer[Any]):
    success_score = serializers.IntegerField(min_value=0, max_value=100)
    miss_analysis = serializers.CharField(required=False, allow_blank=True, max_length=3000)
    next_decision = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    integrity_gates = serializers.JSONField(required=False, default=dict)
