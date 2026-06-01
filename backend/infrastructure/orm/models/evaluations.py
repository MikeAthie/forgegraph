"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.governance import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class EvaluationProfile(models.Model):
    """Reusable evaluation profile supplied by a pack or company."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("disabled", "Disabled"),
        ("deprecated", "Deprecated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evaluation_profiles",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evaluation_profiles",
    )
    pack_release = models.ForeignKey(
        OperatingModelPackRelease,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_profiles",
    )
    profile_id = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    mode = models.CharField(max_length=80, blank=True, default="")
    rubric_json = models.JSONField(default=dict, blank=True)
    weights_json = models.JSONField(default=dict, blank=True)
    thresholds_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "evaluation_profiles"
        ordering = ["profile_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "profile_id"],
                condition=models.Q(company__isnull=False),
                name="eval_profile_company_profile_uniq",
            ),
            models.UniqueConstraint(
                fields=["pack_release", "profile_id"],
                condition=models.Q(company__isnull=True, pack_release__isnull=False),
                name="eval_profile_pack_profile_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="eval_profile_org_status_idx"),
            models.Index(fields=["company", "status"], name="eval_prof_comp_stat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile_id} ({self.status})"


class EvaluationRun(models.Model):
    """Persisted generic evaluation run for an artifact, program, or operation."""

    STATUS_CHOICES = [
        ("PASS", "Pass"),
        ("WARN", "Warn"),
        ("BLOCK", "Block"),
        ("RUNNING", "Running"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="evaluation_runs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="evaluation_runs",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    profile = models.ForeignKey(
        EvaluationProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_runs",
    )
    profile_key = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="RUNNING")
    score = models.FloatField(null=True, blank=True)
    grade = models.CharField(max_length=8, blank=True, default="")
    input_refs_json = models.JSONField(default=list, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_evaluation_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "evaluation_runs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="eval_run_company_status_idx"),
            models.Index(fields=["asset", "created_at"], name="eval_run_asset_time_idx"),
            models.Index(fields=["program", "created_at"], name="eval_run_program_time_idx"),
            models.Index(fields=["profile_key", "status"], name="eval_run_prof_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile_key} ({self.status})"


class EvaluationFinding(models.Model):
    """Actionable finding produced by a generic evaluation run."""

    SEVERITY_CHOICES = [
        ("INFO", "Info"),
        ("WARNING", "Warning"),
        ("CRITICAL", "Critical"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="evaluation_findings",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="evaluation_findings",
    )
    evaluation = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="findings",
    )
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES)
    issue_type = models.CharField(max_length=120)
    message = models.TextField()
    evidence_refs_json = models.JSONField(default=list, blank=True)
    suggested_fix = models.TextField(blank=True, default="")
    blocking = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evaluation_findings"
        ordering = ["-blocking", "severity", "created_at"]
        indexes = [
            models.Index(fields=["evaluation", "blocking"], name="eval_finding_eval_block_idx"),
            models.Index(fields=["company", "severity"], name="eval_finding_company_sev_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.severity} {self.issue_type}"


class EvaluationScorecard(models.Model):
    """Scorecard aggregate for a generic evaluation run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.OneToOneField(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="scorecard",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="evaluation_scorecards",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="evaluation_scorecards",
    )
    dimensions_json = models.JSONField(default=dict, blank=True)
    composite_score = models.FloatField(default=0)
    grade = models.CharField(max_length=8, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evaluation_scorecards"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_at"], name="eval_score_company_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.evaluation_id} {self.composite_score}"


