import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0018_run_event_external_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="LLMUsage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("node_id", models.CharField(max_length=255)),
                ("provider", models.CharField(max_length=32)),
                ("model", models.CharField(max_length=64)),
                ("prompt_tokens", models.PositiveIntegerField(default=0)),
                ("completion_tokens", models.PositiveIntegerField(default=0)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("cost_usd", models.DecimalField(max_digits=12, decimal_places=6, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="llm_usage",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "llm_usage",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LLMBudget",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(unique=True)),
                ("monthly_limit_usd", models.DecimalField(max_digits=12, decimal_places=2)),
                (
                    "warning_threshold_pct",
                    models.DecimalField(max_digits=5, decimal_places=2, default=0.8),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "llm_budgets",
            },
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["tenant_id", "created_at"], name="llm_usage_tenant_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(fields=["run", "node_id"], name="llm_usage_run_node_idx"),
        ),
    ]
