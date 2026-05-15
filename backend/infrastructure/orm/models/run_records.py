"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.billing import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class RunCheckpoint(models.Model):
    """RunCheckpoint model representing the latest durable checkpoint for a run."""

    run = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        related_name="checkpoint",
        primary_key=True,
    )
    node_id = models.CharField(max_length=64)
    step_index = models.PositiveIntegerField(default=0)
    state_json = models.JSONField(default=dict)
    completed_nodes = models.JSONField(default=list)
    skipped_nodes = models.JSONField(default=list)
    graph_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "run_checkpoints"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["updated_at"], name="run_checkpoints_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"RunCheckpoint {self.run_id} @ {self.step_index}"


class NodeRun(models.Model):
    """NodeRun model representing the execution of a single node."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("waiting", "Waiting"),  # Human gate awaiting approval
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="node_runs",
    )
    node_id = models.CharField(max_length=255)
    node_type = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    attempt = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    input_json = models.JSONField(default=dict, blank=True)
    output_json = models.JSONField(null=True, blank=True)
    error_json = models.JSONField(null=True, blank=True)
    trace_id = models.CharField(max_length=32, blank=True, default="")
    span_id = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        db_table = "node_runs"
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["run", "started_at", "attempt"], name="node_runs_run_time_idx"),
            models.Index(fields=["trace_id"], name="node_runs_trace_id_idx"),
        ]

    def __str__(self) -> str:
        return f"NodeRun {self.node_id} - {self.status}"

    @property
    def duration_ms(self) -> int | None:
        """Calculate node run duration in milliseconds."""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


class NodeRunCache(models.Model):
    """NodeRunCache model storing cached node outputs."""

    cache_key = models.CharField(max_length=128, primary_key=True)
    output_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "node_run_cache"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["expires_at"], name="node_run_cache_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"NodeRunCache {self.cache_key}"


class ApprovalTask(models.Model):
    """ApprovalTask model representing a human gate approval request."""

    APPROVAL_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="approval_tasks",
    )
    task_lifecycle = models.ForeignKey(
        "TaskLifecycleRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_tasks",
    )
    node_id = models.CharField(max_length=64)
    assignee = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_tasks",
    )
    status = models.CharField(
        max_length=16,
        choices=APPROVAL_STATUS_CHOICES,
        default="pending",
    )
    payload = models.JSONField(default=dict)  # prompt_message, required_fields from node config
    result = models.JSONField(null=True, blank=True)  # submitted fields, feedback, approved flag
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "approval_tasks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assignee", "status"], name="approval_tasks_assignee_idx"),
            models.Index(fields=["run", "status"], name="approval_tasks_run_idx"),
        ]

    def __str__(self) -> str:
        return f"ApprovalTask {self.id} - {self.status}"


class AgentRegistryEntry(models.Model):
    """Organization-scoped registry entry for a supervised agent."""

    STATUS_CHOICES = [
        ("idle", "Idle"),
        ("active", "Active"),
        ("attention", "Attention"),
        ("offline", "Offline"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="agent_registry_entries",
    )
    slug = models.SlugField(max_length=160)
    display_name = models.CharField(max_length=255)
    source_workflow = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="agent_registry_entries",
    )
    source_workflow_revision = models.ForeignKey(
        GraphVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_registry_entries",
    )
    source_node_id = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="idle")
    policy_snapshot_json = models.JSONField(default=dict, blank=True)
    capabilities_json = models.JSONField(default=dict, blank=True)
    default_model = models.CharField(max_length=128, blank=True, default="")
    last_execution = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_registry_last_seen",
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_registry_entries"
        ordering = ["display_name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_workflow", "source_node_id"],
                name="agent_registry_org_workflow_node_uniq",
            ),
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="agent_registry_org_slug_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="agent_registry_org_status_idx"),
            models.Index(
                fields=["organization", "source_workflow"],
                name="agent_reg_org_wf_idx",
            ),
            models.Index(fields=["last_seen_at"], name="agent_registry_last_seen_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.organization.name})"


class TaskLifecycleRecord(models.Model):
    """Backend-owned canonical lifecycle state for one logical task."""

    STATUS_CHOICES = [
        ("created", "Created"),
        ("queued", "Queued"),
        ("claimed", "Claimed"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("waiting_for_decision", "Waiting For Decision"),
        ("retry_scheduled", "Retry Scheduled"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("dead_lettered", "Dead Lettered"),
        ("cancelled", "Cancelled"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_lifecycle_records",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_lifecycle_records",
    )
    source_node_id = models.CharField(max_length=255)
    node_type = models.CharField(max_length=64, blank=True, default="")
    external_key = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="created")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="normal")
    summary = models.TextField(blank=True, default="")
    current_attempt = models.PositiveIntegerField(default=1)
    current_node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_tasks",
    )
    current_decision = models.ForeignKey(
        "DecisionRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_tasks",
    )
    current_department = models.ForeignKey(
        "DepartmentRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_lifecycle_tasks",
    )
    retry_metadata = models.JSONField(default=dict, blank=True)
    recovery_options = models.JSONField(default=list, blank=True)
    unresolved_error = models.TextField(blank=True, default="")
    stale_event_count = models.PositiveIntegerField(default=0)
    late_event_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_transition_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_lifecycle_records"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_key"],
                name="task_lifecycle_org_external_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="task_life_org_status_idx"),
            models.Index(fields=["run", "status"], name="task_life_run_status_idx"),
            models.Index(fields=["run", "source_node_id"], name="task_life_run_node_idx"),
            models.Index(
                fields=["current_department", "status"],
                name="task_life_dept_status_idx",
            ),
            models.Index(fields=["last_transition_at"], name="task_life_transition_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class TaskAttemptRecord(models.Model):
    """Backend-owned attempt identity for a lifecycle task."""

    STATUS_CHOICES = [
        ("created", "Created"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("retry_scheduled", "Retry Scheduled"),
        ("dead_lettered", "Dead Lettered"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lifecycle_task = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_attempts",
    )
    node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_attempts",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    parent_attempt = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retry_attempts",
    )
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    owner_component = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="created")
    retry_reason = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_attempt_records"
        ordering = ["attempt_number", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lifecycle_task", "attempt_number"],
                name="task_attempt_lifecycle_number_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["run", "attempt_number"], name="task_attempt_run_number_idx"),
            models.Index(fields=["status", "updated_at"], name="task_attempt_status_idx"),
            models.Index(fields=["idempotency_key"], name="task_attempt_idem_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.lifecycle_task_id} attempt {self.attempt_number}"


class TaskLifecycleEvent(models.Model):
    """Immutable task lifecycle transition event."""

    OUTCOME_CHOICES = [
        ("accepted", "Accepted"),
        ("duplicate", "Duplicate"),
        ("invalid", "Invalid"),
        ("stale", "Stale"),
        ("late", "Late"),
        ("out_of_order", "Out Of Order"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_lifecycle_events",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_lifecycle_events",
    )
    lifecycle_task = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.CASCADE,
        related_name="events",
    )
    idempotency_key = models.CharField(max_length=255)
    source = models.CharField(max_length=64, blank=True, default="")
    event_type = models.CharField(max_length=64)
    from_status = models.CharField(max_length=32, blank=True, default="")
    to_status = models.CharField(max_length=32, blank=True, default="")
    attempt_number = models.PositiveIntegerField(default=1)
    outcome = models.CharField(max_length=32, choices=OUTCOME_CHOICES)
    reason = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_lifecycle_events"
        ordering = ["occurred_at", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="task_lifecycle_event_org_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["run", "occurred_at"], name="task_life_evt_run_time_idx"),
            models.Index(
                fields=["lifecycle_task", "occurred_at"], name="task_life_evt_task_time_idx"
            ),
            models.Index(fields=["outcome", "occurred_at"], name="task_life_evt_outcome_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.outcome}"


class TaskDeadLetterRecord(models.Model):
    """Operator-visible terminal diagnostics for a lost or poison task."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("acknowledged", "Acknowledged"),
        ("recovered", "Recovered"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lifecycle_task = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.CASCADE,
        related_name="dead_letters",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_dead_letters",
    )
    runtime_intent_outcome = models.ForeignKey(
        RuntimeIntentOutcome,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_dead_letters",
    )
    intent_id = models.UUIDField(null=True, blank=True)
    stream_message_id = models.CharField(max_length=64, blank=True, default="")
    reason = models.TextField()
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    recovery_options = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_task_dead_letters",
    )
    acknowledgement_reason = models.TextField(blank=True, default="")
    recovered_at = models.DateTimeField(null=True, blank=True)
    recovered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recovered_task_dead_letters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_dead_letter_records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run", "status"], name="task_dl_run_status_idx"),
            models.Index(fields=["status", "created_at"], name="task_dl_status_time_idx"),
            models.Index(fields=["intent_id"], name="task_dl_intent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.lifecycle_task_id} dead-lettered"


class RetryOperation(models.Model):
    """Backend-owned visible retry budget for a retryable operation."""

    RETRY_CLASS_CHOICES = [
        ("transport", "Transport"),
        ("backend_rejection", "Backend Rejection"),
        ("llm_backpressure", "LLM Backpressure"),
        ("human_pending", "Human Pending"),
        ("poison_message", "Poison Message"),
        ("duplicate_intent", "Duplicate Intent"),
    ]
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("exhausted", "Exhausted"),
        ("dead_lettered", "Dead Lettered"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="retry_operations",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="retry_operations",
    )
    lifecycle_task = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retry_operations",
    )
    attempt = models.ForeignKey(
        TaskAttemptRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retry_operations",
    )
    operation_type = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255)
    attempt_number = models.PositiveIntegerField(default=1)
    max_attempts = models.PositiveIntegerField(default=1)
    retry_delay_ms = models.PositiveIntegerField(default=0)
    retry_reason = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    owning_component = models.CharField(max_length=64)
    next_scheduled_at = models.DateTimeField(null=True, blank=True)
    terminal_fallback = models.CharField(max_length=64, blank=True, default="")
    retry_class = models.CharField(max_length=32, choices=RETRY_CLASS_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="scheduled")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "retry_operations"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="retry_operations_org_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["run", "status"], name="retry_ops_run_status_idx"),
            models.Index(fields=["retry_class", "status"], name="retry_ops_class_status_idx"),
            models.Index(fields=["next_scheduled_at"], name="retry_ops_next_sched_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.operation_type} attempt {self.attempt_number}/{self.max_attempts}"


class TaskRecord(models.Model):
    """Projected unit of work attached to an execution and agent."""

    STATUS_CHOICES = [
        ("created", "Created"),
        ("queued", "Queued"),
        ("claimed", "Claimed"),
        ("paused", "Paused"),
        ("waiting_for_decision", "Waiting For Decision"),
        ("retry_scheduled", "Retry Scheduled"),
        ("completed", "Completed"),
        ("dead_lettered", "Dead Lettered"),
        ("cancelled", "Cancelled"),
        ("pending", "Pending"),
        ("running", "Running"),
        ("waiting", "Waiting"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_records",
    )
    execution = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_records",
    )
    lifecycle_task = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_records",
    )
    agent = models.ForeignKey(
        "AgentRegistryEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_records",
    )
    department = models.ForeignKey(
        "DepartmentRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_records",
    )
    source_node_id = models.CharField(max_length=255, blank=True, default="")
    external_key = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="created")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="normal")
    summary = models.TextField(blank=True, default="")
    current_step = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_records",
    )
    current_decision = models.ForeignKey(
        "DecisionRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_tasks",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_records"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_key"],
                name="task_records_org_external_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="task_records_org_status_idx"),
            models.Index(fields=["execution", "status"], name="task_rec_exec_stat_idx"),
            models.Index(fields=["agent", "status"], name="task_records_agent_status_idx"),
            models.Index(fields=["department", "status"], name="task_records_dept_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class TaskJudge(models.Model):
    """Backend-owned acceptance judge attached to one operator-facing task."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("passed", "Passed"),
        ("failed", "Failed"),
        ("inconclusive", "Inconclusive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_judges",
    )
    task = models.OneToOneField(
        TaskRecord,
        on_delete=models.CASCADE,
        related_name="judge",
    )
    execution = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="task_judges",
    )
    source_node_id = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=255, blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    criteria_json = models.JSONField(default=list, blank=True)
    pass_threshold = models.PositiveSmallIntegerField(
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    result_json = models.JSONField(default=dict, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_task_judges",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_task_judges",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_judges"
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="task_judges_org_status_idx"),
            models.Index(fields=["execution", "source_node_id"], name="task_judges_exec_node_idx"),
            models.Index(fields=["evaluated_at"], name="task_judges_eval_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title or self.task.title} judge ({self.status})"
