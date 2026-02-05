from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0026_tenant_retention_policies"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingPlan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("stripe_product_id", models.CharField(blank=True, default="", max_length=255)),
                ("stripe_price_id", models.CharField(blank=True, default="", max_length=255)),
                ("entitlements", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_plans",
            },
        ),
        migrations.CreateModel(
            name="OIDCProvider",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                (
                    "provider",
                    models.CharField(choices=[("auth0", "Auth0")], default="auth0", max_length=32),
                ),
                ("issuer_url", models.URLField()),
                ("client_id", models.CharField(max_length=255)),
                ("encrypted_client_secret", models.BinaryField()),
                ("audience", models.CharField(blank=True, default="", max_length=255)),
                ("email_domains", models.JSONField(blank=True, default=list)),
                (
                    "default_role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                            ("viewer", "Viewer"),
                        ],
                        max_length=16,
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "oidc_providers",
            },
        ),
        migrations.CreateModel(
            name="SCIMToken",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                ("token_hash", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("rotated_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "scim_tokens",
            },
        ),
        migrations.CreateModel(
            name="TenantSubscription",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                ("stripe_customer_id", models.CharField(blank=True, default="", max_length=255)),
                (
                    "stripe_subscription_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("trialing", "Trialing"),
                            ("active", "Active"),
                            ("past_due", "Past Due"),
                            ("canceled", "Canceled"),
                            ("incomplete", "Incomplete"),
                            ("incomplete_expired", "Incomplete Expired"),
                            ("unpaid", "Unpaid"),
                        ],
                        default="trialing",
                        max_length=32,
                    ),
                ),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("cancel_at_period_end", models.BooleanField(default=False)),
                ("seat_count", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscriptions",
                        to="orm.billingplan",
                    ),
                ),
            ],
            options={
                "db_table": "tenant_subscriptions",
            },
        ),
    ]
