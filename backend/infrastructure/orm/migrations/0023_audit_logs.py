from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0022_llm_quota"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("action", models.CharField(max_length=64)),
                ("resource_type", models.CharField(max_length=64)),
                ("resource_id", models.CharField(max_length=128)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "audit_logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["tenant_id", "created_at"], name="audit_logs_tenant_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action", "created_at"], name="audit_logs_action_time_idx"),
        ),
    ]
