"""
Django ORM models.

Clean Architecture: Frameworks & Drivers layer.
These models map to database tables and implement Django's ORM.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from pgvector.django import IvfflatIndex, VectorField

if TYPE_CHECKING:
    from django.db.models.manager import BaseManager


class UserManager(BaseUserManager["User"]):
    """Custom user manager that uses email as the unique identifier."""

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        """Create and save a regular user."""
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        """Create and save a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model with email as the primary identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # type: ignore[assignment]  # Remove username field
    email = models.EmailField("email address", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects: UserManager = UserManager()  # type: ignore[assignment]

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return str(self.email)


class GraphQuerySet(models.QuerySet["Graph"]):
    def for_user(self, user: "User") -> "GraphQuerySet":
        return self.filter(owner=user)


class GraphManager(models.Manager.from_queryset(GraphQuerySet)):  # type: ignore[misc]
    pass


class GraphVersionQuerySet(models.QuerySet["GraphVersion"]):
    def latest_for_graph(self, graph_id: uuid.UUID) -> "GraphVersion | None":
        return self.filter(graph_id=graph_id).order_by("-version").first()


class GraphVersionManager(models.Manager.from_queryset(GraphVersionQuerySet)):  # type: ignore[misc]
    pass


class PromptTemplateQuerySet(models.QuerySet["PromptTemplate"]):
    def public(self) -> "PromptTemplateQuerySet":
        return self.filter(visibility="public")

    def for_user(self, user: "User") -> "PromptTemplateQuerySet":
        return self.filter(models.Q(owner=user) | models.Q(visibility="public"))


class PromptTemplateManager(models.Manager.from_queryset(PromptTemplateQuerySet)):  # type: ignore[misc]
    pass


class Graph(models.Model):
    """Graph model representing a workflow graph."""

    objects = GraphManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="graphs",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "graphs"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner.email})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_create = self._state.adding
        prev_updated = None
        if not is_create and self.pk:
            prev_updated = (
                Graph.objects.filter(pk=self.pk).values_list("updated_at", flat=True).first()
            )

        super().save(*args, **kwargs)

        if is_create:
            latest = (
                Graph.objects.exclude(pk=self.pk)
                .order_by("-updated_at")
                .values_list("updated_at", flat=True)
                .first()
            )
            if latest and self.updated_at <= latest:
                bumped = latest + timedelta(microseconds=1)
                Graph.objects.filter(pk=self.pk).update(updated_at=bumped)
                self.updated_at = bumped
        elif prev_updated and self.updated_at <= prev_updated:
            bumped = prev_updated + timedelta(microseconds=1)
            Graph.objects.filter(pk=self.pk).update(updated_at=bumped)
            self.updated_at = bumped


class MemoryConfiguration(models.Model):
    """Memory configuration for graphs or user defaults."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    graph = models.OneToOneField(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memory_config",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="default_memory_config",
    )

    # Tier 1: Local Buffer
    buffer_enabled = models.BooleanField(default=True)
    buffer_size = models.PositiveIntegerField(default=20)
    auto_prepend = models.BooleanField(default=True)

    # Tier 2: Redis
    redis_enabled = models.BooleanField(default=False)
    redis_summary_ttl = models.PositiveIntegerField(default=86400)
    redis_facts_ttl = models.PositiveIntegerField(default=604800)

    # Tier 3: Vector (Phase 3)
    vector_enabled = models.BooleanField(default=False)
    vector_top_k = models.PositiveIntegerField(default=5)
    vector_threshold = models.FloatField(default=0.7)
    vector_recency_weight = models.FloatField(default=0.2)
    embedding_model = models.CharField(max_length=50, default="text-embedding-ada-002")
    summarization_enabled = models.BooleanField(default=False)
    summarization_threshold = models.PositiveIntegerField(default=30)
    summarization_keep_recent = models.PositiveIntegerField(default=10)
    summarization_model = models.CharField(max_length=50, default="gpt-4")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_configurations"
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(graph__isnull=True) & models.Q(user__isnull=True)),
                name="memory_config_requires_scope",
            ),
            models.CheckConstraint(
                condition=~(models.Q(graph__isnull=False) & models.Q(user__isnull=False)),
                name="memory_config_single_scope",
            ),
        ]

    def __str__(self) -> str:
        scope = "graph" if self.graph_id else "user"
        return f"MemoryConfiguration({scope}:{self.id})"


class MemorySession(models.Model):
    """MemorySession tracks cross-run shared memory buffers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.UUIDField(unique=True, db_index=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memory_sessions",
    )
    agent_id = models.UUIDField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_sessions"
        indexes = [
            models.Index(fields=["owner", "session_id"], name="memory_sessions_owner_idx"),
        ]

    def __str__(self) -> str:
        return f"MemorySession({self.session_id})"


