"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.operating_models import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class AssertionRecord(models.Model):
    """Company-scoped assertion register for facts, opinions, assumptions, and questions."""

    KIND_CHOICES = [
        ("FACT", "Fact"),
        ("OPINION", "Opinion"),
        ("ASSUMPTION", "Assumption"),
        ("QUESTION", "Question"),
    ]
    VALIDATION_STATUS_CHOICES = [
        ("unvalidated", "Unvalidated"),
        ("pending", "Pending"),
        ("validated", "Validated"),
        ("rejected", "Rejected"),
        ("corrected", "Corrected"),
        ("client_asserted", "Client Asserted"),
        ("open", "Open"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="assertion_records",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="assertion_records",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assertion_records",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    pack_label = models.CharField(max_length=80, blank=True, default="")
    category = models.CharField(max_length=120, blank=True, default="")
    statement = models.TextField()
    source = models.TextField(blank=True, default="")
    confidence = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    validation_status = models.CharField(
        max_length=32,
        choices=VALIDATION_STATUS_CHOICES,
        default="unvalidated",
    )
    evidence_refs_json = models.JSONField(default=list, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assertion_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assertion_records"
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "kind"], name="assertion_org_kind_idx"),
            models.Index(fields=["company", "kind"], name="assertion_company_kind_idx"),
            models.Index(fields=["program", "validation_status"], name="assert_program_val_idx"),
            models.Index(fields=["company", "validation_status"], name="assert_company_val_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.statement[:80]}"


class AssetDependency(models.Model):
    """Generic lineage edge between company asset revisions."""

    DEPENDENCY_TYPE_CHOICES = [
        ("derived_from", "Derived From"),
        ("cites", "Cites"),
        ("supersedes", "Supersedes"),
        ("requires", "Requires"),
        ("informs", "Informs"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="asset_dependencies",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="asset_dependencies",
    )
    source_asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="outgoing_dependencies",
    )
    source_asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_dependencies",
    )
    target_asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="incoming_dependencies",
    )
    target_asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_dependencies",
    )
    dependency_type = models.CharField(
        max_length=32,
        choices=DEPENDENCY_TYPE_CHOICES,
        default="derived_from",
    )
    reason = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "asset_dependencies"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_asset",
                    "source_asset_version",
                    "target_asset",
                    "target_asset_version",
                    "dependency_type",
                ],
                name="asset_dependency_unique_edge",
            )
        ]
        indexes = [
            models.Index(fields=["company", "dependency_type"], name="asset_dep_company_type_idx"),
            models.Index(fields=["source_asset"], name="asset_dep_source_idx"),
            models.Index(fields=["target_asset"], name="asset_dep_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_asset_id} -> {self.target_asset_id} ({self.dependency_type})"


class StateProjection(models.Model):
    """Backend-owned materialized current-state projection for a company or program."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="state_projections",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="state_projections",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="state_projections",
    )
    projection_type = models.CharField(max_length=120)
    display_label = models.CharField(max_length=160, default="Current State")
    source_refs_json = models.JSONField(default=list, blank=True)
    json_state = models.JSONField(default=dict, blank=True)
    markdown_summary = models.TextField(blank=True, default="")
    generated_by = models.CharField(max_length=32, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "state_projections"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "program", "projection_type"],
                condition=models.Q(program__isnull=False),
                name="state_projection_program_type_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "projection_type"],
                condition=models.Q(program__isnull=True),
                name="state_projection_company_type_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "projection_type"], name="state_proj_company_type_idx"),
            models.Index(fields=["program", "projection_type"], name="state_proj_program_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.projection_type} {self.company_id}"


class PeriodicReviewDefinition(models.Model):
    """Company-scoped recurring review definition for metrics, scorecards, and reports."""

    CADENCE_CHOICES = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="periodic_review_definitions",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="periodic_review_definitions",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodic_review_definitions",
    )
    pack_id = models.CharField(max_length=160, blank=True, default="")
    template_id = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    cadence = models.CharField(max_length=24, choices=CADENCE_CHOICES, default="monthly")
    timezone = models.CharField(max_length=64, blank=True, default="UTC")
    evaluation_profile = models.ForeignKey(
        "EvaluationProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodic_review_definitions",
    )
    evaluation_profile_key = models.CharField(max_length=160, blank=True, default="")
    report_template_id = models.CharField(max_length=160, blank=True, default="")
    history_projection_type = models.CharField(max_length=120, blank=True, default="")
    enabled = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_periodic_review_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "periodic_review_definitions"
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "program", "template_id"],
                condition=models.Q(program__isnull=False),
                name="per_rev_comp_prog_tpl_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "template_id"],
                condition=models.Q(program__isnull=True),
                name="per_rev_comp_tpl_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "enabled"], name="per_rev_org_en_idx"),
            models.Index(fields=["company", "enabled"], name="per_rev_comp_en_idx"),
            models.Index(fields=["company", "cadence"], name="per_rev_comp_cad_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.cadence})"


class MetricSnapshot(models.Model):
    """Immutable company-scoped metric values captured for one review period."""

    SOURCE_TYPE_CHOICES = [
        ("connector", "Connector"),
        ("manual", "Manual"),
        ("imported", "Imported"),
        ("computed", "Computed"),
        ("seed", "Seed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="metric_snapshots",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="metric_snapshots",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metric_snapshots",
    )
    review_definition = models.ForeignKey(
        PeriodicReviewDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metric_snapshots",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    metric_values_json = models.JSONField(default=dict, blank=True)
    metric_sources_json = models.JSONField(default=dict, blank=True)
    source_type = models.CharField(max_length=24, choices=SOURCE_TYPE_CHOICES, default="manual")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_metric_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "metric_snapshots"
        ordering = ["-period_start", "-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "period_start"], name="metric_snap_org_period_idx"
            ),
            models.Index(fields=["company", "period_start"], name="metric_snap_comp_period_idx"),
            models.Index(
                fields=["review_definition", "period_start"], name="metric_snap_rev_period_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company_id} {self.period_start} - {self.period_end}"


class ReportRun(models.Model):
    """Generated report run that references artifacts, evaluations, and metric snapshots."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="report_runs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="report_runs",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    review_definition = models.ForeignKey(
        PeriodicReviewDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    metric_snapshot = models.ForeignKey(
        MetricSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    artifact = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    artifact_revision = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    report_template_id = models.CharField(max_length=160, blank=True, default="")
    period_start = models.DateField()
    period_end = models.DateField()
    evaluation_run_ids_json = models.JSONField(default=list, blank=True)
    generated_sections_json = models.JSONField(default=dict, blank=True)
    source_refs_json = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_report_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "report_runs"
        ordering = ["-period_start", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "period_start"], name="report_run_org_period_idx"),
            models.Index(fields=["company", "period_start"], name="report_run_company_period_idx"),
            models.Index(
                fields=["review_definition", "period_start"], name="report_run_review_period_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_template_id} {self.period_start} - {self.period_end}"


class ValidationDecision(models.Model):
    """Structured validation decision that can drive rework planning."""

    DECISION_CHOICES = [
        ("ACCEPT", "Accept"),
        ("REJECT", "Reject"),
        ("EDIT", "Edit"),
        ("DEFER", "Defer"),
        ("NEEDS_RESEARCH", "Needs Research"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="validation_decisions",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="validation_decisions",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_decisions",
    )
    assertion = models.ForeignKey(
        AssertionRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_decisions",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_decisions",
    )
    asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_decisions",
    )
    decision = models.CharField(max_length=32, choices=DECISION_CHOICES)
    category = models.CharField(max_length=120, blank=True, default="")
    rationale = models.TextField(blank=True, default="")
    proposed_change_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_validation_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "validation_decisions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "decision"], name="validation_company_dec_idx"),
            models.Index(fields=["program", "category"], name="validation_program_cat_idx"),
            models.Index(fields=["asset"], name="validation_asset_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.decision} {self.category}"


class ReworkPlan(models.Model):
    """Inspectable impact/rework plan generated from validation decisions."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approval_required", "Approval Required"),
        ("approved", "Approved"),
        ("executed", "Executed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="rework_plans",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="rework_plans",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rework_plans",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    trigger_summary = models.TextField(blank=True, default="")
    impact_json = models.JSONField(default=dict, blank=True)
    required_approvals_json = models.JSONField(default=list, blank=True)
    estimated_effort_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rework_plans",
    )
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executed_rework_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rework_plans"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="rework_plan_company_status_idx"),
            models.Index(fields=["program", "status"], name="rework_plan_program_status_idx"),
        ]

    def __str__(self) -> str:
        return f"ReworkPlan {self.id} ({self.status})"


class ReworkPlanItem(models.Model):
    """One target/action inside a generic rework plan."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("skipped", "Skipped"),
        ("executed", "Executed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        ReworkPlan,
        on_delete=models.CASCADE,
        related_name="items",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="rework_plan_items",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="rework_plan_items",
    )
    item_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=120)
    reason = models.TextField(blank=True, default="")
    recommended_order = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    metadata_json = models.JSONField(default=dict, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rework_plan_items"
        ordering = ["plan", "recommended_order", "created_at"]
        indexes = [
            models.Index(fields=["plan", "status"], name="rework_item_plan_status_idx"),
            models.Index(fields=["company", "item_type"], name="rework_item_company_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.target_id}"
