import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0049_run_dispatch_graph_json"),
    ]

    operations = [
        migrations.CreateModel(
            name="ToolExecution",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("node_id", models.CharField(max_length=255)),
                ("attempt_id", models.CharField(max_length=64)),
                ("tool_name", models.CharField(max_length=128)),
                ("tool_version", models.CharField(blank=True, default="", max_length=64)),
                ("idempotency_key", models.CharField(max_length=128)),
                (
                    "side_effect_class",
                    models.CharField(
                        choices=[
                            ("pure", "Pure"),
                            ("idempotent", "Idempotent"),
                            ("non_idempotent", "Non-Idempotent"),
                            ("critical", "Critical"),
                        ],
                        default="non_idempotent",
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("in_progress", "In Progress"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("ambiguous", "Ambiguous"),
                        ],
                        default="planned",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tool_executions",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "tool_executions",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["run", "status"], name="tool_exec_run_status_idx"),
                    models.Index(fields=["idempotency_key"], name="tool_exec_idem_key_idx"),
                    models.Index(fields=["tool_name", "tool_version"], name="tool_exec_tool_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "node_id", "attempt_id"),
                        name="tool_exec_run_node_attempt_uniq",
                    )
                ],
            },
        ),
    ]