class GraphVersion(models.Model):
    """GraphVersion model representing a specific version of a graph."""

    objects = GraphVersionManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    graph_json = models.JSONField()
    checksum = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "graph_versions"
        ordering = ["-version"]
        unique_together = [["graph", "version"]]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Compute checksum before saving."""
        if not self.checksum:
            json_str = json.dumps(self.graph_json, sort_keys=True, separators=(",", ":"))
            self.checksum = hashlib.sha256(json_str.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.graph.name} v{self.version}"


class PromptTemplate(models.Model):
    """PromptTemplate model representing a reusable prompt template."""

    objects = PromptTemplateManager()

    CATEGORY_CHOICES = [
        ("research", "Research"),
        ("summarization", "Summarization"),
        ("email", "Email"),
        ("extraction", "Extraction"),
        ("reasoning", "Reasoning"),
        ("other", "Other"),
    ]

    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("public", "Public"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="prompts",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="other")
    content = models.TextField()
    variables_schema = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=32, default="1.0.0")
    license = models.CharField(max_length=64, default="MIT")
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default="private")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prompt_templates"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_create = self._state.adding
        super().save(*args, **kwargs)

        if is_create:
            latest = (
                PromptTemplate.objects.exclude(pk=self.pk)
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            if latest and self.created_at <= latest:
                bumped = latest + timedelta(microseconds=1)
                PromptTemplate.objects.filter(pk=self.pk).update(
                    created_at=bumped, updated_at=bumped
                )
                self.created_at = bumped
                self.updated_at = bumped

    @property
    def is_builtin(self) -> bool:
        """Check if this is a built-in prompt."""
        return self.owner is None

    def clone_for_user(self, user: "User") -> "PromptTemplate":
        """Create a private copy of this prompt for the given user."""
        prompt: PromptTemplate = PromptTemplate.objects.create(
            owner=user,
            title=f"{self.title} (Copy)",
            description=self.description,
            category=self.category,
            content=self.content,
            variables_schema=copy.deepcopy(self.variables_schema),
            version=self.version,
            license=self.license,
            visibility="private",
        )


class Run(models.Model):
    """Run model representing an execution of a graph."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
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
    output_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

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
        ]

    def __str__(self) -> str:
        return f"Run {self.id} - {self.status}"

    @property
    def duration_ms(self) -> int | None:
        """Calculate run duration in milliseconds."""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


class RunEvent(models.Model):
    """RunEvent model storing execution events for observability."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "run_events"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["run", "created_at"], name="run_events_run_time_idx"),
        ]

    def __str__(self) -> str:
        return f"RunEvent {self.run_id} - {self.event_type}"


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


class MemoryChunk(models.Model):
    """MemoryChunk stores embedded long-term memory chunks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    agent_id = models.UUIDField(null=True, blank=True, db_index=True)
    run_id = models.UUIDField(null=True, blank=True, db_index=True)
    session_id = models.UUIDField(null=True, blank=True, db_index=True)
    content = models.TextField()
    chunk_type = models.CharField(max_length=20)
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=1536)
    embedding_model = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    source_timestamp = models.DateTimeField()

    class Meta:
        db_table = "memory_chunks"
        indexes = [
            models.Index(fields=["tenant_id"], name="memory_chunks_tenant_idx"),
            models.Index(fields=["tenant_id", "agent_id"], name="memory_chunks_agent_idx"),
            models.Index(fields=["tenant_id", "run_id"], name="memory_chunks_run_idx"),
            models.Index(fields=["tenant_id", "session_id"], name="memory_chunks_session_idx"),
            IvfflatIndex(
                name="memory_chunks_embedding_ivfflat",
                fields=["embedding"],
                lists=100,
            ),
        ]

    def __str__(self) -> str:
        return f"MemoryChunk {self.id} ({self.chunk_type})"


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

    class Meta:
        db_table = "node_runs"
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["run", "started_at", "attempt"], name="node_runs_run_time_idx"),
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


class APIKey(models.Model):
    """APIKey model for storing encrypted user API keys for LLM providers."""

    PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google AI"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=100, help_text="User-friendly name for this key")
    encrypted_key = models.BinaryField(help_text="Fernet-encrypted API key")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"
        ordering = ["-created_at"]
        unique_together = [["user", "provider", "name"]]
        indexes = [
            models.Index(fields=["user", "provider"], name="api_keys_user_provider_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} - {self.name} ({self.user.email})"

    @property
    def key_hint(self) -> str:
        """Return last 4 characters of the decrypted key for display."""
        from infrastructure.crypto.encryption import decrypt_api_key

        try:
            decrypted = decrypt_api_key(self.encrypted_key)
            return f"****{decrypted[-4:]}" if len(decrypted) >= 4 else "****"
        except Exception:
            return "****"
