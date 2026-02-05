from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0025_organizations_and_rbac"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantRetentionPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                ("runs_retention_days", models.PositiveIntegerField(blank=True, null=True)),
                ("run_logs_retention_days", models.PositiveIntegerField(blank=True, null=True)),
                ("audit_logs_retention_days", models.PositiveIntegerField(blank=True, null=True)),
                ("usage_retention_days", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "tenant_retention_policies",
            },
        ),
    ]
