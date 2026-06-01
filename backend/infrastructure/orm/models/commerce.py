"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.decisions_assets import *  # noqa: F403
from infrastructure.orm.models.base import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


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
