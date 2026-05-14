"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.auth import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


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
