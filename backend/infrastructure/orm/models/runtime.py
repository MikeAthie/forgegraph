"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.graphs import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class Run(models.Model):
    """Run model representing an execution of a graph."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("resume_requested", "Resume Requested"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]
    RECOVERY_POLICY_CHOICES = [
        ("fail", "Fail"),
        ("retry", "Retry"),
        ("resume", "Resume"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="runs",
    )
    thread_id = models.UUIDField(null=True, blank=True)
    graph_version = models.ForeignKey(
        GraphVersion,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    input_json = models.JSONField(default=dict, blank=True)
    dispatch_graph_json = models.JSONField(null=True, blank=True)
    output_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    trace_id = models.CharField(max_length=32, blank=True, default="")
    last_progress_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    engine_instance_id = models.CharField(max_length=64, blank=True, default="")
    recovery_state = models.CharField(max_length=32, blank=True, default="idle")
    recovery_reason = models.CharField(max_length=64, blank=True, default="")
    recovery_policy = models.CharField(
        max_length=16,
        choices=RECOVERY_POLICY_CHOICES,
        default="fail",
    )
    resume_requested_at = models.DateTimeField(null=True, blank=True)
    resume_attempt_id = models.UUIDField(null=True, blank=True)

    # Human Gate pause state (for durable resume)
    pause_state_json = models.JSONField(null=True, blank=True)
    paused_node_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["owner", "started_at"], name="runs_owner_started_idx"),
            models.Index(fields=["owner", "status"], name="runs_owner_status_idx"),
            models.Index(fields=["owner", "thread_id"], name="runs_owner_thread_idx"),
            models.Index(fields=["organization", "started_at"], name="runs_org_started_idx"),
            models.Index(fields=["organization", "status"], name="runs_org_status_idx"),
            models.Index(fields=["organization", "thread_id"], name="runs_org_thread_idx"),
            models.Index(fields=["trace_id"], name="runs_trace_id_idx"),
            models.Index(fields=["last_progress_at"], name="runs_progress_idx"),
            models.Index(fields=["recovery_state"], name="runs_recovery_state_idx"),
        ]

    def __str__(self) -> str:
        return f"Run {self.id} - {self.status}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.organization_id:
            if self.graph_version_id:
                self.organization_id = (
                    GraphVersion.objects.filter(pk=self.graph_version_id)
                    .values_list("graph__organization_id", flat=True)
                    .first()
                )
            if not self.organization_id and self.owner_id:
                self.organization_id = (
                    User.objects.filter(pk=self.owner_id)
                    .values_list(
                        "default_organization_id",
                        flat=True,
                    )
                    .first()
                )
        super().save(*args, **kwargs)

    @property
    def duration_ms(self) -> int | None:
        """Calculate run duration in milliseconds."""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def authoritative_attempt_id(self) -> str:
        from application.services.run_snapshots import get_snapshot

        try:
            snapshot = get_snapshot(self.id)
        except Exception:
            snapshot = None
        if snapshot is not None:
            attempt_id = str(snapshot.attempt_id or "").strip()
            if attempt_id:
                return attempt_id

        if self.resume_attempt_id is not None:
            return str(self.resume_attempt_id)

        metadata = (
            self.dispatch_graph_json.get("metadata")
            if isinstance(self.dispatch_graph_json, dict)
            else None
        )
        if isinstance(metadata, dict):
            backend_attempt_id = str(metadata.get("backend_attempt_id") or "").strip()
            if backend_attempt_id:
                return backend_attempt_id

        processed_attempt_id = (
            ProcessedRuntimeIntent.objects.filter(run=self)
            .exclude(attempt_id="")
            .order_by("-processed_at")
            .values_list("attempt_id", flat=True)
            .first()
        )
        if isinstance(processed_attempt_id, str) and processed_attempt_id.strip():
            return processed_attempt_id.strip()

        return ""

    @property
    def active_attempt_id(self) -> str:
        attempt_id = self.authoritative_attempt_id
        if attempt_id:
            return attempt_id

        return f"backend-attempt-{self.id}"


class RunQueueEntry(models.Model):
    """Queue entry for run execution."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        related_name="queue_entry",
    )
    tenant_id = models.UUIDField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    priority = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    available_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "run_queue"
        indexes = [
            models.Index(fields=["status", "available_at"], name="run_queue_status_idx"),
            models.Index(fields=["tenant_id", "status"], name="run_queue_tenant_idx"),
            models.Index(fields=["locked_at"], name="run_queue_locked_idx"),
        ]

    def __str__(self) -> str:
        return f"RunQueueEntry {self.run_id} - {self.status}"


