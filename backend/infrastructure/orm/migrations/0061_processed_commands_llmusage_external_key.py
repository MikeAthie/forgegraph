from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0060_event_dead_letter_records"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedCommand",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255)),
                ("action", models.CharField(max_length=96)),
                ("request_hash", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_body", models.JSONField(default=dict)),
                ("resource_type", models.CharField(blank=True, default="", max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_commands",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "processed_commands",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="llmusage",
            name="external_key",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name="processedcommand",
            constraint=models.UniqueConstraint(
                fields=("organization", "action", "idempotency_key"),
                name="processed_cmd_org_action_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="processedcommand",
            index=models.Index(
                fields=["organization", "created_at"], name="processed_cmd_org_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="processedcommand",
            index=models.Index(
                fields=["organization", "resource_type", "resource_id"],
                name="processed_cmd_resource_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["tenant_id", "external_key"], name="llm_usage_tenant_ext_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="llmusage",
            constraint=models.UniqueConstraint(
                condition=models.Q(external_key__isnull=False),
                fields=("tenant_id", "external_key"),
                name="llm_usage_tenant_external_uniq",
            ),
        ),
    ]
