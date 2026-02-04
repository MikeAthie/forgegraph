from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0023_audit_logs"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                ("http_allowlist", models.JSONField(blank=True, default=list)),
                ("http_denylist", models.JSONField(blank=True, default=list)),
                ("http_default_deny", models.BooleanField(default=False)),
                ("allowed_providers", models.JSONField(blank=True, default=list)),
                ("allowed_models", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "tenant_policies",
            },
        ),
    ]