class RunEvent(models.Model):
    """RunEvent model storing execution events for observability."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Idempotency key from engine events (event_id).",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    trace_id = models.CharField(max_length=32, blank=True, default="")
    span_id = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "run_events"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["run", "created_at"], name="run_events_run_time_idx"),
            models.Index(fields=["run", "external_id"], name="run_events_run_external_idx"),
            models.Index(fields=["trace_id"], name="run_events_trace_id_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "external_id"],
                name="run_events_run_external_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"RunEvent {self.run_id} - {self.event_type}"


class StateFeedEvent(models.Model):
    """Versioned backend state-feed event retained for WebSocket replay."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="state_feed_events",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="state_feed_events",
    )
    event_id = models.CharField(max_length=128)
    state_version = models.PositiveBigIntegerField()
    type = models.CharField(max_length=96)
    level = models.CharField(max_length=16, blank=True, default="")
    requires_refetch = models.BooleanField(default=False)
    message = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "state_feed_events"
        ordering = ["state_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "state_version"],
                name="state_feed_run_version_uniq",
            ),
            models.UniqueConstraint(
                fields=["run", "event_id"],
                name="state_feed_run_event_id_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "run", "state_version"],
                name="state_feed_org_run_ver_idx",
            ),
            models.Index(fields=["run", "created_at"], name="state_feed_run_created_idx"),
            models.Index(
                fields=["organization", "created_at"],
                name="state_feed_org_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"StateFeedEvent {self.run_id} v{self.state_version} {self.type}"


class OrganizationStateFeedSequence(models.Model):
    """Per-organization allocator for Command Ops state-feed versions."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="state_feed_sequence",
    )
    next_sequence = models.BigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_state_feed_sequences"

    def __str__(self) -> str:
        return f"{self.organization_id} next={self.next_sequence}"


class OrganizationStateFeedEvent(models.Model):
    """Versioned organization notification retained for Command Ops replay."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="organization_state_feed_events",
    )
    event_id = models.CharField(max_length=128)
    state_version = models.PositiveBigIntegerField()
    type = models.CharField(max_length=96)
    resource_type = models.CharField(max_length=64, blank=True, default="")
    resource_id = models.CharField(max_length=128, blank=True, default="")
    requires_refetch = models.BooleanField(default=True)
    message = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization_state_feed_events"
        ordering = ["organization_id", "state_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "state_version"],
                name="org_state_feed_org_version_uniq",
            ),
            models.UniqueConstraint(
                fields=["organization", "event_id"],
                name="org_state_feed_org_event_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "state_version"],
                name="org_state_feed_org_ver_idx",
            ),
            models.Index(
                fields=["organization", "type", "state_version"],
                name="org_state_feed_type_ver_idx",
            ),
            models.Index(
                fields=["organization", "resource_type", "resource_id"],
                name="org_state_feed_resource_idx",
            ),
            models.Index(
                fields=["organization", "created_at"],
                name="org_state_feed_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"OrganizationStateFeedEvent {self.organization_id} v{self.state_version} {self.type}"
        )


