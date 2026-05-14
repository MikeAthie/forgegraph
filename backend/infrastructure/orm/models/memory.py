"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.runtime import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class MemoryEntry(models.Model):
    """MemoryEntry stores key/value memory entries for memory nodes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(max_length=255, default="global")
    key = models.CharField(max_length=255)
    value_json = models.JSONField(default=dict)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_entries"
        indexes = [
            models.Index(fields=["namespace", "key"], name="memory_entries_ns_key_idx"),
            models.Index(fields=["expires_at"], name="memory_entries_exp_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["namespace", "key"], name="memory_entries_ns_key_uniq"),
        ]

    def __str__(self) -> str:
        return f"MemoryEntry {self.namespace}:{self.key}"


class MemoryObservationQuerySet(models.QuerySet["MemoryObservation"]):
    def active(self) -> MemoryObservationQuerySet:
        return self.filter(deleted_at__isnull=True)

    def for_tenant(self, tenant_id: uuid.UUID) -> MemoryObservationQuerySet:
        return self.filter(tenant_id=tenant_id)


class MemoryObservationManager(models.Manager.from_queryset(MemoryObservationQuerySet)):  # type: ignore[misc]
    pass


class MemoryObservation(models.Model):
    """MemoryObservation stores curated, inspectable memory observations."""

    SCOPE_CHOICES = [
        ("graph", "Graph"),
        ("run", "Run"),
        ("session", "Session"),
    ]

    objects = MemoryObservationManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    graph_id = models.UUIDField(null=True, blank=True)
    run_id = models.UUIDField(null=True, blank=True)
    session_id = models.UUIDField(null=True, blank=True)
    agent_id = models.UUIDField(null=True, blank=True)
    type = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    content = models.TextField()
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default="graph")
    topic_key = models.CharField(max_length=128, blank=True, default="")
    tool_name = models.CharField(max_length=128, blank=True, default="")
    source_event_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    source_event_type = models.CharField(max_length=128, blank=True, default="")
    fact_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    provenance_json = models.JSONField(default=dict, blank=True)
    cost_metadata_json = models.JSONField(default=dict, blank=True)
    retention_policy_json = models.JSONField(default=dict, blank=True)
    revision_count = models.PositiveIntegerField(default=1)
    duplicate_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)
    memory_chunk = models.ForeignKey(
        "MemoryChunk",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="observation_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "memory_observations"
        ordering = ["-last_seen_at", "-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "last_seen_at"], name="mem_obs_tenant_seen_idx"),
            models.Index(fields=["tenant_id", "topic_key"], name="mem_obs_tenant_topic_idx"),
            models.Index(
                fields=["tenant_id", "scope", "last_seen_at"], name="mem_obs_scope_seen_idx"
            ),
            models.Index(fields=["tenant_id", "deleted_at"], name="mem_obs_deleted_idx"),
            models.Index(
                fields=["tenant_id", "type", "last_seen_at"], name="mem_obs_type_seen_idx"
            ),
            models.Index(fields=["tenant_id", "source_event_id"], name="mem_obs_source_event_idx"),
            models.Index(fields=["tenant_id", "fact_hash"], name="mem_obs_fact_hash_idx"),
        ]
        constraints = [
            _make_check_constraint(
                ~(
                    models.Q(graph_id__isnull=True)
                    & models.Q(run_id__isnull=True)
                    & models.Q(session_id__isnull=True)
                ),
                name="mem_obs_requires_scope",
            ),
            _make_check_constraint(
                ~(models.Q(scope="graph") & models.Q(graph_id__isnull=True)),
                name="mem_obs_graph_scope_req",
            ),
            _make_check_constraint(
                ~(models.Q(scope="run") & models.Q(run_id__isnull=True)),
                name="mem_obs_run_scope_req",
            ),
            _make_check_constraint(
                ~(models.Q(scope="session") & models.Q(session_id__isnull=True)),
                name="mem_obs_session_scope_req",
            ),
        ]

    def __str__(self) -> str:
        return f"MemoryObservation {self.id} ({self.type})"


class MemoryUsage(models.Model):
    """Daily memory usage totals per tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    usage_date = models.DateField()
    summarization_prompt_tokens = models.PositiveIntegerField(default=0)
    summarization_completion_tokens = models.PositiveIntegerField(default=0)
    summarization_total_tokens = models.PositiveIntegerField(default=0)
    summarization_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_usage"
        ordering = ["-usage_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "usage_date"],
                name="memory_usage_tenant_date_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"MemoryUsage {self.tenant_id} {self.usage_date}"


class LLMUsage(models.Model):
    """LLM usage per prompt node execution."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="llm_usage",
    )
    node_id = models.CharField(max_length=255)
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    external_key = models.CharField(max_length=255, null=True, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "llm_usage"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "created_at"], name="llm_usage_tenant_time_idx"),
            models.Index(fields=["run", "node_id"], name="llm_usage_run_node_idx"),
            models.Index(fields=["tenant_id", "external_key"], name="llm_usage_tenant_ext_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "external_key"],
                condition=models.Q(external_key__isnull=False),
                name="llm_usage_tenant_external_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"LLMUsage {self.run_id} {self.node_id} {self.model}"


class LLMBudget(models.Model):
    """Monthly LLM budget limits per tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    monthly_limit_usd = models.DecimalField(max_digits=12, decimal_places=2)
    warning_threshold_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0.8)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "llm_budgets"

    def __str__(self) -> str:
        return f"LLMBudget {self.tenant_id} ${self.monthly_limit_usd}"


