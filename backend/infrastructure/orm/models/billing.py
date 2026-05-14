"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.memory import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


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
