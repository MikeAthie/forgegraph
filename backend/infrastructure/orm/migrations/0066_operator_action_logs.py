import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orm", "0065_memory_observation_provenance"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperatorActionLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=96)),
                ("target_type", models.CharField(max_length=64)),
                ("target_id", models.CharField(max_length=128)),
                ("reason", models.TextField(blank=True, default="")),
                ("status", models.CharField(default="applied", max_length=32)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="operator_action_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="operator_action_logs",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "operator_action_logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="operatoractionlog",
            index=models.Index(
                fields=["organization", "created_at"],
                name="operator_action_org_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="operatoractionlog",
            index=models.Index(
                fields=["organization", "action", "created_at"],
                name="operator_action_org_action_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="operatoractionlog",
            index=models.Index(
                fields=["target_type", "target_id"],
                name="operator_action_target_idx",
            ),
        ),
    ]
