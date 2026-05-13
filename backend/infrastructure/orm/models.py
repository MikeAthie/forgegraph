"""
Django ORM models.

Clean Architecture: Frameworks & Drivers layer.
These models map to database tables and implement Django's ORM.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from pgvector.django import IvfflatIndex, VectorField

if TYPE_CHECKING:
    pass


def _make_check_constraint(expr: models.Q, *, name: str) -> models.CheckConstraint:
    params = inspect.signature(models.CheckConstraint).parameters
    if "condition" in params:
        return models.CheckConstraint(condition=expr, name=name)
    return models.CheckConstraint(check=expr, name=name)


class UserManager(BaseUserManager["User"]):
    """Custom user manager that uses email as the unique identifier."""

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> User:
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
    ) -> User:
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
    default_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_users",
    )

    USERNAME_FIELD: str = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return str(self.email)


class Organization(models.Model):
    """Organization model for multi-user tenants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organizations"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrganizationMembership(models.Model):
    """OrganizationMembership links users to organizations with roles."""

    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="member")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_memberships"
        unique_together = [["organization", "user"]]
        indexes = [
            models.Index(fields=["organization", "role"], name="org_membership_role_idx"),
            models.Index(fields=["user", "organization"], name="org_membership_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.organization.name}: {self.user.email} ({self.role})"


class GraphQuerySet(models.QuerySet["Graph"]):
    def for_user(self, user: User) -> GraphQuerySet:
        tenant_id = getattr(user, "default_organization_id", None)
        if tenant_id:
            if not OrganizationMembership.objects.filter(
                user=user, organization_id=tenant_id
            ).exists():
                return self.none()
            return self.filter(
                models.Q(organization_id=tenant_id)
                | models.Q(organization__isnull=True, owner__default_organization_id=tenant_id)
            )
        return self.filter(owner=user)


class GraphManager(models.Manager.from_queryset(GraphQuerySet)):  # type: ignore[misc]
    pass


class GraphVersionQuerySet(models.QuerySet["GraphVersion"]):
    def latest_for_graph(self, graph_id: uuid.UUID) -> GraphVersion | None:
        return self.filter(graph_id=graph_id).order_by("-version").first()


class GraphVersionManager(models.Manager.from_queryset(GraphVersionQuerySet)):  # type: ignore[misc]
    pass


class PromptTemplateQuerySet(models.QuerySet["PromptTemplate"]):
    def public(self) -> PromptTemplateQuerySet:
        return self.filter(visibility="public")

    def for_user(self, user: User) -> PromptTemplateQuerySet:
        tenant_id = getattr(user, "default_organization_id", None)
        if tenant_id:
            if not OrganizationMembership.objects.filter(
                user=user, organization_id=tenant_id
            ).exists():
                return self.public()
            return self.filter(
                models.Q(organization_id=tenant_id)
                | models.Q(organization__isnull=True, owner__default_organization_id=tenant_id)
                | models.Q(visibility="public")
            )
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
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="graphs",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    external_source = models.CharField(max_length=64, blank=True, default="")
    external_ref = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "graphs"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "external_source", "external_ref"],
                condition=models.Q(external_ref__gt=""),
                name="graphs_owner_source_external_ref_unique",
            ),
            models.UniqueConstraint(
                fields=["organization", "external_source", "external_ref"],
                condition=models.Q(organization__isnull=False, external_ref__gt=""),
                name="graphs_org_source_external_ref_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner", "external_source", "external_ref"],
                name="graphs_external_ref_idx",
            ),
            models.Index(
                fields=["organization", "updated_at"],
                name="graphs_org_updated_idx",
            ),
        ]

    def __str__(self) -> str:
        organization = self.organization
        scope = organization.name if organization is not None else self.owner.email
        return f"{self.name} ({scope})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_create = self._state.adding
        prev_updated = None
        if not self.organization_id and self.owner_id:
            self.organization_id = (
                User.objects.filter(pk=self.owner_id)
                .values_list(
                    "default_organization_id",
                    flat=True,
                )
                .first()
            )
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
            _make_check_constraint(
                ~(models.Q(graph__isnull=True) & models.Q(user__isnull=True)),
                name="memory_config_requires_scope",
            ),
            _make_check_constraint(
                ~(models.Q(graph__isnull=False) & models.Q(user__isnull=False)),
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
    external_idempotency_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "graph_versions"
        ordering = ["-version"]
        unique_together = [["graph", "version"]]
        constraints = [
            models.UniqueConstraint(
                fields=["graph", "external_idempotency_key"],
                condition=models.Q(external_idempotency_key__gt=""),
                name="graph_versions_idempotency_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["graph", "external_idempotency_key"],
                name="graph_versions_idempotency_idx",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Compute checksum before saving."""
        if not self.checksum:
            json_str = json.dumps(self.graph_json, sort_keys=True, separators=(",", ":"))
            self.checksum = hashlib.sha256(json_str.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.graph.name} v{self.version}"


class GraphTemplate(models.Model):
    """GraphTemplate model representing a reusable workflow template."""

    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("organization", "Organization"),
        ("private", "Private"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=64, blank=True, default="")
    tags = models.JSONField(default=list, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=3)
    graph_json = models.JSONField()
    sample_input = models.JSONField(default=dict, blank=True)
    guide_steps = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    changelog = models.TextField(blank=True, default="")
    is_latest = models.BooleanField(default=True)
    visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="public",
    )
    owner_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graph_templates",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "graph_templates"
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["is_active", "display_order"], name="graph_templates_active_idx"),
            models.Index(fields=["group_id", "version"], name="graph_templates_group_idx"),
            models.Index(fields=["is_latest", "visibility"], name="graph_templates_latest_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class TemplateShare(models.Model):
    """Share a template with another organization (read-only)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        GraphTemplate,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="template_shares",
    )
    shared_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "template_shares"
        unique_together = [["template", "organization"]]
        indexes = [
            models.Index(fields=["organization"], name="template_shares_org_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.template_id} -> {self.organization_id}"


class TemplateUsage(models.Model):
    """Track template usage (clones and runs)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        GraphTemplate,
        on_delete=models.CASCADE,
        related_name="usage_events",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="template_usage_events",
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_usage_events",
    )
    graph = models.ForeignKey(
        "Graph",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_usage_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "template_usage"
        indexes = [
            models.Index(fields=["template", "created_at"], name="template_usage_template_idx"),
            models.Index(fields=["organization", "created_at"], name="template_usage_org_idx"),
        ]

    def __str__(self) -> str:
        return f"TemplateUsage({self.template_id})"


class TemplateRating(models.Model):
    """Track template ratings."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        GraphTemplate,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="template_ratings",
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="template_ratings",
    )
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "template_ratings"
        unique_together = [["template", "user"]]
        indexes = [
            models.Index(fields=["template", "rating"], name="template_ratings_template_idx"),
        ]

    def __str__(self) -> str:
        return f"TemplateRating({self.template_id}, {self.rating})"


class NodeRegistryPackage(models.Model):
    """Published integration package metadata for the node marketplace."""

    CATEGORY_CHOICES = [
        ("communication", "Communication"),
        ("productivity", "Productivity"),
        ("crm", "CRM"),
        ("storage", "Storage"),
        ("developer", "Developer"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    summary = models.TextField(blank=True, default="")
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="other")
    icon = models.CharField(max_length=32, blank=True, default="")
    docs_url = models.URLField(blank=True, default="")
    homepage_url = models.URLField(blank=True, default="")
    owner_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_node_packages",
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_node_packages",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "node_registry_packages"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "category"], name="node_pkg_active_category_idx"),
        ]

    def __str__(self) -> str:
        return f"NodeRegistryPackage({self.slug})"


class NodeRegistryRelease(models.Model):
    """Versioned node package release with SDK schema + review status."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_review", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    EXECUTION_TYPE_CHOICES = [
        ("http", "HTTP"),
        ("prompt", "Prompt"),
        ("tool", "Tool"),
        ("transform", "Transform"),
    ]

    PACKAGE_KIND_CHOICES = [
        ("template_http", "Template HTTP"),
        ("template_prompt", "Template Prompt"),
        ("runtime_tool", "Runtime Tool"),
        ("runtime_transform", "Runtime Transform"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    package = models.ForeignKey(
        NodeRegistryPackage,
        on_delete=models.CASCADE,
        related_name="releases",
    )
    version = models.CharField(max_length=32)
    changelog = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    package_kind = models.CharField(
        max_length=32,
        choices=PACKAGE_KIND_CHOICES,
        default="template_http",
    )
    execution_node_type = models.CharField(
        max_length=32,
        choices=EXECUTION_TYPE_CHOICES,
    )
    ui_schema = models.JSONField(default=dict, blank=True)
    config_schema = models.JSONField(default=dict, blank=True)
    config_defaults = models.JSONField(default=dict, blank=True)
    runtime_manifest = models.JSONField(null=True, blank=True)
    manifest_version = models.PositiveSmallIntegerField(default=1)
    cloud_allowed = models.BooleanField(default=True)
    review_notes = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_node_releases",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="node_releases",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "node_registry_releases"
        ordering = ["-created_at"]
        unique_together = [["package", "version"]]
        indexes = [
            models.Index(fields=["status", "created_at"], name="node_rel_status_time_idx"),
            models.Index(fields=["package", "status"], name="node_rel_package_status_idx"),
        ]

    def __str__(self) -> str:
        return f"NodeRegistryRelease({self.package.slug}@{self.version})"


class NodePackageInstallation(models.Model):
    """Installed package release for an organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="installed_node_packages",
    )
    package = models.ForeignKey(
        NodeRegistryPackage,
        on_delete=models.CASCADE,
        related_name="installations",
    )
    release = models.ForeignKey(
        NodeRegistryRelease,
        on_delete=models.PROTECT,
        related_name="installations",
    )
    installed_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installed_node_packages",
    )
    is_active = models.BooleanField(default=True)
    install_metadata = models.JSONField(default=dict, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "node_package_installations"
        unique_together = [["organization", "package"]]
        indexes = [
            models.Index(fields=["organization", "is_active"], name="node_install_org_active_idx"),
        ]

    def __str__(self) -> str:
        return f"NodePackageInstallation({self.organization_id}, {self.package.slug})"


class OnboardingMilestone(models.Model):
    """Track onboarding progress milestones."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="onboarding_milestones",
    )
    milestone = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onboarding_milestones"
        unique_together = [["user", "milestone"]]
        indexes = [
            models.Index(fields=["tenant_id", "milestone"], name="onboarding_milestone_idx"),
        ]

    def __str__(self) -> str:
        return f"OnboardingMilestone({self.user_id}, {self.milestone})"


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
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="prompt_templates",
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
        indexes = [
            models.Index(fields=["organization", "created_at"], name="prompt_templates_org_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_create = self._state.adding
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

    def clone_for_user(self, user: User) -> PromptTemplate:
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
        return prompt


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


class BillingPlan(models.Model):
    """Billing plan with Stripe mapping and entitlements."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    stripe_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_price_id = models.CharField(max_length=255, blank=True, default="")
    entitlements = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_plans"

    def __str__(self) -> str:
        return self.name


class TenantSubscription(models.Model):
    """Stripe subscription state per tenant."""

    STATUS_CHOICES = [
        ("trialing", "Trialing"),
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
        ("incomplete", "Incomplete"),
        ("incomplete_expired", "Incomplete Expired"),
        ("unpaid", "Unpaid"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True)
    plan = models.ForeignKey(
        BillingPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="trialing")
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    seat_count = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_subscriptions"

    def __str__(self) -> str:
        return f"TenantSubscription {self.tenant_id} {self.status}"


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


class InventoryProduct(models.Model):
    """Reusable company-scoped inventory product/SKU."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="inventory_products",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="inventory_products",
    )
    sku = models.CharField(max_length=128)
    model = models.CharField(max_length=255)
    name = models.CharField(max_length=255, blank=True, default="")
    variant = models.CharField(max_length=255, blank=True, default="")
    color = models.CharField(max_length=128, blank=True, default="")
    photo_url = models.CharField(max_length=1024, blank=True, default="")
    price_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="mxn")
    price_mxn = models.DecimalField(max_digits=10, decimal_places=2)
    cost_mxn = models.DecimalField(max_digits=10, decimal_places=2)
    target_margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    anchor_model = models.BooleanField(default=False)
    scarcity_tag = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_products"
        ordering = ["model", "sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"],
                name="inventory_product_company_sku_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="inventory_prod_org_status_idx"),
            models.Index(fields=["company", "status"], name="inv_prod_company_status_idx"),
            models.Index(fields=["company", "anchor_model"], name="inventory_prod_anchor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.model} ({self.sku})"


class InventoryReservation(models.Model):
    """Backend-owned temporary hold on scarce stock."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("expired", "Expired"),
        ("released", "Released"),
        ("converted", "Converted"),
    ]
    CHANNEL_CHOICES = [
        ("manual", "Manual"),
        ("instagram", "Instagram"),
        ("whatsapp", "WhatsApp"),
        ("dm", "DM"),
        ("storefront", "Storefront"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="inventory_reservations",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="inventory_reservations",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    quantity = models.PositiveIntegerField(default=1)
    buyer_alias = models.CharField(max_length=120, blank=True, default="")
    channel = models.CharField(max_length=32, choices=CHANNEL_CHOICES, default="manual")
    note = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_reservations"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="inventory_res_company_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="inventory_res_org_status_idx"),
            models.Index(fields=["company", "status"], name="inv_res_company_status_idx"),
            models.Index(fields=["company", "expires_at"], name="inventory_res_expiry_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} x{self.quantity} ({self.status})"


class InventoryStockUnit(models.Model):
    """One row per physical stock unit."""

    STATUS_CHOICES = [
        ("available", "Available"),
        ("reserved", "Reserved"),
        ("sold", "Sold"),
        ("removed", "Removed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="inventory_stock_units",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="inventory_stock_units",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.CASCADE,
        related_name="stock_units",
    )
    current_reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_units",
    )
    unit_number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="available")
    source = models.CharField(max_length=64, blank=True, default="csv_import")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_stock_units"
        ordering = ["product", "unit_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "unit_number"],
                name="inventory_stock_product_unit_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="inventory_stock_org_status_idx"),
            models.Index(fields=["company", "status"], name="inv_stock_company_status_idx"),
            models.Index(fields=["product", "status"], name="inv_stock_product_status_idx"),
            models.Index(fields=["current_reservation"], name="inventory_stock_res_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} unit {self.unit_number} ({self.status})"


class InventoryOrderShell(models.Model):
    """Reusable order shell owned by backend commerce state."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_payment", "Pending Payment"),
        ("paid", "Paid"),
        ("payment_expired", "Payment Expired"),
        ("cancelled", "Cancelled"),
        ("payment_review_required", "Payment Review Required"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="inventory_order_shells",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="inventory_order_shells",
    )
    reservation = models.OneToOneField(
        InventoryReservation,
        on_delete=models.PROTECT,
        related_name="order",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_order_shells",
    )
    order_number = models.CharField(max_length=64)
    public_reference = models.CharField(max_length=64, blank=True, default="")
    public_status_token = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending_payment")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    stripe_session_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_checkout_url = models.CharField(max_length=2048, blank=True, default="")
    customer_email = models.CharField(max_length=255, blank=True, default="")
    customer_name = models.CharField(max_length=255, blank=True, default="")
    shipping_json = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_expired_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_order_shells"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "order_number"],
                name="inventory_order_company_number_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="inventory_order_company_idem_uniq",
            ),
            models.UniqueConstraint(
                fields=["stripe_session_id"],
                condition=models.Q(stripe_session_id__gt=""),
                name="inventory_order_stripe_session_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "public_reference"],
                condition=models.Q(public_reference__gt=""),
                name="inventory_order_public_ref_uniq",
            ),
            models.UniqueConstraint(
                fields=["public_status_token"],
                condition=models.Q(public_status_token__gt=""),
                name="inventory_order_public_token_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="inventory_order_org_status_idx"),
            models.Index(fields=["company", "status"], name="inv_order_company_status_idx"),
            models.Index(fields=["stripe_session_id"], name="inv_order_stripe_sess_idx"),
            models.Index(fields=["public_status_token"], name="inv_order_public_token_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.order_number} ({self.status})"


class CommerceStorefrontProfile(models.Model):
    """Backend-owned public storefront configuration for a company."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_storefront_profiles",
    )
    company = models.OneToOneField(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_storefront_profile",
    )
    slug = models.SlugField(max_length=128, unique=True)
    display_name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    currency = models.CharField(max_length=8, default="mxn")
    stripe_credential = models.ForeignKey(
        "APIKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_storefront_profiles",
    )
    success_path = models.CharField(max_length=255, blank=True, default="")
    cancel_path = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commerce_storefront_profiles"
        ordering = ["slug"]
        indexes = [
            models.Index(fields=["organization", "enabled"], name="storefront_org_enabled_idx"),
            models.Index(fields=["company", "enabled"], name="storefront_company_enabled_idx"),
            models.Index(fields=["slug", "enabled"], name="storefront_slug_enabled_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.slug})"


class CommercePayment(models.Model):
    """Backend-owned payment state for one-time commerce checkout."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("expired", "Expired"),
        ("failed", "Failed"),
        ("review_required", "Review Required"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_payments",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_payments",
    )
    reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.PROTECT,
        related_name="commerce_payments",
    )
    order = models.OneToOneField(
        InventoryOrderShell,
        on_delete=models.PROTECT,
        related_name="commerce_payment",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.PROTECT,
        related_name="commerce_payments",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_payments",
    )
    provider = models.CharField(max_length=32, default="stripe")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    amount_mxn = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="mxn")
    quantity = models.PositiveIntegerField(default=1)
    stripe_session_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    checkout_url = models.CharField(max_length=2048, blank=True, default="")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    latest_event_id = models.CharField(max_length=255, blank=True, default="")
    processed_event_ids = models.JSONField(default=list, blank=True)
    customer_email = models.CharField(max_length=255, blank=True, default="")
    customer_name = models.CharField(max_length=255, blank=True, default="")
    shipping_json = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=1000, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commerce_payments"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="commerce_payment_company_idem_uniq",
            ),
            models.UniqueConstraint(
                fields=["stripe_session_id"],
                condition=models.Q(stripe_session_id__gt=""),
                name="commerce_payment_stripe_session_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="comm_pay_org_status_idx"),
            models.Index(fields=["company", "status"], name="comm_pay_company_status_idx"),
            models.Index(fields=["stripe_session_id"], name="comm_pay_stripe_sess_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.amount_mxn} {self.currency} ({self.status})"


class CommerceCashLedgerEntry(models.Model):
    """Backend-owned cash ledger entry for commerce events."""

    ENTRY_TYPE_CHOICES = [
        ("sale", "Sale"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_cash_ledger_entries",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_cash_ledger_entries",
    )
    payment = models.OneToOneField(
        CommercePayment,
        on_delete=models.PROTECT,
        related_name="cash_ledger_entry",
    )
    order = models.ForeignKey(
        InventoryOrderShell,
        on_delete=models.PROTECT,
        related_name="cash_ledger_entries",
    )
    entry_type = models.CharField(max_length=32, choices=ENTRY_TYPE_CHOICES, default="sale")
    amount_mxn = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="mxn")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    occurred_at = models.DateTimeField()
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commerce_cash_ledger_entries"
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="commerce_cash_company_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "occurred_at"], name="commerce_cash_org_time_idx"),
            models.Index(fields=["company", "occurred_at"], name="commerce_cash_company_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount_mxn} {self.currency}"


class CommerceStripeEvent(models.Model):
    """Idempotency record for Stripe webhook events."""

    STATUS_CHOICES = [
        ("processed", "Processed"),
        ("ignored", "Ignored"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_stripe_events",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_stripe_events",
    )
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    payload_json = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=1000, blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commerce_stripe_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stripe_event_id"], name="commerce_stripe_event_id_idx"),
            models.Index(fields=["company", "event_type"], name="comm_stripe_company_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.stripe_event_id} ({self.status})"


class CommerceFulfillment(models.Model):
    """Backend-owned fulfillment state for paid commerce orders."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("ready", "Ready"),
        ("blocked", "Blocked"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_fulfillments",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_fulfillments",
    )
    order = models.OneToOneField(
        InventoryOrderShell,
        on_delete=models.PROTECT,
        related_name="commerce_fulfillment",
    )
    payment = models.OneToOneField(
        CommercePayment,
        on_delete=models.PROTECT,
        related_name="commerce_fulfillment",
    )
    reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.PROTECT,
        related_name="commerce_fulfillments",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    reason_code = models.CharField(max_length=64, blank=True, default="")
    operator_note = models.TextField(blank=True, default="")
    carrier = models.CharField(max_length=120, blank=True, default="")
    tracking_number = models.CharField(max_length=120, blank=True, default="")
    tracking_url = models.CharField(max_length=1024, blank=True, default="")
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commerce_fulfillments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="comm_fulfill_org_status_idx"),
            models.Index(fields=["company", "status"], name="comm_fulfill_company_status"),
            models.Index(fields=["company", "updated_at"], name="comm_fulfill_company_time"),
        ]

    def __str__(self) -> str:
        return f"{self.order.order_number} fulfillment ({self.status})"


class CommerceFulfillmentEvent(models.Model):
    """Append-only fulfillment timeline for operator-visible order operations."""

    EVENT_TYPE_CHOICES = [
        ("created", "Created"),
        ("ready", "Ready"),
        ("blocked", "Blocked"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
        ("note", "Note"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_fulfillment_events",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_fulfillment_events",
    )
    fulfillment = models.ForeignKey(
        CommerceFulfillment,
        on_delete=models.CASCADE,
        related_name="events",
    )
    order = models.ForeignKey(
        InventoryOrderShell,
        on_delete=models.PROTECT,
        related_name="fulfillment_events",
    )
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_fulfillment_events",
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    status_from = models.CharField(max_length=32, blank=True, default="")
    status_to = models.CharField(max_length=32, blank=True, default="")
    message = models.CharField(max_length=512, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commerce_fulfillment_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"], name="commerce_fevent_org_time_idx"
            ),
            models.Index(fields=["company", "created_at"], name="comm_fevent_company_time"),
            models.Index(fields=["fulfillment", "created_at"], name="commerce_fevent_fulfill_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.order_id}"


class CompanySignal(models.Model):
    """Backend-owned business signal for operating-loop work."""

    SIGNAL_TYPE_CHOICES = [
        ("demand", "Demand"),
        ("lead", "Lead"),
        ("stockout", "Stockout"),
        ("content_response", "Content Response"),
        ("fulfillment_issue", "Fulfillment Issue"),
        ("paid_order", "Paid Order"),
        ("manual", "Manual"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("qualified", "Qualified"),
        ("converted", "Converted"),
        ("dismissed", "Dismissed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_signals",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_signals",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_signals",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_signals",
    )
    order = models.ForeignKey(
        InventoryOrderShell,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_signals",
    )
    fulfillment = models.ForeignKey(
        CommerceFulfillment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_signals",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_signals",
    )
    signal_type = models.CharField(max_length=32, choices=SIGNAL_TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="new")
    source = models.CharField(max_length=64, blank=True, default="manual")
    external_key = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    channel = models.CharField(max_length=64, blank=True, default="")
    contact_alias = models.CharField(max_length=120, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_signals"
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source", "external_key"],
                condition=models.Q(external_key__gt=""),
                name="company_signal_source_ext_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="company_signal_org_status_idx"),
            models.Index(fields=["company", "signal_type"], name="company_signal_type_idx"),
            models.Index(fields=["company", "status"], name="company_signal_status_idx"),
            models.Index(fields=["company", "occurred_at"], name="company_signal_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type} signal ({self.status})"


class CompanyOperationObjective(models.Model):
    """Objective contract and evaluation for a company operation run."""

    RUN_TYPE_CHOICES = [
        ("rehearsal", "Rehearsal"),
        ("demand", "Demand"),
        ("commerce", "Commerce"),
        ("live_selling", "Live Selling"),
    ]
    STATUS_CHOICES = [
        ("planned", "Planned"),
        ("evaluated", "Evaluated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_operation_objectives",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_operation_objectives",
    )
    operation = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        related_name="company_objective",
    )
    source_signal = models.ForeignKey(
        CompanySignal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operation_objectives",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_operation_objectives",
    )
    run_type = models.CharField(max_length=32, choices=RUN_TYPE_CHOICES, default="rehearsal")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="planned")
    run_goal = models.TextField()
    hypothesis = models.TextField(blank=True, default="")
    target_signal = models.TextField(blank=True, default="")
    action_plan_json = models.JSONField(default=list, blank=True)
    integrity_gates_json = models.JSONField(default=dict, blank=True)
    success_score = models.PositiveSmallIntegerField(null=True, blank=True)
    miss_analysis = models.TextField(blank=True, default="")
    next_decision = models.TextField(blank=True, default="")
    evaluated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_operation_objectives"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="company_obj_status_idx"),
            models.Index(fields=["company", "run_type"], name="company_obj_run_type_idx"),
            models.Index(fields=["organization", "created_at"], name="company_obj_org_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.run_type} objective for {self.operation_id}"


class CompanyOpportunity(models.Model):
    """Qualified business opportunity derived from company signals."""

    STATUS_CHOICES = [
        ("new", "New"),
        ("qualified", "Qualified"),
        ("follow_up", "Follow Up"),
        ("reserved", "Reserved"),
        ("converted", "Converted"),
        ("lost", "Lost"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_opportunities",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_opportunities",
    )
    signal = models.ForeignKey(
        CompanySignal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_opportunities",
    )
    reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_opportunities",
    )
    order = models.ForeignKey(
        InventoryOrderShell,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_opportunities",
    )
    owner_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_opportunities",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="qualified")
    external_key = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    contact_alias = models.CharField(max_length=120, blank=True, default="")
    channel = models.CharField(max_length=64, blank=True, default="")
    estimated_value_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="mxn")
    next_action = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_opportunities"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "external_key"],
                condition=models.Q(external_key__gt=""),
                name="company_opp_external_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="company_opp_org_status_idx"),
            models.Index(fields=["company", "status"], name="company_opp_status_idx"),
            models.Index(fields=["company", "updated_at"], name="company_opp_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class PublicationDraft(models.Model):
    """Human-gated publication or content draft for a company."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approval_requested", "Approval Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("published", "Published"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="publication_drafts",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="publication_drafts",
    )
    signal = models.ForeignKey(
        CompanySignal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    opportunity = models.ForeignKey(
        CompanyOpportunity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    origin_operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_publication_drafts",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_publication_drafts",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    media_job = models.ForeignKey(
        MediaGenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publication_drafts",
    )
    title = models.CharField(max_length=255)
    channel = models.CharField(max_length=64, blank=True, default="")
    audience = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(blank=True, default="")
    call_to_action = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "publication_drafts"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="publication_draft_company_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="pub_draft_org_status_idx"),
            models.Index(fields=["company", "status"], name="pub_draft_company_status_idx"),
            models.Index(fields=["company", "updated_at"], name="pub_draft_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class CommerceProcurementDraft(models.Model):
    """Human-gated procurement/reorder proposal for a company."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approval_requested", "Approval Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("ordered", "Ordered"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="commerce_procurement_drafts",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="commerce_procurement_drafts",
    )
    origin_operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_procurement_drafts",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_procurement_drafts",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_procurement_drafts",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_procurement_drafts",
    )
    title = models.CharField(max_length=255)
    rationale = models.TextField(blank=True, default="")
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="mxn")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commerce_procurement_drafts"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="procurement_draft_company_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="proc_draft_org_status_idx"),
            models.Index(fields=["company", "status"], name="proc_draft_company_status_idx"),
            models.Index(fields=["company", "updated_at"], name="proc_draft_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class CommerceProcurementDraftLine(models.Model):
    """Line item for a procurement draft."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(
        CommerceProcurementDraft,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurement_draft_lines",
    )
    sku = models.CharField(max_length=128, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    unit_cost_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="mxn")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commerce_procurement_draft_lines"
        ordering = ["draft", "created_at"]
        indexes = [
            models.Index(fields=["draft"], name="proc_line_draft_idx"),
            models.Index(fields=["product"], name="proc_line_product_idx"),
        ]

    def __str__(self) -> str:
        label = self.sku or self.description or str(self.product_id or "")
        return f"{label} x{self.quantity}"


class InventoryEvent(models.Model):
    """Append-only reusable inventory timeline."""

    EVENT_TYPE_CHOICES = [
        ("import", "Import"),
        ("reserve", "Reserve"),
        ("release", "Release"),
        ("expire", "Expire"),
        ("extend", "Extend"),
        ("order_shell", "Order Shell"),
        ("sell", "Sell"),
        ("payment_expire", "Payment Expire"),
        ("payment_review", "Payment Review"),
        ("adjust", "Adjust"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="inventory_events",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="inventory_events",
    )
    product = models.ForeignKey(
        InventoryProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_events",
    )
    stock_unit = models.ForeignKey(
        InventoryStockUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_events",
    )
    reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_events",
    )
    order = models.ForeignKey(
        InventoryOrderShell,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_events",
    )
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_events",
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    quantity_delta = models.IntegerField(default=0)
    message = models.CharField(max_length=512, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"], name="inventory_event_org_time_idx"
            ),
            models.Index(fields=["company", "created_at"], name="inv_event_company_time_idx"),
            models.Index(fields=["product", "created_at"], name="inv_event_product_time_idx"),
            models.Index(fields=["reservation"], name="inventory_event_res_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.company_id})"


class AssetExtract(models.Model):
    """Searchable extraction from an exact asset version."""

    EMBEDDING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("indexed", "Indexed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.CASCADE,
        related_name="extracts",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="asset_extracts",
    )
    summary = models.TextField(null=True, blank=True)
    text_content = models.TextField(null=True, blank=True)
    chunks_json = models.JSONField(default=list, blank=True)
    claims_json = models.JSONField(default=list, blank=True)
    entities_json = models.JSONField(default=list, blank=True)
    embedding_status = models.CharField(
        max_length=16,
        choices=EMBEDDING_STATUS_CHOICES,
        default="pending",
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "asset_extracts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset_version"],
                name="asset_extract_ver_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "embedding_status"], name="asset_ext_comp_stat_idx"),
            models.Index(fields=["created_at"], name="asset_ext_created_idx"),
        ]

    def __str__(self) -> str:
        return f"AssetExtract {self.asset_version_id} ({self.embedding_status})"


class ContextPack(models.Model):
    """Bounded backend-prepared context for operation planning or execution."""

    CREATED_FOR_CHOICES = [
        ("operation_planning", "Operation Planning"),
        ("task_execution", "Task Execution"),
        ("review", "Review"),
        ("decision", "Decision"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="context_packs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="context_packs",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="context_packs",
    )
    task = models.ForeignKey(
        TaskRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="context_packs",
    )
    node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="context_packs",
    )
    department_id = models.CharField(max_length=255, blank=True, default="")
    scope_json = models.JSONField(default=dict, blank=True)
    brief_snapshot_json = models.JSONField(null=True, blank=True)
    asset_refs_json = models.JSONField(default=list, blank=True)
    memory_refs_json = models.JSONField(default=list, blank=True)
    decision_refs_json = models.JSONField(default=list, blank=True)
    policy_refs_json = models.JSONField(default=list, blank=True)
    assumptions_json = models.JSONField(default=list, blank=True)
    created_for = models.CharField(max_length=32, choices=CREATED_FOR_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "context_packs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_at"], name="ctx_pack_comp_time_idx"),
            models.Index(fields=["operation", "created_at"], name="ctx_pack_run_time_idx"),
            models.Index(fields=["task", "created_at"], name="ctx_pack_task_time_idx"),
        ]

    def __str__(self) -> str:
        return f"ContextPack {self.id} ({self.created_for})"


class EvidenceLink(models.Model):
    """Trace that an asset/version/extract influenced work."""

    USED_FOR_CHOICES = [
        ("planning", "Planning"),
        ("decision", "Decision"),
        ("validation", "Validation"),
        ("generation", "Generation"),
        ("review", "Review"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    context_pack = models.ForeignKey(
        ContextPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    asset_version = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    asset_extract = models.ForeignKey(
        AssetExtract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    usage_key = models.CharField(max_length=64, blank=True, default="")
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    task = models.ForeignKey(
        TaskRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    decision = models.ForeignKey(
        DecisionRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    deliverable_id = models.UUIDField(null=True, blank=True)
    used_for = models.CharField(max_length=16, choices=USED_FOR_CHOICES)
    relevance_score = models.FloatField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evidence_links"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "usage_key"],
                condition=models.Q(usage_key__gt=""),
                name="evid_company_usage_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "created_at"], name="evid_comp_time_idx"),
            models.Index(fields=["operation", "used_for"], name="evid_run_used_idx"),
            models.Index(fields=["task", "used_for"], name="evid_task_used_idx"),
            models.Index(fields=["decision", "used_for"], name="evid_dec_used_idx"),
            models.Index(fields=["context_pack"], name="evid_context_idx"),
            models.Index(fields=["company", "usage_key"], name="evid_comp_usage_idx"),
        ]

    def __str__(self) -> str:
        return f"EvidenceLink {self.asset_id} -> {self.used_for}"


class PreferenceEvent(models.Model):
    """Human feedback captured as structured learning data."""

    ACTOR_TYPE_CHOICES = [
        ("user", "User"),
        ("admin", "Admin"),
        ("reviewer", "Reviewer"),
        ("system", "System"),
    ]
    EVENT_TYPE_CHOICES = [
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("edited", "Edited"),
        ("overridden", "Overridden"),
        ("clarified", "Clarified"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="preference_events",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="preference_events",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    task = models.ForeignKey(
        TaskRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    decision = models.ForeignKey(
        DecisionRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    context_pack = models.ForeignKey(
        ContextPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preference_events",
    )
    actor_id = models.UUIDField(null=True, blank=True)
    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPE_CHOICES)
    event_type = models.CharField(max_length=16, choices=EVENT_TYPE_CHOICES)
    proposed_value_json = models.JSONField(null=True, blank=True)
    final_value_json = models.JSONField(null=True, blank=True)
    diff_json = models.JSONField(null=True, blank=True)
    rationale = models.TextField(null=True, blank=True)
    risk_level = models.FloatField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "preference_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["approval_task"],
                condition=models.Q(approval_task__isnull=False),
                name="pref_approval_task_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "created_at"], name="pref_comp_time_idx"),
            models.Index(fields=["operation", "created_at"], name="pref_run_time_idx"),
            models.Index(fields=["task", "event_type"], name="pref_task_event_idx"),
            models.Index(fields=["approval_task"], name="pref_approval_idx"),
            models.Index(fields=["context_pack"], name="pref_context_idx"),
        ]

    def __str__(self) -> str:
        return f"PreferenceEvent {self.event_type} {self.id}"


class OutcomeReview(models.Model):
    """Post-delivery review of whether a decision or deliverable worked."""

    CREATED_BY_TYPE_CHOICES = [
        ("user", "User"),
        ("agent", "Agent"),
        ("system", "System"),
        ("external", "External"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="outcome_reviews",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="outcome_reviews",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outcome_reviews",
    )
    task = models.ForeignKey(
        TaskRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outcome_reviews",
    )
    node_run = models.ForeignKey(
        NodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outcome_reviews",
    )
    decision = models.ForeignKey(
        DecisionRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outcome_reviews",
    )
    deliverable_id = models.UUIDField(null=True, blank=True)
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outcome_reviews",
    )
    success_score = models.FloatField(null=True, blank=True)
    success_metrics_json = models.JSONField(default=dict, blank=True)
    human_feedback = models.TextField(null=True, blank=True)
    issues_json = models.JSONField(default=list, blank=True)
    root_cause = models.TextField(null=True, blank=True)
    created_by_type = models.CharField(
        max_length=16,
        choices=CREATED_BY_TYPE_CHOICES,
        default="user",
    )
    created_by_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outcome_reviews"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_at"], name="outcome_comp_time_idx"),
            models.Index(fields=["operation", "created_at"], name="outcome_run_time_idx"),
            models.Index(fields=["asset", "created_at"], name="outcome_asset_time_idx"),
            models.Index(fields=["deliverable_id"], name="outcome_deliv_idx"),
        ]

    def __str__(self) -> str:
        return f"OutcomeReview {self.id}"


class PolicyRule(models.Model):
    """Learned or explicit company policy. Candidates require explicit promotion."""

    SCOPE_TYPE_CHOICES = [
        ("company", "Company"),
        ("department", "Department"),
        ("operation_type", "Operation Type"),
        ("task_type", "Task Type"),
        ("user", "User"),
    ]
    STATUS_CHOICES = [
        ("candidate", "Candidate"),
        ("active", "Active"),
        ("deprecated", "Deprecated"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="policy_rules",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="policy_rules",
    )
    scope_type = models.CharField(max_length=32, choices=SCOPE_TYPE_CHOICES, default="company")
    scope_id = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=255)
    condition_json = models.JSONField(default=dict, blank=True)
    recommendation_json = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="candidate")
    supporting_preference_event_ids_json = models.JSONField(default=list, blank=True)
    supporting_outcome_review_ids_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "policy_rules"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="policy_comp_status_idx"),
            models.Index(fields=["company", "scope_type"], name="policy_comp_scope_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class EscalationRule(models.Model):
    """Company rule for situations that should still ask humans."""

    SCOPE_TYPE_CHOICES = PolicyRule.SCOPE_TYPE_CHOICES
    TRIGGER_TYPE_CHOICES = [
        ("high_cost", "High Cost"),
        ("irreversible", "Irreversible"),
        ("low_confidence", "Low Confidence"),
        ("policy_conflict", "Policy Conflict"),
        ("novel_case", "Novel Case"),
        ("sensitive_asset", "Sensitive Asset"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("deprecated", "Deprecated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="escalation_rules",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="escalation_rules",
    )
    scope_type = models.CharField(max_length=32, choices=SCOPE_TYPE_CHOICES, default="company")
    scope_id = models.CharField(max_length=255, blank=True, default="")
    trigger_type = models.CharField(max_length=32, choices=TRIGGER_TYPE_CHOICES)
    condition_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "escalation_rules"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="esc_comp_status_idx"),
            models.Index(fields=["company", "trigger_type"], name="esc_comp_trigger_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.trigger_type} ({self.status})"


class OperatingModelPackRelease(models.Model):
    """Versioned, installable company operating model pack manifest."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("deprecated", "Deprecated"),
        ("disabled", "Disabled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pack_id = models.CharField(max_length=160)
    base_pack_id = models.CharField(max_length=120)
    version = models.CharField(max_length=32)
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    checksum = models.CharField(max_length=64)
    manifest_json = models.JSONField(default=dict, blank=True)
    files_json = models.JSONField(default=dict, blank=True)
    compatibility_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operating_model_pack_releases"
        ordering = ["base_pack_id", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["pack_id"],
                name="op_model_pack_release_pack_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["base_pack_id", "status"], name="op_pack_base_status_idx"),
            models.Index(fields=["status", "updated_at"], name="op_pack_status_updated_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pack_id} ({self.status})"


class CompanyOperatingModelInstallation(models.Model):
    """Company-scoped installation of an operating model pack release."""

    STATUS_CHOICES = [
        ("installing", "Installing"),
        ("active", "Active"),
        ("disabled", "Disabled"),
        ("archived", "Archived"),
        ("upgrading", "Upgrading"),
        ("rollback_pending", "Rollback Pending"),
        ("failed", "Failed"),
        ("removed", "Removed"),
        ("upgrade_available", "Upgrade Available"),
    ]
    ROLE_CHOICES = [
        ("primary", "Primary"),
        ("addon", "Add-on"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="operating_model_installations",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="operating_model_installations",
    )
    pack_release = models.ForeignKey(
        OperatingModelPackRelease,
        on_delete=models.PROTECT,
        related_name="company_installations",
    )
    pack_id = models.CharField(max_length=160)
    base_pack_id = models.CharField(max_length=160, blank=True, default="")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="addon")
    namespace = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    installed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operating_model_installations",
    )
    config_json = models.JSONField(default=dict, blank=True)
    public_config_json = models.JSONField(default=dict, blank=True)
    private_config_ref = models.CharField(max_length=255, blank=True, default="")
    dashboard_json = models.JSONField(default=dict, blank=True)
    install_metadata_json = models.JSONField(default=dict, blank=True)
    active_since = models.DateTimeField(null=True, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "company_operating_model_installations"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "pack_id"],
                name="company_op_model_install_company_pack_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "role"],
                condition=models.Q(role="primary", status="active"),
                name="company_op_model_one_active_primary",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="op_install_org_status_idx"),
            models.Index(fields=["company", "status"], name="op_install_company_status_idx"),
            models.Index(fields=["pack_id", "status"], name="op_install_pack_status_idx"),
            models.Index(fields=["company", "role", "status"], name="op_install_company_role_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company_id} {self.pack_id} ({self.status})"


class PackInstallationConfigRevision(models.Model):
    """Backend-owned revision history for company pack installation config."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="pack_installation_config_revisions",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="pack_installation_config_revisions",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.CASCADE,
        related_name="config_revisions",
    )
    version = models.PositiveIntegerField()
    public_config_json = models.JSONField(default=dict, blank=True)
    private_config_ref = models.CharField(max_length=255, blank=True, default="")
    change_reason = models.CharField(max_length=120, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_pack_config_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pack_installation_config_revisions"
        ordering = ["installation", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["installation", "version"],
                name="pack_config_revision_install_version_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "installation"], name="pack_config_company_inst_idx"),
            models.Index(fields=["organization", "created_at"], name="pack_config_org_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.installation_id} config v{self.version}"


class PackNamespaceClaim(models.Model):
    """Company-scoped claim for a pack-defined public object namespace."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("released", "Released"),
        ("conflict", "Conflict"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="pack_namespace_claims",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="pack_namespace_claims",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.CASCADE,
        related_name="namespace_claims",
    )
    pack_id = models.CharField(max_length=160)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=200)
    namespaced_id = models.CharField(max_length=400)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    source_checksum = models.CharField(max_length=64, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pack_namespace_claims"
        ordering = ["object_type", "namespaced_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "namespaced_id"],
                condition=models.Q(status="active"),
                name="pack_namespace_company_active_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="pack_ns_comp_stat_idx"),
            models.Index(fields=["installation", "status"], name="pack_ns_inst_stat_idx"),
            models.Index(fields=["pack_id", "object_type"], name="pack_namespace_pack_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.namespaced_id} ({self.status})"

    def clean(self) -> None:
        super().clean()
        expected_prefix = f"{self.pack_id}."
        if (
            self.pack_id
            and self.namespaced_id
            and not self.namespaced_id.startswith(expected_prefix)
        ):
            raise ValidationError(
                {
                    "namespaced_id": (
                        "Pack namespace claim namespaced_id must start with "
                        f"the owning pack id plus a dot: {expected_prefix}"
                    )
                }
            )


class CompanyAccessPolicy(models.Model):
    """Company-level access defaults layered under organization membership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_access_policies",
    )
    company = models.OneToOneField(
        Graph,
        on_delete=models.CASCADE,
        related_name="access_policy",
    )
    assignment_required = models.BooleanField(default=False)
    org_admin_access_enabled = models.BooleanField(default=True)
    cross_client_learning_enabled = models.BooleanField(default=False)
    learning_policy_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_access_policies"
        ordering = ["company_id"]
        indexes = [
            models.Index(
                fields=["organization", "assignment_required"], name="company_access_org_req_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company_id} access policy"


class CompanyAssignment(models.Model):
    """User assignment granting access to one company inside an organization."""

    ROLE_CHOICES = [
        ("viewer", "Viewer"),
        ("member", "Member"),
        ("admin", "Admin"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_assignments",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_assignments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="company_assignments",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="viewer")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_company_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_assignments"
        ordering = ["company", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user"],
                name="company_assignment_company_user_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="comp_assign_org_stat_idx"),
            models.Index(fields=["company", "status"], name="comp_assign_comp_stat_idx"),
            models.Index(fields=["user", "status"], name="comp_assign_user_stat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.company_id} ({self.role}, {self.status})"


class ServiceCatalogItem(models.Model):
    """Generic customer-facing service offer mapped to internal company capabilities."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("disabled", "Disabled"),
        ("archived", "Archived"),
    ]
    VISIBILITY_CHOICES = [
        ("internal", "Internal"),
        ("organization", "Organization"),
        ("customer", "Customer"),
        ("public", "Public"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_catalog_items",
    )
    slug = models.SlugField(max_length=160)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="organization",
    )
    audience = models.CharField(max_length=120, blank=True, default="")
    required_pack_ids_json = models.JSONField(default=list, blank=True)
    optional_pack_ids_json = models.JSONField(default=list, blank=True)
    intake_schema_json = models.JSONField(default=dict, blank=True)
    deliverables_schema_json = models.JSONField(default=list, blank=True)
    default_operation_templates_json = models.JSONField(default=list, blank=True)
    default_report_template_id = models.CharField(max_length=160, blank=True, default="")
    pricing_metadata_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_service_catalog_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_catalog_items"
        ordering = ["title", "slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="service_catalog_org_slug_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="svc_catalog_org_status_idx"),
            models.Index(fields=["organization", "visibility"], name="svc_catalog_org_vis_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class ServiceEngagement(models.Model):
    """Company-scoped request or purchase of a generic service catalog item."""

    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("intake", "Intake"),
        ("in_progress", "In Progress"),
        ("waiting_on_customer", "Waiting On Customer"),
        ("in_review", "In Review"),
        ("delivered", "Delivered"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("archived", "Archived"),
    ]
    CUSTOMER_STATUS_CHOICES = [
        ("requested", "Requested"),
        ("intake_needed", "Intake Needed"),
        ("working", "Working"),
        ("waiting_on_you", "Waiting On You"),
        ("review_ready", "Review Ready"),
        ("delivered", "Delivered"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_engagements",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="service_engagements",
    )
    catalog_item = models.ForeignKey(
        ServiceCatalogItem,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="requested")
    customer_status = models.CharField(
        max_length=32,
        choices=CUSTOMER_STATUS_CHOICES,
        default="requested",
    )
    intake_data_json = models.JSONField(default=dict, blank=True)
    public_summary = models.TextField(blank=True, default="")
    internal_notes = models.TextField(blank=True, default="")
    source_key = models.CharField(max_length=255, blank=True, default="")
    required_pack_ids_json = models.JSONField(default=list, blank=True)
    operation_ids_json = models.JSONField(default=list, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    assigned_operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_service_engagements",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_service_engagements",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagements"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_key"],
                condition=models.Q(source_key__gt=""),
                name="service_engagement_company_source_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="svc_eng_org_status_idx"),
            models.Index(fields=["company", "status"], name="svc_eng_company_status_idx"),
            models.Index(fields=["catalog_item", "status"], name="svc_eng_catalog_status_idx"),
            models.Index(
                fields=["assigned_operator", "status"], name="svc_eng_operator_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company_id} {self.catalog_item_id} ({self.status})"


class ServiceDeliverable(models.Model):
    """Customer-facing wrapper around a company-owned artifact or report."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("in_review", "In Review"),
        ("ready", "Ready"),
        ("delivered", "Delivered"),
        ("accepted", "Accepted"),
        ("archived", "Archived"),
    ]
    VISIBILITY_CHOICES = [
        ("customer", "Customer"),
        ("operator", "Operator"),
        ("internal", "Internal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_deliverables",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="service_deliverables",
    )
    engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.CASCADE,
        related_name="deliverables",
    )
    title = models.CharField(max_length=255)
    deliverable_type = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default="customer")
    artifact = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_deliverables",
    )
    report_run = models.ForeignKey(
        "ReportRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_deliverables",
    )
    summary = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_service_deliverables",
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_deliverables"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="svc_deliv_org_status_idx"),
            models.Index(fields=["company", "status"], name="svc_deliv_company_status_idx"),
            models.Index(fields=["engagement", "status"], name="svc_deliv_eng_status_idx"),
            models.Index(fields=["visibility", "status"], name="svc_deliv_vis_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class CompanyProgram(models.Model):
    """Pack-defined multi-stage company program such as an engagement."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="company_programs",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="company_programs",
    )
    installation = models.ForeignKey(
        CompanyOperatingModelInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="programs",
    )
    pack_id = models.CharField(max_length=160, blank=True, default="")
    template_id = models.CharField(max_length=160)
    display_label = models.CharField(max_length=120, default="Program")
    title = models.CharField(max_length=255)
    objective = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    current_stage_id = models.CharField(max_length=120, blank=True, default="")
    external_key = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_company_programs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_programs"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "external_key"],
                condition=models.Q(external_key__gt=""),
                name="company_program_external_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="company_program_org_status_idx"),
            models.Index(fields=["company", "status"], name="company_program_status_idx"),
            models.Index(fields=["company", "pack_id"], name="company_program_pack_idx"),
            models.Index(fields=["company", "template_id"], name="company_program_template_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class ProgramStageState(models.Model):
    """Backend-owned state for a stage inside a generic company program."""

    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("blocked", "Blocked"),
        ("awaiting_validation", "Awaiting Validation"),
        ("completed", "Completed"),
        ("rerun_required", "Rerun Required"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="program_stage_states",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="program_stage_states",
    )
    program = models.ForeignKey(
        CompanyProgram,
        on_delete=models.CASCADE,
        related_name="stage_states",
    )
    stage_id = models.CharField(max_length=120)
    label = models.CharField(max_length=255)
    sequence = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="not_started")
    state_json = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "program_stage_states"
        ordering = ["program", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "stage_id"],
                name="program_stage_state_program_stage_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="stage_state_company_status_idx"),
            models.Index(fields=["program", "status"], name="stage_state_program_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.program_id} {self.stage_id} ({self.status})"


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


class APIKey(models.Model):
    """APIKey model for storing encrypted user API keys for LLM providers."""

    PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google AI"),
        ("openrouter", "OpenRouter"),
        ("gmail", "Gmail"),
        ("google_calendar", "Google Calendar"),
        ("google_tasks", "Google Tasks"),
        ("notion", "Notion"),
        ("slack", "Slack"),
        ("jira", "Jira"),
        ("linear", "Linear"),
        ("hubspot", "HubSpot"),
        ("google_drive", "Google Drive"),
        ("telegram", "Telegram"),
        ("twilio", "Twilio"),
        ("stripe", "Stripe"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=100, help_text="User-friendly name for this key")
    encrypted_key = models.BinaryField(help_text="Fernet-encrypted API key")
    encrypted_refresh_token = models.BinaryField(
        null=True,
        blank=True,
        help_text="Fernet-encrypted OAuth refresh token",
    )
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"
        ordering = ["-created_at"]
        unique_together = [["organization", "provider", "name"]]
        indexes = [
            models.Index(
                fields=["organization", "provider"],
                name="api_keys_org_provider_idx",
            ),
            models.Index(fields=["user"], name="api_keys_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} - {self.name} ({self.organization.name})"

    @property
    def key_hint(self) -> str:
        """Return last 4 characters of the decrypted key for display."""
        from infrastructure.crypto.encryption import decrypt_api_key

        try:
            decrypted = decrypt_api_key(bytes(self.encrypted_key))
            return f"****{decrypted[-4:]}" if len(decrypted) >= 4 else "****"
        except Exception:
            return "****"


@receiver(post_save, sender=User)
def ensure_default_organization(
    sender: type[User], instance: User, created: bool, **kwargs: Any
) -> None:
    if not created or instance.default_organization_id:
        return

    org_name = instance.email.split("@")[0] or "Personal"
    organization = Organization.objects.create(name=f"{org_name} Org")
    OrganizationMembership.objects.create(
        organization=organization,
        user=instance,
        role="owner",
        is_default=True,
    )
    User.objects.filter(pk=instance.pk).update(default_organization=organization)


@receiver(post_save, sender=Organization)
def ensure_organization_runtime_ledgers(
    sender: type[Organization], instance: Organization, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    OrganizationDomainEventSequence.objects.get_or_create(
        organization_id=instance.id,
        defaults={"next_sequence": 1},
    )
    OrganizationStateFeedSequence.objects.get_or_create(
        organization_id=instance.id,
        defaults={"next_sequence": 1},
    )


@receiver(post_save, sender=Run)
def record_run_domain_event_signal(
    sender: type[Run], instance: Run, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_run_domain_event

    record_run_domain_event(instance, created=created)


@receiver(post_save, sender=RunEvent)
def record_run_event_domain_event_signal(
    sender: type[RunEvent], instance: RunEvent, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_run_event_domain_event

    record_run_event_domain_event(instance)


@receiver(post_save, sender=NodeRun)
def record_node_run_domain_event_signal(
    sender: type[NodeRun], instance: NodeRun, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_node_run_domain_event

    record_node_run_domain_event(instance, created=created)


@receiver(post_save, sender=TaskLifecycleEvent)
def record_task_lifecycle_domain_event_signal(
    sender: type[TaskLifecycleEvent], instance: TaskLifecycleEvent, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_task_lifecycle_domain_event

    record_task_lifecycle_domain_event(instance)


@receiver(post_save, sender=ApprovalTask)
def record_approval_domain_event_signal(
    sender: type[ApprovalTask], instance: ApprovalTask, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_approval_domain_event

    record_approval_domain_event(instance, created=created)


@receiver(post_save, sender=LLMUsage)
def record_llm_usage_domain_event_signal(
    sender: type[LLMUsage], instance: LLMUsage, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_llm_usage_domain_event

    record_llm_usage_domain_event(instance)


@receiver(post_save, sender=MemoryUsage)
def record_memory_usage_domain_event_signal(
    sender: type[MemoryUsage], instance: MemoryUsage, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_memory_usage_domain_event

    record_memory_usage_domain_event(instance)


@receiver(post_save, sender=MemoryObservation)
def record_memory_observation_domain_event_signal(
    sender: type[MemoryObservation], instance: MemoryObservation, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import (
        domain_event_signals_suppressed,
        record_memory_observation_domain_event,
    )

    if domain_event_signals_suppressed():
        return

    record_memory_observation_domain_event(instance, created=created)


@receiver(post_save, sender=GraphVersion)
def record_graph_version_domain_event_signal(
    sender: type[GraphVersion], instance: GraphVersion, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_graph_version_domain_event

    record_graph_version_domain_event(instance)


@receiver(post_save, sender=AuditLog)
def record_audit_review_domain_event_signal(
    sender: type[AuditLog], instance: AuditLog, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_audit_review_domain_event

    record_audit_review_domain_event(instance)
