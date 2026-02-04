from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0021_add_personal_life_manager_template"),
    ]

    operations = [
        migrations.CreateModel(
            name="LLMQuota",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(unique=True)),
                ("monthly_token_limit", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "monthly_cost_limit_usd",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "llm_quotas",
            },
        ),
    ]