class OrganizationDomainEventSequence(models.Model):
    """Per-organization allocator for backend-authored domain event sequences."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="domain_event_sequence",
    )
    next_sequence = models.BigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_domain_event_sequences"

    def __str__(self) -> str:
        return f"{self.organization_id} next={self.next_sequence}"


class DomainEvent(models.Model):
    """Backend-owned durable projection event derived from committed backend writes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="domain_events",
    )
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=128)
    event_version = models.IntegerField(default=1)
    sequence = models.BigIntegerField()
    idempotency_key = models.CharField(max_length=255, unique=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "domain_events"
        ordering = ["organization_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sequence"],
                name="domain_events_org_sequence_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "sequence"], name="domain_events_org_seq_idx"),
            models.Index(fields=["tenant_id", "event_type"], name="domain_events_tenant_type_idx"),
            models.Index(
                fields=["aggregate_type", "aggregate_id", "sequence"],
                name="domain_events_agg_seq_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.organization_id}#{self.sequence}"


class DomainEventOutbox(models.Model):
    """Durable, retryable outbound event row for backend-authored domain events."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("published", "Published"),
        ("failed", "Failed"),
        ("deferred", "Deferred"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    domain_event = models.ForeignKey(
        DomainEvent,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="outbox_events",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="domain_event_outbox",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="domain_event_outbox",
    )
    event_type = models.CharField(max_length=128)
    schema_version = models.CharField(max_length=64)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.UUIDField(db_index=True)
    visibility = models.CharField(max_length=32, blank=True, default="")
    topic = models.CharField(max_length=255)
    payload_json = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    publish_attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "domain_event_outbox"
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at", "created_at"],
                name="domain_outbox_due_idx",
            ),
            models.Index(
                fields=["organization", "status", "created_at"],
                name="domain_outbox_org_status_idx",
            ),
            models.Index(
                fields=["topic", "status", "created_at"],
                name="domain_outbox_topic_status_idx",
            ),
            models.Index(fields=["event_type", "created_at"], name="domain_outbox_type_time_idx"),
            models.Index(fields=["domain_event"], name="domain_outbox_event_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.topic} {self.event_type} {self.status}"


class ProjectionCursor(models.Model):
    """Per-organization cursor for one materialized projection."""

    STATUS_CHOICES = [
        ("fresh", "Fresh"),
        ("stale", "Stale"),
        ("rebuilding", "Rebuilding"),
        ("degraded", "Degraded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    projection_name = models.CharField(max_length=128)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projection_cursors",
    )
    last_sequence = models.BigIntegerField(default=0)
    last_event_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="fresh")
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projection_cursors"
        ordering = ["projection_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["projection_name", "organization"],
                name="projection_cursor_name_org_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "projection_name"],
                name="projection_cursor_org_name_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.projection_name} {self.organization_id}#{self.last_sequence}"


class ProcessedProjectionEvent(models.Model):
    """Idempotency marker for projection handlers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    projection_name = models.CharField(max_length=128)
    event = models.ForeignKey(
        DomainEvent,
        on_delete=models.CASCADE,
        related_name="processed_projection_events",
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_projection_events"
        ordering = ["-processed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["projection_name", "event"],
                name="uniq_projection_event_once",
            )
        ]

    def __str__(self) -> str:
        return f"{self.projection_name} {self.event_id}"


class ProcessedRuntimeIntent(models.Model):
    """ProcessedRuntimeIntent records backend-applied runtime write intents."""

    intent_id = models.UUIDField(primary_key=True)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="processed_runtime_intents",
    )
    intent_type = models.CharField(max_length=64)
    attempt_id = models.CharField(max_length=64, blank=True, default="")
    trace_id = models.CharField(max_length=32, blank=True, default="")
    stream_message_id = models.CharField(max_length=64, blank=True, default="")
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_runtime_intents"
        ordering = ["processed_at"]
        indexes = [
            models.Index(fields=["run", "processed_at"], name="rt_intents_run_time_idx"),
            models.Index(fields=["intent_type", "processed_at"], name="rt_intents_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"ProcessedRuntimeIntent {self.intent_type} {self.intent_id}"


class ProcessedCommand(models.Model):
    """ProcessedCommand records idempotent HTTP mutation responses."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="processed_commands",
    )
    idempotency_key = models.CharField(max_length=255)
    action = models.CharField(max_length=96)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    resource_type = models.CharField(max_length=64, blank=True, default="")
    resource_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processed_commands"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "action", "idempotency_key"],
                name="processed_cmd_org_action_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="processed_cmd_org_time_idx"),
            models.Index(
                fields=["organization", "resource_type", "resource_id"],
                name="processed_cmd_resource_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"ProcessedCommand {self.action} {self.idempotency_key}"


class ProcessedCallbackEvent(models.Model):
    """ProcessedCallbackEvent records backend-applied engine callback events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="processed_callback_events",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="processed_callback_events",
    )
    event_id = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    event_type = models.CharField(max_length=96)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(default=dict, blank=True)
    resource_type = models.CharField(max_length=64, blank=True, default="")
    resource_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=32, default="applied")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processed_callback_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "event_id"],
                name="processed_callback_run_event_uniq",
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="processed_callback_org_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="processed_cb_org_time_idx",
            ),
            models.Index(fields=["event_type", "created_at"], name="processed_cb_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"ProcessedCallbackEvent {self.event_type} {self.event_id}"


class ProcessedDecisionSubmission(models.Model):
    """ProcessedDecisionSubmission records backend-applied human decisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="processed_decision_submissions",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="processed_decision_submissions",
    )
    approval_task = models.ForeignKey(
        "ApprovalTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_submissions",
    )
    submit_id = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    resume_attempt_id = models.UUIDField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, default="applied")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processed_decision_submissions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "submit_id"],
                name="processed_decision_org_submit_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["run", "created_at"], name="processed_dec_run_time_idx"),
            models.Index(
                fields=["approval_task", "created_at"],
                name="processed_dec_task_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"ProcessedDecisionSubmission {self.submit_id}"


class ProcessedAccountingEvent(models.Model):
    """ProcessedAccountingEvent records backend-applied usage/cost events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="processed_accounting_events",
    )
    event_key = models.CharField(max_length=255)
    event_type = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64, blank=True, default="")
    llm_usage = models.ForeignKey(
        "LLMUsage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_accounting_events",
    )
    memory_usage = models.ForeignKey(
        "MemoryUsage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_accounting_events",
    )
    cost_ledger_entry = models.ForeignKey(
        "CostLedgerEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_accounting_events",
    )
    status = models.CharField(max_length=32, default="applied")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processed_accounting_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "event_key"],
                name="processed_accounting_org_key_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="processed_acct_org_time_idx",
            ),
            models.Index(fields=["event_type", "created_at"], name="processed_acct_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"ProcessedAccountingEvent {self.event_type} {self.event_key}"


class ProcessedMemoryEvent(models.Model):
    """ProcessedMemoryEvent records backend-applied memory writes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="processed_memory_events",
    )
    event_id = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    event_type = models.CharField(max_length=96)
    request_hash = models.CharField(max_length=64)
    observation_ids_json = models.JSONField(default=list, blank=True)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, default="applied")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processed_memory_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "event_id"],
                name="processed_memory_org_event_uniq",
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="processed_memory_org_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="processed_mem_org_time_idx"),
            models.Index(fields=["event_type", "created_at"], name="processed_mem_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"ProcessedMemoryEvent {self.event_type} {self.event_id}"


class RuntimeIntentOutcome(models.Model):
    """Backend-owned processing outcome for a runtime write intent."""

    OUTCOME_CHOICES = [
        ("processed", "Processed"),
        ("duplicate", "Duplicate"),
        ("ignored", "Ignored"),
        ("invalid", "Invalid"),
        ("dead_lettered", "Dead Lettered"),
    ]

    intent_id = models.UUIDField(primary_key=True)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="runtime_intent_outcomes",
        null=True,
        blank=True,
    )
    intent_type = models.CharField(max_length=64, blank=True, default="")
    attempt_id = models.CharField(max_length=64, blank=True, default="")
    outcome = models.CharField(max_length=32, choices=OUTCOME_CHOICES)
    reason = models.TextField(blank=True, default="")
    error_class = models.CharField(max_length=128, blank=True, default="")
    trace_id = models.CharField(max_length=32, blank=True, default="")
    stream_message_id = models.CharField(max_length=64, blank=True, default="")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_runtime_intent_outcomes",
    )
    acknowledgement_reason = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "runtime_intent_outcomes"
        ordering = ["processed_at"]
        indexes = [
            models.Index(fields=["run", "processed_at"], name="rt_outcomes_run_time_idx"),
            models.Index(fields=["outcome", "processed_at"], name="rt_outcomes_status_time_idx"),
            models.Index(fields=["intent_type", "processed_at"], name="rt_outcomes_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"RuntimeIntentOutcome {self.outcome} {self.intent_id}"


class EventDeadLetterRecord(models.Model):
    """Operator-visible diagnostics for backend event ingestion failures."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("acknowledged", "Acknowledged"),
        ("replay_requested", "Replay Requested"),
        ("resolved", "Resolved"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="event_dead_letters",
        null=True,
        blank=True,
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="event_dead_letters",
        null=True,
        blank=True,
    )
    event_id = models.CharField(max_length=128, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    event_type = models.CharField(max_length=96, blank=True, default="")
    source = models.CharField(max_length=64, default="engine_callback")
    reason = models.TextField()
    error_class = models.CharField(max_length=128, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    retry_count = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    last_replay_action = models.TextField(blank=True, default="")
    replay_requested_at = models.DateTimeField(null=True, blank=True)
    replay_requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replay_requested_event_dead_letters",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_event_dead_letters",
    )
    acknowledgement_reason = models.TextField(blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "event_dead_letter_records"
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(
                fields=["organization", "status", "last_seen_at"],
                name="event_dl_org_status_time_idx",
            ),
            models.Index(fields=["run", "status"], name="event_dl_run_status_idx"),
            models.Index(fields=["event_id"], name="event_dl_event_id_idx"),
            models.Index(fields=["source", "last_seen_at"], name="event_dl_source_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.event_type or 'event'} dead-lettered"


class ToolExecution(models.Model):
    """Backend-owned execution identity for one logical external tool operation."""

    SIDE_EFFECT_CLASS_CHOICES = [
        ("pure", "Pure"),
        ("idempotent", "Idempotent"),
        ("non_idempotent", "Non-Idempotent"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [
        ("planned", "Planned"),
        ("in_progress", "In Progress"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("ambiguous", "Ambiguous"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="tool_executions",
    )
    node_id = models.CharField(max_length=255)
    attempt_id = models.CharField(max_length=64)
    tool_name = models.CharField(max_length=128)
    tool_version = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=128)
    side_effect_class = models.CharField(
        max_length=32,
        choices=SIDE_EFFECT_CLASS_CHOICES,
        default="non_idempotent",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="planned")
    result_json = models.JSONField(blank=True, default=dict)
    error_json = models.JSONField(blank=True, default=dict)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tool_executions"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "node_id", "attempt_id"],
                name="tool_exec_run_node_attempt_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["run", "status"], name="tool_exec_run_status_idx"),
            models.Index(fields=["idempotency_key"], name="tool_exec_idem_key_idx"),
            models.Index(fields=["tool_name", "tool_version"], name="tool_exec_tool_idx"),
        ]

    def __str__(self) -> str:
        return f"ToolExecution {self.id} {self.tool_name}@{self.tool_version} - {self.status}"


class RunEventProjection(models.Model):
    """Event-derived shadow state for validating run reconstruction completeness."""

    run = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        related_name="event_projection",
        primary_key=True,
    )
    status = models.CharField(max_length=16, choices=Run.STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    output_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    pause_state_json = models.JSONField(null=True, blank=True)
    paused_node_id = models.CharField(max_length=64, null=True, blank=True)
    trace_id = models.CharField(max_length=32, blank=True, default="")
    last_event_id = models.CharField(max_length=64, blank=True, default="")
    last_event_type = models.CharField(max_length=64, blank=True, default="")
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "run_event_projections"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "updated_at"], name="run_evt_proj_status_idx"),
            models.Index(fields=["trace_id"], name="run_evt_proj_trace_idx"),
            models.Index(fields=["last_event_at"], name="run_evt_proj_event_at_idx"),
        ]

    def __str__(self) -> str:
        return f"RunEventProjection {self.run_id} - {self.status}"


class NodeRunEventProjection(models.Model):
    """Event-derived shadow state for validating node reconstruction completeness."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("waiting", "Waiting"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="node_event_projections",
    )
    node_id = models.CharField(max_length=255)
    node_type = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    attempt = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    output_json = models.JSONField(null=True, blank=True)
    error_json = models.JSONField(null=True, blank=True)
    trace_id = models.CharField(max_length=32, blank=True, default="")
    span_id = models.CharField(max_length=16, blank=True, default="")
    last_event_id = models.CharField(max_length=64, blank=True, default="")
    last_event_type = models.CharField(max_length=64, blank=True, default="")
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "node_run_event_projections"
        ordering = ["started_at", "attempt"]
        indexes = [
            models.Index(
                fields=["run", "started_at", "attempt"],
                name="node_evt_proj_run_time_idx",
            ),
            models.Index(fields=["trace_id"], name="node_evt_proj_trace_idx"),
            models.Index(fields=["last_event_at"], name="node_evt_proj_event_at_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "node_id", "attempt"],
                name="node_evt_proj_run_node_attempt_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"NodeRunEventProjection {self.run_id} {self.node_id}#{self.attempt} - {self.status}"
