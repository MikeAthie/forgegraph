"""
Django ORM models.

Clean Architecture: Frameworks & Drivers layer.
These models map to database tables and implement Django's ORM.
"""

import copy
import hashlib
import json
import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager that uses email as the unique identifier."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
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
    username = None  # Remove username field
    email = models.EmailField("email address", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email


class GraphQuerySet(models.QuerySet):
    def for_user(self, user: "User") -> "GraphQuerySet":
        return self.filter(owner=user)


class GraphManager(models.Manager.from_queryset(GraphQuerySet)):
    pass


class GraphVersionQuerySet(models.QuerySet):
    def latest_for_graph(self, graph_id: uuid.UUID) -> "GraphVersion | None":
        return self.filter(graph_id=graph_id).order_by("-version").first()


class GraphVersionManager(models.Manager.from_queryset(GraphVersionQuerySet)):
    pass


class PromptTemplateQuerySet(models.QuerySet):
    def public(self) -> "PromptTemplateQuerySet":
        return self.filter(visibility="public")

    def for_user(self, user: "User") -> "PromptTemplateQuerySet":
        return self.filter(models.Q(owner=user) | models.Q(visibility="public"))


class PromptTemplateManager(models.Manager.from_queryset(PromptTemplateQuerySet)):
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

    def __str__(self):
        return f"{self.name} ({self.owner.email})"


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

    def save(self, *args, **kwargs):
        """Compute checksum before saving."""
        if not self.checksum:
            json_str = json.dumps(self.graph_json, sort_keys=True, separators=(",", ":"))
            self.checksum = hashlib.sha256(json_str.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
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

    def __str__(self):
        return self.title

    @property
    def is_builtin(self) -> bool:
        """Check if this is a built-in prompt."""
        return self.owner is None

    def clone_for_user(self, user: User) -> "PromptTemplate":
        """Create a private copy of this prompt for the given user."""
        return PromptTemplate.objects.create(
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
        ]

    def __str__(self):
        return f"Run {self.id} - {self.status}"

    @property
    def duration_ms(self):
        """Calculate run duration in milliseconds."""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


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

    def __str__(self):
        return f"NodeRun {self.node_id} - {self.status}"

    @property
    def duration_ms(self):
        """Calculate node run duration in milliseconds."""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


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

    def __str__(self):
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

    def __str__(self):
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
