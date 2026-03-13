from __future__ import annotations

import inspect
import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def _make_check_constraint(expr: models.Q, *, name: str) -> models.CheckConstraint:
    params = inspect.signature(models.CheckConstraint).parameters
    if "condition" in params:
        return models.CheckConstraint(condition=expr, name=name)
    return models.CheckConstraint(check=expr, name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0040_marketplace_runtime_contract"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemoryObservation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("graph_id", models.UUIDField(blank=True, null=True)),
                ("run_id", models.UUIDField(blank=True, null=True)),
                ("session_id", models.UUIDField(blank=True, null=True)),
                ("agent_id", models.UUIDField(blank=True, null=True)),
                ("type", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                (
                    "scope",
                    models.CharField(
                        choices=[("graph", "Graph"), ("run", "Run"), ("session", "Session")],
                        default="graph",
                        max_length=16,
                    ),
                ),
                ("topic_key", models.CharField(blank=True, default="", max_length=128)),
                ("tool_name", models.CharField(blank=True, default="", max_length=128)),
                ("revision_count", models.PositiveIntegerField(default=1)),
                ("duplicate_count", models.PositiveIntegerField(default=0)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "memory_chunk",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="observation_links",
                        to="orm.memorychunk",
                    ),
                ),
            ],
            options={
                "db_table": "memory_observations",
                "ordering": ["-last_seen_at", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "last_seen_at"], name="mem_obs_tenant_seen_idx"
                    ),
                    models.Index(
                        fields=["tenant_id", "topic_key"], name="mem_obs_tenant_topic_idx"
                    ),
                    models.Index(
                        fields=["tenant_id", "scope", "last_seen_at"],
                        name="mem_obs_scope_seen_idx",
                    ),
                    models.Index(fields=["tenant_id", "deleted_at"], name="mem_obs_deleted_idx"),
                    models.Index(
                        fields=["tenant_id", "type", "last_seen_at"],
                        name="mem_obs_type_seen_idx",
                    ),
                ],
                "constraints": [
                    _make_check_constraint(
                        ~(
                            models.Q(graph_id__isnull=True)
                            & models.Q(run_id__isnull=True)
                            & models.Q(session_id__isnull=True)
                        ),
                        name="mem_obs_requires_scope",
                    ),
                    _make_check_constraint(
                        ~(models.Q(scope="graph") & models.Q(graph_id__isnull=True)),
                        name="mem_obs_graph_scope_req",
                    ),
                    _make_check_constraint(
                        ~(models.Q(scope="run") & models.Q(run_id__isnull=True)),
                        name="mem_obs_run_scope_req",
                    ),
                    _make_check_constraint(
                        ~(models.Q(scope="session") & models.Q(session_id__isnull=True)),
                        name="mem_obs_session_scope_req",
                    ),
                ],
            },
        ),
    ]