class LLMQuota(models.Model):
    """Monthly LLM usage quotas per tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    monthly_token_limit = models.PositiveIntegerField(null=True, blank=True)
    monthly_cost_limit_usd = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "llm_quotas"

    def __str__(self) -> str:
        return f"LLMQuota {self.tenant_id}"


class AuditLog(models.Model):
    """Append-only audit log entries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=128)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "created_at"], name="audit_logs_tenant_time_idx"),
            models.Index(fields=["action", "created_at"], name="audit_logs_action_time_idx"),
        ]

    def __str__(self) -> str:
        return f"AuditLog {self.action} {self.resource_type} {self.resource_id}"


class OperatorActionLog(models.Model):
    """Append-only operator recovery action log."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_action_logs",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="operator_action_logs",
    )
    action = models.CharField(max_length=96)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=128)
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, default="applied")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "operator_action_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="operator_action_org_time_idx",
            ),
            models.Index(
                fields=["organization", "action", "created_at"],
                name="operator_action_org_action_idx",
            ),
            models.Index(
                fields=["target_type", "target_id"],
                name="operator_action_target_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"OperatorActionLog {self.action} {self.target_type} {self.target_id}"


class ServiceMetricSample(models.Model):
    """Backend-owned operational metric sample used for SLO windows."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric_name = models.CharField(max_length=128)
    source = models.CharField(max_length=64)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_metric_samples",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_metric_samples",
    )
    value = models.FloatField(default=0.0)
    unit = models.CharField(max_length=32, blank=True, default="")
    dimensions = models.JSONField(default=dict, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_metric_samples"
        ordering = ["-observed_at", "-created_at"]
        indexes = [
            models.Index(fields=["metric_name", "observed_at"], name="svc_metric_name_time_idx"),
            models.Index(fields=["source", "observed_at"], name="svc_metric_source_time_idx"),
            models.Index(
                fields=["organization", "metric_name", "observed_at"],
                name="svc_metric_org_name_time_idx",
            ),
            models.Index(fields=["run", "metric_name"], name="svc_metric_run_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.metric_name}={self.value} {self.unit}".strip()


class TenantPolicy(models.Model):
    """Per-tenant guardrail policy for egress and LLM usage."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    http_allowlist = models.JSONField(default=list, blank=True)
    http_denylist = models.JSONField(default=list, blank=True)
    http_default_deny = models.BooleanField(default=False)
    allowed_providers = models.JSONField(default=list, blank=True)
    allowed_models = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_policies"

    def __str__(self) -> str:
        return f"TenantPolicy {self.tenant_id}"


class TenantRetentionPolicy(models.Model):
    """Per-tenant data retention policy for runs, logs, and audit data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    runs_retention_days = models.PositiveIntegerField(null=True, blank=True)
    run_logs_retention_days = models.PositiveIntegerField(null=True, blank=True)
    audit_logs_retention_days = models.PositiveIntegerField(null=True, blank=True)
    usage_retention_days = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_retention_policies"

    def __str__(self) -> str:
        return f"TenantRetentionPolicy {self.tenant_id}"


class OIDCProvider(models.Model):
    """OIDC provider configuration per tenant (Auth0)."""

    PROVIDER_CHOICES = [
        ("auth0", "Auth0"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, default="auth0")
    issuer_url = models.URLField()
    client_id = models.CharField(max_length=255)
    encrypted_client_secret = models.BinaryField()
    audience = models.CharField(max_length=255, blank=True, default="")
    email_domains = models.JSONField(default=list, blank=True)
    default_role = models.CharField(max_length=16, choices=OrganizationMembership.ROLE_CHOICES)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "oidc_providers"

    def __str__(self) -> str:
        return f"OIDCProvider {self.provider} {self.tenant_id}"

    @property
    def client_secret(self) -> str:
        from infrastructure.crypto.encryption import decrypt_api_key

        return decrypt_api_key(bytes(self.encrypted_client_secret))


class IntegrationOAuthProviderConfig(models.Model):
    """Tenant-scoped OAuth app configuration for third-party integrations."""

    PROVIDER_CHOICES = [
        ("gmail", "Gmail"),
        ("google_calendar", "Google Calendar"),
        ("google_tasks", "Google Tasks"),
        ("notion", "Notion"),
        ("slack", "Slack"),
        ("jira", "Jira"),
        ("linear", "Linear"),
        ("hubspot", "HubSpot"),
        ("google_drive", "Google Drive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    client_id = models.CharField(max_length=255)
    encrypted_client_secret = models.BinaryField()
    authorize_url = models.URLField()
    token_url = models.URLField()
    redirect_uri = models.URLField(blank=True, default="")
    scopes = models.JSONField(default=list, blank=True)
    authorize_extra_params = models.JSONField(default=dict, blank=True)
    token_extra_params = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integration_oauth_provider_configs"
        unique_together = [["tenant_id", "provider"]]
        indexes = [
            models.Index(fields=["tenant_id", "provider"], name="int_oauth_tenant_provider_idx"),
            models.Index(fields=["tenant_id", "enabled"], name="int_oauth_tenant_enabled_idx"),
        ]

    def __str__(self) -> str:
        return f"IntegrationOAuthProviderConfig {self.tenant_id} {self.provider}"

    @property
    def client_secret(self) -> str:
        from infrastructure.crypto.encryption import decrypt_api_key

        return decrypt_api_key(bytes(self.encrypted_client_secret))


class SCIMToken(models.Model):
    """SCIM bearer token per tenant (stored as hash)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    token_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "scim_tokens"

    def __str__(self) -> str:
        return f"SCIMToken {self.tenant_id}"
