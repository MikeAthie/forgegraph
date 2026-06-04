"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.company_ops import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


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


class ServiceEngagementBusinessSnapshot(models.Model):
    """Backend-owned engagement economics, scope, and SLA snapshot."""

    PROFITABILITY_BAND_CHOICES = [
        ("unknown", "Unknown"),
        ("strong", "Strong"),
        ("healthy", "Healthy"),
        ("thin", "Thin"),
        ("break_even", "Break Even"),
        ("loss", "Loss"),
    ]
    SCOPE_STATUS_CHOICES = [
        ("unknown", "Unknown"),
        ("on_track", "On Track"),
        ("at_risk", "At Risk"),
        ("over_limit", "Over Limit"),
    ]
    SLA_STATUS_CHOICES = [
        ("unknown", "Unknown"),
        ("met", "Met"),
        ("at_risk", "At Risk"),
        ("breached", "Breached"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="service_engagement_business_snapshots",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="service_engagement_business_snapshots",
    )
    engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.CASCADE,
        related_name="business_snapshots",
    )
    source_key = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    revenue_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_cost_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pass_through_cost_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tooling_cost_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_margin_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_margin_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    profitability_band = models.CharField(
        max_length=32,
        choices=PROFITABILITY_BAND_CHOICES,
        default="unknown",
    )
    scope_unit = models.CharField(max_length=64, blank=True, default="")
    scope_included_units = models.PositiveIntegerField(null=True, blank=True)
    scope_used_units = models.PositiveIntegerField(null=True, blank=True)
    scope_overage_units = models.PositiveIntegerField(default=0)
    scope_utilization_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    scope_status = models.CharField(
        max_length=32,
        choices=SCOPE_STATUS_CHOICES,
        default="unknown",
    )
    sla_target_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    sla_elapsed_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    sla_breach_count = models.PositiveIntegerField(default=0)
    sla_status = models.CharField(
        max_length=32,
        choices=SLA_STATUS_CHOICES,
        default="unknown",
    )
    snapshot_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_service_engagement_business_snapshots",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagement_business_snapshots"
        ordering = ["-recorded_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "idempotency_key"],
                name="svc_bus_snap_eng_idem_uniq",
            ),
            models.UniqueConstraint(
                fields=["engagement", "source_key"],
                condition=models.Q(source_key__gt=""),
                name="svc_bus_snap_eng_src_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "recorded_at"], name="svc_bus_snap_org_time_idx"),
            models.Index(fields=["company", "recorded_at"], name="svc_bus_snap_comp_time_idx"),
            models.Index(
                fields=["engagement", "recorded_at"],
                name="svc_bus_snap_eng_time_idx",
            ),
            models.Index(
                fields=["company", "profitability_band"],
                name="svc_bus_snap_profit_idx",
            ),
            models.Index(fields=["company", "scope_status"], name="svc_bus_snap_scope_idx"),
            models.Index(fields=["company", "sla_status"], name="svc_bus_snap_sla_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.engagement_id} {self.period_start or 'snapshot'} ({self.scope_status})"


class AtlasLaunchAttempt(models.Model):
    """Backend-owned durable state for an Atlas campaign launch attempt."""

    STATUS_CHOICES = [
        ("dry_run", "Dry Run"),
        ("blocked", "Blocked"),
        ("ready", "Ready"),
        ("launched", "Launched"),
        ("failed", "Failed"),
    ]
    MODE_CHOICES = [("dry_run", "Dry Run"), ("live", "Live")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="atlas_launch_attempts",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="atlas_launch_attempts",
    )
    whiteboard = models.ForeignKey(
        "WorkWhiteboard",
        on_delete=models.CASCADE,
        related_name="atlas_launch_attempts",
    )
    source_key = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=255)
    requested_mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="dry_run")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="dry_run")
    blocker_snapshot_json = models.JSONField(default=list, blank=True)
    readiness_snapshot_json = models.JSONField(default=dict, blank=True)
    receipt_deliverable = models.ForeignKey(
        "ServiceDeliverable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atlas_launch_attempts",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_atlas_launch_attempts",
    )
    last_checkpoint_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "atlas_launch_attempts"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_key"],
                name="atlas_launch_att_comp_src_uniq",
            ),
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                name="atlas_launch_att_comp_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="atlas_launch_att_org_st_idx"),
            models.Index(fields=["company", "status"], name="atlas_launch_att_comp_st_idx"),
            models.Index(fields=["whiteboard", "status"], name="atlas_launch_att_board_st_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company_id} {self.source_key} ({self.status})"


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
    department = models.ForeignKey(
        "DepartmentRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_deliverables",
    )
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
            models.Index(fields=["department", "status"], name="svc_deliv_dept_status_idx"),
            models.Index(fields=["visibility", "status"], name="svc_deliv_vis_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class AtlasLaunchCheckpoint(models.Model):
    """Append-only audit checkpoint for an Atlas launch attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="atlas_launch_checkpoints",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="atlas_launch_checkpoints",
    )
    attempt = models.ForeignKey(
        AtlasLaunchAttempt,
        on_delete=models.CASCADE,
        related_name="checkpoints",
    )
    whiteboard = models.ForeignKey(
        "WorkWhiteboard",
        on_delete=models.CASCADE,
        related_name="atlas_launch_checkpoints",
    )
    sequence = models.PositiveIntegerField()
    checkpoint_type = models.CharField(max_length=80, default="readiness_evaluated")
    requested_mode = models.CharField(max_length=16, choices=AtlasLaunchAttempt.MODE_CHOICES)
    status = models.CharField(max_length=16, choices=AtlasLaunchAttempt.STATUS_CHOICES)
    idempotency_key = models.CharField(max_length=255)
    source_key = models.CharField(max_length=255)
    blocker_snapshot_json = models.JSONField(default=list, blank=True)
    readiness_snapshot_json = models.JSONField(default=dict, blank=True)
    receipt_deliverable = models.ForeignKey(
        ServiceDeliverable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atlas_launch_checkpoints",
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_atlas_launch_checkpoints",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "atlas_launch_checkpoints"
        ordering = ["attempt", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "sequence"],
                name="atlas_launch_cp_att_seq_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="atlas_launch_cp_org_cr_idx"),
            models.Index(fields=["company", "status"], name="atlas_launch_cp_comp_st_idx"),
            models.Index(fields=["whiteboard", "created_at"], name="atlas_launch_cp_board_cr_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} #{self.sequence} ({self.status})"


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
