import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0029_onboarding_milestones"),
    ]

    operations = [
        migrations.CreateModel(
            name="RunQueueEntry",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                (
                    "run",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="queue_entry",
                        to="orm.run",
                    ),
                ),
                ("tenant_id", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                    ),
                ),
                ("priority", models.PositiveSmallIntegerField(default=0)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=5)),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("locked_at", models.DateTimeField(null=True, blank=True)),
                ("locked_by", models.CharField(max_length=64, blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "run_queue",
            },
        ),
        migrations.AddIndex(
            model_name="runqueueentry",
            index=models.Index(fields=["status", "available_at"], name="run_queue_status_idx"),
        ),
        migrations.AddIndex(
            model_name="runqueueentry",
            index=models.Index(fields=["tenant_id", "status"], name="run_queue_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="runqueueentry",
            index=models.Index(fields=["locked_at"], name="run_queue_locked_idx"),
        ),
    ]