class PolicyPack(models.Model):
    """Reusable policy pack supplied by an operating model pack or company."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("disabled", "Disabled"),
        ("deprecated", "Deprecated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="policy_packs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="policy_packs",
    )
    pack_release = models.ForeignKey(
        OperatingModelPackRelease,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_packs",
    )
    policy_pack_id = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    rules_json = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "policy_packs"
        ordering = ["policy_pack_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "policy_pack_id"],
                condition=models.Q(company__isnull=False),
                name="policy_pack_company_pack_uniq",
            ),
            models.UniqueConstraint(
                fields=["pack_release", "policy_pack_id"],
                condition=models.Q(company__isnull=True, pack_release__isnull=False),
                name="policy_pack_release_pack_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="policy_pack_org_status_idx"),
            models.Index(fields=["company", "status"], name="policy_pack_company_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.policy_pack_id} ({self.status})"


class PolicyEvaluation(models.Model):
    """Trace of policy evaluation before a side-effecting action."""

    RISK_LEVEL_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("CRITICAL", "Critical"),
    ]
    STATUS_CHOICES = [
        ("allowed", "Allowed"),
        ("approval_required", "Approval Required"),
        ("blocked", "Blocked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="policy_evaluations",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="policy_evaluations",
    )
    policy_pack = models.ForeignKey(
        PolicyPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_evaluations",
    )
    decision_record = models.ForeignKey(
        DecisionRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_evaluations",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_evaluations",
    )
    action_type = models.CharField(max_length=120)
    risk_level = models.CharField(max_length=16, choices=RISK_LEVEL_CHOICES, default="LOW")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="allowed")
    input_json = models.JSONField(default=dict, blank=True)
    trace_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_policy_evaluations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "policy_evaluations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="policy_eval_company_status_idx"),
            models.Index(fields=["company", "risk_level"], name="policy_eval_company_risk_idx"),
            models.Index(fields=["action_type", "risk_level"], name="policy_eval_action_risk_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action_type} {self.risk_level} ({self.status})"


class SignalTaxonomy(models.Model):
    """Pack or company supplied taxonomy for company operating-loop signals."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("disabled", "Disabled"),
        ("deprecated", "Deprecated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="signal_taxonomies",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="signal_taxonomies",
    )
    pack_release = models.ForeignKey(
        OperatingModelPackRelease,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signal_taxonomies",
    )
    taxonomy_id = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    definitions_json = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "signal_taxonomies"
        ordering = ["taxonomy_id"]
        indexes = [
            models.Index(fields=["organization", "status"], name="signal_tax_org_status_idx"),
            models.Index(fields=["company", "status"], name="signal_tax_company_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.taxonomy_id} ({self.status})"


class CompanyTeamRole(models.Model):
    """Company-scoped role definition installed from a pack or created by operators."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_team_roles",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_team_roles",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_roles",
    )
    role_key = models.CharField(max_length=120)
    display_label = models.CharField(max_length=160)
    permissions_json = models.JSONField(default=list, blank=True)
    approval_level = models.CharField(max_length=32, blank=True, default="")
    capacity_per_week = models.PositiveSmallIntegerField(default=0)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_company_team_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_team_roles"
        ordering = ["display_label"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "role_key"],
                name="company_team_role_company_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "role_key"], name="team_role_org_key_idx"),
            models.Index(fields=["company", "approval_level"], name="team_role_company_level_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_label} ({self.company_id})"


class CompanyTeamAssignment(models.Model):
    """Assignment of a user or stakeholder to a company team role."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_team_assignments",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_team_assignments",
    )
    role = models.ForeignKey(
        CompanyTeamRole,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_team_assignments",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_assignments",
    )
    assignment_scope = models.CharField(max_length=120, default="company")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    capacity_weight = models.FloatField(default=1)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_team_assignments"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="team_assign_company_status_idx"),
            models.Index(fields=["role", "status"], name="team_assign_role_status_idx"),
            models.Index(fields=["program", "status"], name="team_assign_program_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.role_id} {self.assignment_scope} ({self.status})"


class CapacityPlan(models.Model):
    """Company-scoped capacity plan for pack-defined or operator-defined work."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="capacity_plans",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="capacity_plans",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capacity_plans",
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    plan_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_capacity_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "capacity_plans"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["company", "period_start"], name="capacity_company_start_idx"),
            models.Index(fields=["organization", "period_start"], name="capacity_org_start_idx"),
        ]

    def __str__(self) -> str:
        return f"CapacityPlan {self.company_id}"


class PortfolioHealthSnapshot(models.Model):
    """Point-in-time health snapshot for one company or a pack-filtered portfolio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="portfolio_health_snapshots",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="portfolio_health_snapshots",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portfolio_health_snapshots",
    )
    pack_id = models.CharField(max_length=160, blank=True, default="")
    score = models.FloatField(null=True, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_portfolio_health_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "portfolio_health_snapshots"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "pack_id"], name="portfolio_org_pack_idx"),
            models.Index(fields=["company", "created_at"], name="portfolio_company_time_idx"),
        ]

    def __str__(self) -> str:
        return f"PortfolioHealth {self.pack_id or self.company_id}"


class CostLedgerEntry(models.Model):
    """Append-only accounting fact table projected from runtime usage data."""

    COST_TYPE_CHOICES = [
        ("llm", "LLM"),
        ("memory_summarization", "Memory Summarization"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="cost_ledger_entries",
    )
    execution = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_ledger_entries",
    )
    task = models.ForeignKey(
        "TaskRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_ledger_entries",
    )
    agent = models.ForeignKey(
        "AgentRegistryEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_ledger_entries",
    )
    workflow_revision = models.ForeignKey(
        GraphVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_ledger_entries",
    )
    provider = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    cost_type = models.CharField(max_length=32, choices=COST_TYPE_CHOICES, default="llm")
    quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    unit_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    total_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    occurred_at = models.DateTimeField()
    external_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cost_ledger_entries"
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_key"],
                name="cost_ledger_org_external_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "occurred_at"], name="cost_ledger_org_time_idx"),
            models.Index(fields=["cost_type", "occurred_at"], name="cost_ledger_type_time_idx"),
            models.Index(fields=["agent", "occurred_at"], name="cost_ledger_agent_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cost_type} ${self.total_cost_usd}"


class CostAggregate(models.Model):
    """Cached accounting aggregate for organization and operator views."""

    GRAIN_CHOICES = [
        ("hourly", "Hourly"),
        ("daily", "Daily"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="cost_aggregates",
    )
    agent = models.ForeignKey(
        "AgentRegistryEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_aggregates",
    )
    task = models.ForeignKey(
        "TaskRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_aggregates",
    )
    workflow_revision = models.ForeignKey(
        GraphVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_aggregates",
    )
    grain = models.CharField(max_length=16, choices=GRAIN_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    provider = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    cost_type = models.CharField(max_length=32, blank=True, default="")
    total_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    total_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    entry_count = models.PositiveIntegerField(default=0)
    external_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cost_aggregates"
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_key"],
                name="cost_aggregates_org_external_key_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "grain", "period_start"],
                name="cost_aggs_org_grain_time_idx",
            ),
            models.Index(
                fields=["agent", "grain", "period_start"], name="cost_aggs_agent_grain_time_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization.name} {self.grain} {self.period_start.isoformat()}"
