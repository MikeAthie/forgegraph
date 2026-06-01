"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.commerce import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class CompanySignal(models.Model):
    """Backend-owned business signal for operating-loop work."""

    SIGNAL_KIND_CHOICES = [
        ("request", "Request"),
        ("opportunity", "Opportunity"),
        ("risk", "Risk"),
        ("exception", "Exception"),
        ("feedback", "Feedback"),
        ("metric_change", "Metric Change"),
        ("capability_gap", "Capability Gap"),
        ("milestone", "Milestone"),
        ("manual", "Manual"),
    ]
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
    signal_kind = models.CharField(max_length=32, choices=SIGNAL_KIND_CHOICES, default="manual")
    domain_context = models.CharField(max_length=64, blank=True, default="general")
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
            models.Index(fields=["company", "signal_kind"], name="company_signal_kind_idx"),
            models.Index(fields=["company", "status"], name="company_signal_status_idx"),
            models.Index(fields=["company", "occurred_at"], name="company_signal_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type} signal ({self.status})"


class CompanyOperationObjective(models.Model):
    """Objective contract and evaluation for a company operation run."""

    OPERATION_FAMILY_CHOICES = [
        ("brief", "Brief"),
        ("planning", "Planning"),
        ("follow_up", "Follow Up"),
        ("exception_review", "Exception Review"),
        ("evidence_capture", "Evidence Capture"),
        ("approval_request", "Approval Request"),
    ]
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
    operation_family = models.CharField(
        max_length=32,
        choices=OPERATION_FAMILY_CHOICES,
        default="brief",
    )
    domain_context = models.CharField(max_length=64, blank=True, default="general")
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
            models.Index(fields=["company", "operation_family"], name="company_obj_family_idx"),
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
