"""Serializers for generic operating model pack APIs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class PackCompileSerializer(serializers.Serializer[Any]):
    company_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    objective = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    autonomy_mode = serializers.CharField(max_length=64, required=False, default="assisted")
    ai_access_mode = serializers.CharField(max_length=64, required=False, default="managed")
    intelligence_provider = serializers.CharField(max_length=64, required=False, default="openai")
    selected_services = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )
    regions = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )


class PackInstallSerializer(serializers.Serializer[Any]):
    config = serializers.JSONField(required=False, default=dict)


class CompanyPackInstallSerializer(serializers.Serializer[Any]):
    pack_id = serializers.CharField(max_length=160)
    release_id = serializers.UUIDField(required=False, allow_null=True)
    role = serializers.ChoiceField(choices=["primary", "addon"], required=False)
    config = serializers.JSONField(required=False, default=dict)
    secret_bindings = serializers.JSONField(required=False, default=dict)


class CompanyPackPatchSerializer(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=["primary", "addon"], required=False)
    status = serializers.ChoiceField(
        choices=[
            "active",
            "disabled",
            "archived",
            "installing",
            "upgrading",
            "rollback_pending",
            "failed",
        ],
        required=False,
    )
    config = serializers.JSONField(required=False)


class CompanyPackUpgradeSerializer(serializers.Serializer[Any]):
    target_release_id = serializers.UUIDField(required=False, allow_null=True)
    config_overrides = serializers.JSONField(required=False, default=dict)


class CompanyPackArchiveSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ProgramCreateSerializer(serializers.Serializer[Any]):
    template_id = serializers.CharField(max_length=160)
    pack_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    objective = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class ProgramPatchSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=["draft", "active", "paused", "completed", "cancelled"],
        required=False,
    )
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    objective = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


class StageAdvanceSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[
            "not_started",
            "in_progress",
            "blocked",
            "awaiting_validation",
            "completed",
            "rerun_required",
        ],
        required=False,
        default="completed",
    )


class StageOperationLaunchSerializer(serializers.Serializer[Any]):
    operation_template_id = serializers.CharField(max_length=160)
    context_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    run_goal = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class StageOutputGenerationSerializer(serializers.Serializer[Any]):
    workflow_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    artifact_schema_ids = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )
    selected_family_ids = serializers.ListField(
        child=serializers.CharField(max_length=120),
        allow_empty=True,
        required=False,
        default=list,
    )
    source_artifact_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=False,
        default=list,
    )
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    evaluation_inputs = serializers.JSONField(required=False, default=dict)


class AssertionCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    kind = serializers.ChoiceField(choices=["FACT", "OPINION", "ASSUMPTION", "QUESTION"])
    pack_label = serializers.CharField(max_length=80, required=False, allow_blank=True)
    category = serializers.CharField(max_length=120, required=False, allow_blank=True)
    statement = serializers.CharField(max_length=4000)
    source = serializers.CharField(max_length=4000, required=False, allow_blank=True)  # type: ignore[assignment]
    confidence = serializers.FloatField(required=False, min_value=0, max_value=1, default=0.5)
    validation_status = serializers.ChoiceField(
        choices=[
            "unvalidated",
            "pending",
            "validated",
            "rejected",
            "corrected",
            "client_asserted",
            "open",
        ],
        required=False,
        default="unvalidated",
    )
    evidence_refs = serializers.ListField(required=False, default=list)
    metadata = serializers.JSONField(required=False, default=dict)


class AssertionQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False)
    kind = serializers.CharField(max_length=16, required=False, allow_blank=True)
    validation_status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ValidationDecisionCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    assertion_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField(required=False, allow_null=True)
    asset_version_id = serializers.UUIDField(required=False, allow_null=True)
    decision = serializers.ChoiceField(
        choices=["ACCEPT", "REJECT", "EDIT", "DEFER", "NEEDS_RESEARCH"]
    )
    category = serializers.CharField(max_length=120, required=False, allow_blank=True)
    rationale = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    proposed_change = serializers.JSONField(required=False, default=dict)


class WorkArtifactCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255)
    artifact_type = serializers.CharField(max_length=120)
    content = serializers.JSONField()
    metadata = serializers.JSONField(required=False, default=dict)


class WorkArtifactQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(required=False)
    artifact_type = serializers.CharField(max_length=120, required=False, allow_blank=True)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ArtifactRevisionCreateSerializer(serializers.Serializer[Any]):
    content = serializers.JSONField()
    parent_revision_id = serializers.UUIDField(required=False, allow_null=True)
    label = serializers.CharField(max_length=64, required=False, allow_blank=True)  # type: ignore[assignment]
    metadata = serializers.JSONField(required=False, default=dict)


class CanonicalRevisionSerializer(serializers.Serializer[Any]):
    revision_id = serializers.UUIDField()


class EvaluationRunSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    profile_id = serializers.CharField(max_length=160)
    content = serializers.CharField(required=False, allow_blank=True)
    program_id = serializers.UUIDField(required=False, allow_null=True)
    asset_id = serializers.UUIDField(required=False, allow_null=True)
    asset_version_id = serializers.UUIDField(required=False, allow_null=True)
    input_refs = serializers.ListField(required=False, default=list)
    inputs = serializers.JSONField(required=False, default=dict)


class PeriodicReviewQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    enabled = serializers.BooleanField(required=False)


class PeriodicReviewCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    template_id = serializers.CharField(max_length=160)
    display_name = serializers.CharField(max_length=255)
    cadence = serializers.ChoiceField(
        choices=["weekly", "monthly", "quarterly", "custom"],
        required=False,
        default="monthly",
    )
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    evaluation_profile_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    report_template_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    history_projection_type = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    enabled = serializers.BooleanField(required=False, default=True)
    metadata = serializers.JSONField(required=False, default=dict)


class MetricSnapshotQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    review_definition_id = serializers.UUIDField(required=False, allow_null=True)


class MetricSnapshotCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    review_definition_id = serializers.UUIDField(required=False, allow_null=True)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    metric_values = serializers.JSONField(required=False, default=dict)
    metric_sources = serializers.JSONField(required=False, default=dict)
    source_type = serializers.ChoiceField(
        choices=["connector", "manual", "imported", "computed", "seed"],
        required=False,
        default="manual",
    )
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)


class PeriodicReviewRunSerializer(serializers.Serializer[Any]):
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    metric_snapshot_id = serializers.UUIDField(required=False, allow_null=True)
    metric_values = serializers.JSONField(required=False)
    metric_sources = serializers.JSONField(required=False, default=dict)
    source_type = serializers.ChoiceField(
        choices=["connector", "manual", "imported", "computed", "seed"],
        required=False,
        default="manual",
    )
    force = serializers.BooleanField(required=False, default=False)
    dry_run = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)


class ReportRunQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    review_definition_id = serializers.UUIDField(required=False, allow_null=True)


class PolicyEvaluationSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    action_type = serializers.CharField(max_length=120)
    policy_pack_id = serializers.CharField(max_length=160, required=False, allow_blank=True)
    operation_id = serializers.UUIDField(required=False, allow_null=True)
    inputs = serializers.JSONField(required=False, default=dict)


class ReworkPlanCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False, allow_null=True)
    validation_decision_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class PackToolExecutionSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField()
    tool_id = serializers.CharField(max_length=160)
    inputs = serializers.JSONField(required=False, default=dict)
    dry_run = serializers.BooleanField(required=False, default=True)
    policy_evaluation_id = serializers.UUIDField(required=False, allow_null=True)


class StateProjectionQuerySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    program_id = serializers.UUIDField(required=False)
    projection_type = serializers.CharField(
        max_length=120,
        required=False,
        default="currently_true_state",
    )
