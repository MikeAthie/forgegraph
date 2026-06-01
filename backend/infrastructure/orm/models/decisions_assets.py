"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.run_records import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class DecisionRecord(models.Model):
    """Unified decision ledger for human and automated supervision decisions."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("resolved", "Resolved"),
    ]

    TYPE_CHOICES = [
        ("human_approval", "Human Approval"),
        ("policy_guardrail", "Policy Guardrail"),
        ("marketplace_review", "Marketplace Review"),
        ("operator_intervention", "Operator Intervention"),
        ("objective_evaluation", "Objective Evaluation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="decision_records",
    )
    execution = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_records",
    )
    task = models.ForeignKey(
        "TaskRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_records",
    )
    task_lifecycle = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_records",
    )
    agent = models.ForeignKey(
        "AgentRegistryEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_records",
    )
    decision_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    source_approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_records",
    )
    external_key = models.CharField(max_length=255)
    context_json = models.JSONField(default=dict, blank=True)
    resolution_json = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "decision_records"
        ordering = ["-requested_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_key"],
                name="decision_records_org_external_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="decision_rec_org_stat_idx"),
            models.Index(fields=["decision_type", "status"], name="decision_rec_type_stat_idx"),
            models.Index(fields=["execution", "status"], name="decision_rec_exec_stat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.decision_type} ({self.status})"


class OperatingBriefRecord(models.Model):
    """Backend-owned current Living Operating Brief for a company or operation."""

    AUTONOMY_MODE_CHOICES = [
        ("manual", "Manual"),
        ("assisted", "Assisted"),
        ("autonomous", "Autonomous"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="operating_briefs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="operating_briefs",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="operating_briefs",
    )
    objective = models.TextField(null=True, blank=True)
    deliverable = models.TextField(null=True, blank=True)
    constraints_json = models.JSONField(default=list, blank=True)
    success_criteria_json = models.JSONField(default=list, blank=True)
    stakeholders_json = models.JSONField(default=list, blank=True)
    dependencies_json = models.JSONField(default=list, blank=True)
    assumptions_json = models.JSONField(default=list, blank=True)
    clarifications_json = models.JSONField(default=list, blank=True)
    priority_frame_json = models.JSONField(default=dict, blank=True)
    autonomy_mode = models.CharField(
        max_length=16,
        choices=AUTONOMY_MODE_CHOICES,
        default="assisted",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_operating_briefs",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_operating_briefs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operating_briefs"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "company"],
                condition=models.Q(operation__isnull=True),
                name="operating_briefs_company_current_uniq",
            ),
            models.UniqueConstraint(
                fields=["organization", "company", "operation"],
                condition=models.Q(operation__isnull=False),
                name="operating_briefs_operation_current_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "updated_at"], name="op_briefs_org_updated_idx"),
            models.Index(fields=["company", "operation"], name="op_briefs_company_op_idx"),
        ]

    def __str__(self) -> str:
        scope = self.operation_id or self.company_id
        return f"OperatingBrief {scope}"


class InteractionEventRecord(models.Model):
    """Append-only interaction history used to derive and inspect brief mutations."""

    EVENT_TYPE_CHOICES = [
        ("CREATE", "Create"),
        ("MODIFY", "Modify"),
        ("CLARIFY", "Clarify"),
        ("CONSTRAINT", "Constraint"),
        ("PRIORITY_SHIFT", "Priority Shift"),
        ("APPROVE", "Approve"),
        ("OVERRIDE", "Override"),
    ]
    ACTOR_CHOICES = [
        ("user", "User"),
        ("system", "System"),
    ]
    ACTION_CHOICES = [
        ("EXECUTE", "Execute"),
        ("ASK_CLARIFICATION", "Ask Clarification"),
        ("ASSUME_AND_CONTINUE", "Assume And Continue"),
        ("BLOCK", "Block"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="interaction_events",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="interaction_events",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="interaction_events",
    )
    brief = models.ForeignKey(
        OperatingBriefRecord,
        on_delete=models.CASCADE,
        related_name="events",
    )
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES)
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interaction_events",
    )
    timestamp = models.DateTimeField()
    raw_input = models.TextField(blank=True, default="")
    delta_json = models.JSONField(default=dict, blank=True)
    affected_fields_json = models.JSONField(default=list, blank=True)
    interpretation_json = models.JSONField(default=dict, blank=True)
    pm_action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    plan_implications_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "interaction_events"
        ordering = ["brief", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["brief", "sequence"],
                name="interaction_events_brief_sequence_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="interaction_org_time_idx"),
            models.Index(fields=["company", "created_at"], name="interaction_company_time_idx"),
            models.Index(fields=["operation", "created_at"], name="interaction_operation_time_idx"),
            models.Index(fields=["brief", "sequence"], name="interaction_brief_seq_idx"),
        ]

    def __str__(self) -> str:
        return f"InteractionEvent {self.event_type} #{self.sequence}"


class Asset(models.Model):
    """Company-owned artifact that can be reused as future knowledge."""

    ASSET_TYPE_CHOICES = [
        ("document", "Document"),
        ("image", "Image"),
        ("video", "Video"),
        ("dataset", "Dataset"),
        ("report", "Report"),
        ("deliverable", "Deliverable"),
        ("memo", "Memo"),
        ("policy_source", "Policy Source"),
    ]
    CREATED_BY_TYPE_CHOICES = [
        ("user", "User"),
        ("agent", "Agent"),
        ("system", "System"),
        ("external", "External"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
        ("superseded", "Superseded"),
        ("deleted", "Deleted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    title = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=32, choices=ASSET_TYPE_CHOICES)
    source_key = models.CharField(max_length=512, blank=True, default="")
    origin_operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="origin_assets",
    )
    origin_task = models.ForeignKey(
        TaskRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="origin_assets",
    )
    origin_node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="origin_assets",
    )
    origin_deliverable_id = models.UUIDField(null=True, blank=True)
    created_by_type = models.CharField(
        max_length=16,
        choices=CREATED_BY_TYPE_CHOICES,
        default="system",
    )
    created_by_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_assets"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_key"],
                condition=models.Q(source_key__gt=""),
                name="asset_company_source_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="asset_org_time_idx"),
            models.Index(fields=["company", "status"], name="asset_comp_status_idx"),
            models.Index(fields=["company", "asset_type"], name="asset_comp_type_idx"),
            models.Index(fields=["origin_operation"], name="asset_origin_run_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.asset_type})"


class AssetVersion(models.Model):
    """Versioned content pointer for an asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    content_uri = models.CharField(max_length=1024)
    content_hash = models.CharField(max_length=64, blank=True, default="")
    mime_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    provenance_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "asset_versions"
        ordering = ["asset", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "version_number"],
                name="asset_ver_asset_num_uniq",
            ),
            models.UniqueConstraint(
                fields=["asset", "content_hash"],
                condition=models.Q(content_hash__gt=""),
                name="asset_ver_hash_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["asset", "version_number"], name="asset_ver_num_idx"),
            models.Index(fields=["content_hash"], name="asset_ver_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.asset_id} v{self.version_number}"


class MediaGenerationJob(models.Model):
    """Backend-owned Gemini media generation state for draft assets."""

    MODALITY_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="media_generation_jobs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="media_generation_jobs",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_generation_jobs",
    )
    credential = models.ForeignKey(
        "APIKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_generation_jobs",
    )
    modality = models.CharField(max_length=16, choices=MODALITY_CHOICES)
    provider = models.CharField(max_length=32, default="google")
    model = models.CharField(max_length=128)
    prompt = models.TextField()
    prompt_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    provider_operation_name = models.CharField(max_length=512, blank=True, default="")
    output_asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    output_asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    output_mime_type = models.CharField(max_length=128, blank=True, default="")
    output_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    request_json = models.JSONField(default=dict, blank=True)
    response_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "media_generation_jobs"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="media_job_company_idempotency_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="media_job_org_status_idx"),
            models.Index(fields=["company", "status"], name="media_job_company_status_idx"),
            models.Index(
                fields=["provider_operation_name"],
                name="media_job_provider_op_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.modality} media job {self.id} ({self.status})"
