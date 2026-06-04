"""Backend-owned gateway connector runtime state."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.credentials import *  # noqa: F403
from infrastructure.orm.models.graphs import *  # noqa: F403
from infrastructure.orm.models.runtime import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403


class GatewayConnection(models.Model):
    """Durable configuration and liveness state for one gateway connector."""

    STATUS_CHOICES = [
        ("enabled", "Enabled"),
        ("disabled", "Disabled"),
        ("degraded", "Degraded"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_connections",
    )
    graph_version = models.ForeignKey(
        GraphVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_connections",
    )
    credential = models.ForeignKey(
        APIKey,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_connections",
    )
    platform = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    name = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="enabled")
    config_json = models.JSONField(default=dict, blank=True)
    allowlist_json = models.JSONField(default=list, blank=True)
    webhook_secret_hash = models.CharField(max_length=128, blank=True, default="")
    verify_token_hash = models.CharField(max_length=128, blank=True, default="")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=96, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_connections"
        indexes = [
            models.Index(fields=["organization", "platform"], name="gw_conn_org_platform_idx"),
            models.Index(fields=["organization", "status"], name="gw_conn_org_status_idx"),
            models.Index(fields=["credential"], name="gw_conn_credential_idx"),
            models.Index(fields=["graph_version"], name="gw_conn_graphver_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "provider", "name"],
                name="gw_conn_org_platform_provider_name_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"GatewayConnection({self.organization_id}, {self.platform}, {self.provider})"


class GatewayConversation(models.Model):
    """Backend-owned mapping from provider conversation ids to ForgeGraph threads."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_conversations",
    )
    connection = models.ForeignKey(
        GatewayConnection,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    graph_version = models.ForeignKey(
        GraphVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_conversations",
    )
    platform = models.CharField(max_length=64)
    external_conversation_id = models.CharField(max_length=255)
    thread_id = models.UUIDField(db_index=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_conversations"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "external_conversation_id"],
                name="gw_conv_org_platform_external_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "thread_id"], name="gw_conv_org_thread_idx"),
            models.Index(fields=["connection", "updated_at"], name="gw_conv_conn_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayConversation({self.platform}:{self.external_conversation_id})"


class GatewayInboundReceipt(models.Model):
    """Durable idempotency receipt for inbound gateway events."""

    STATUS_CHOICES = [
        ("received", "Received"),
        ("processing", "Processing"),
        ("accepted", "Accepted"),
        ("ignored", "Ignored"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_inbound_receipts",
    )
    connection = models.ForeignKey(
        GatewayConnection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inbound_receipts",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_inbound_receipts",
    )
    platform = models.CharField(max_length=64)
    provider = models.CharField(max_length=64, blank=True, default="")
    external_event_id = models.CharField(max_length=255)
    external_conversation_id = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="received")
    event_json = models.JSONField(default=dict, blank=True)
    error_json = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_inbound_receipts"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "idempotency_key"],
                name="gw_inbound_org_platform_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="gw_inbound_org_status_idx"),
            models.Index(fields=["connection", "received_at"], name="gw_inbound_conn_recv_idx"),
            models.Index(fields=["run"], name="gw_inbound_run_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayInboundReceipt({self.platform}:{self.idempotency_key})"


class GatewayPollCursor(models.Model):
    """Backend-owned poll/stream cursor for gateway connectors."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_poll_cursors",
    )
    connection = models.ForeignKey(
        GatewayConnection,
        on_delete=models.CASCADE,
        related_name="poll_cursors",
    )
    platform = models.CharField(max_length=64)
    cursor_key = models.CharField(max_length=128)
    cursor_value = models.CharField(max_length=512, blank=True, default="")
    state_json = models.JSONField(default=dict, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_poll_cursors"
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "cursor_key"],
                name="gw_cursor_connection_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "platform"], name="gw_cursor_org_platform_idx"),
            models.Index(fields=["connection", "updated_at"], name="gw_cursor_conn_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayPollCursor({self.platform}:{self.cursor_key})"


class GatewayConnectorCapability(models.Model):
    """Reviewed backend capability metadata for one gateway provider."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    display_name = models.CharField(max_length=120)
    credential_provider = models.CharField(max_length=64, blank=True, default="")
    runtime_tool_id = models.CharField(max_length=128, blank=True, default="")
    capabilities_json = models.JSONField(default=dict, blank=True)
    setup_requirements_json = models.JSONField(default=list, blank=True)
    inbound_modes_json = models.JSONField(default=list, blank=True)
    outbound_modes_json = models.JSONField(default=list, blank=True)
    sidecar_required = models.BooleanField(default=False)
    sidecar_health_path = models.CharField(max_length=255, blank=True, default="")
    docs_url = models.URLField(blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_connector_capabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "provider"],
                name="gw_cap_platform_provider_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["enabled", "platform"], name="gw_cap_enabled_platform_idx"),
            models.Index(fields=["credential_provider"], name="gw_cap_credential_idx"),
            models.Index(fields=["runtime_tool_id"], name="gw_cap_tool_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayConnectorCapability({self.platform}:{self.provider})"


class GatewayMediaArtifact(models.Model):
    """Sanitized backend reference for gateway attachment/media evidence."""

    DIRECTION_CHOICES = [
        ("inbound", "Inbound"),
        ("outbound", "Outbound"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_media_artifacts",
    )
    connection = models.ForeignKey(
        GatewayConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_artifacts",
    )
    inbound_receipt = models.ForeignKey(
        GatewayInboundReceipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_artifacts",
    )
    tool_execution = models.ForeignKey(
        ToolExecution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_media_artifacts",
    )
    asset = models.ForeignKey(
        "Asset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_media_artifacts",
    )
    asset_version = models.ForeignKey(
        "AssetVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_media_artifacts",
    )
    transcript_observation = models.ForeignKey(
        "MemoryObservation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_media_artifacts",
    )
    platform = models.CharField(max_length=64)
    provider = models.CharField(max_length=64, blank=True, default="")
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    media_kind = models.CharField(max_length=32, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    source_id_hash = models.CharField(max_length=96, blank=True, default="")
    content_sha256 = models.CharField(max_length=96, blank=True, default="")
    filename_hint = models.CharField(max_length=255, blank=True, default="")
    storage_ref = models.CharField(max_length=255, blank=True, default="")
    external_media_id = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gateway_media_artifacts"
        indexes = [
            models.Index(fields=["organization", "platform"], name="gw_media_org_platform_idx"),
            models.Index(fields=["connection", "created_at"], name="gw_media_conn_time_idx"),
            models.Index(fields=["inbound_receipt"], name="gw_media_receipt_idx"),
            models.Index(fields=["tool_execution"], name="gw_media_tool_idx"),
            models.Index(fields=["source_id_hash"], name="gw_media_source_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayMediaArtifact({self.platform}:{self.direction}:{self.id})"


class GatewayAutomationSchedule(models.Model):
    """Backend-owned recurrence state for gateway-triggered automations."""

    STATUS_CHOICES = [
        ("enabled", "Enabled"),
        ("disabled", "Disabled"),
        ("error", "Error"),
    ]
    SCHEDULE_TYPE_CHOICES = [
        ("once", "Once"),
        ("interval", "Interval"),
        ("cron", "Cron"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gateway_automation_schedules",
    )
    graph_version = models.ForeignKey(
        GraphVersion,
        on_delete=models.CASCADE,
        related_name="gateway_automation_schedules",
    )
    connection = models.ForeignKey(
        GatewayConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_schedules",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_automation_schedules",
    )
    last_materialized_run = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_automation_schedules",
    )
    platform = models.CharField(max_length=64)
    provider = models.CharField(max_length=64, blank=True, default="")
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="enabled")
    schedule_type = models.CharField(max_length=16, choices=SCHEDULE_TYPE_CHOICES)
    schedule_json = models.JSONField(default=dict, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default="UTC")
    input_template_json = models.JSONField(default=dict, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_fire_key = models.CharField(max_length=255, blank=True, default="")
    last_error_code = models.CharField(max_length=96, blank=True, default="")
    last_error_message = models.TextField(blank=True, default="")
    last_error_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_automation_schedules"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="gw_schedule_org_name_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="gw_sched_org_status_idx"),
            models.Index(fields=["status", "next_run_at"], name="gw_sched_due_idx"),
            models.Index(fields=["connection", "status"], name="gw_sched_conn_status_idx"),
            models.Index(fields=["last_materialized_run"], name="gw_sched_last_run_idx"),
        ]

    def __str__(self) -> str:
        return f"GatewayAutomationSchedule({self.organization_id}:{self.name})"
