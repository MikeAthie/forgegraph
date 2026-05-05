from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0061_processed_commands_llmusage_external_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationDomainEventSequence",
            fields=[
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="domain_event_sequence",
                        serialize=False,
                        to="orm.organization",
                    ),
                ),
                ("next_sequence", models.BigIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "organization_domain_event_sequences",
            },
        ),
        migrations.CreateModel(
            name="DomainEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("aggregate_type", models.CharField(max_length=64)),
                ("aggregate_id", models.UUIDField(db_index=True)),
                ("event_type", models.CharField(max_length=128)),
                ("event_version", models.IntegerField(default=1)),
                ("sequence", models.BigIntegerField()),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domain_events",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "domain_events",
                "ordering": ["organization_id", "sequence"],
            },
        ),
        migrations.CreateModel(
            name="ProjectionCursor",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("projection_name", models.CharField(max_length=128)),
                ("last_sequence", models.BigIntegerField(default=0)),
                ("last_event_id", models.UUIDField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("fresh", "Fresh"),
                            ("stale", "Stale"),
                            ("rebuilding", "Rebuilding"),
                            ("degraded", "Degraded"),
                        ],
                        default="fresh",
                        max_length=32,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="projection_cursors",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "projection_cursors",
                "ordering": ["projection_name"],
            },
        ),
        migrations.CreateModel(
            name="ProcessedProjectionEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("projection_name", models.CharField(max_length=128)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_projection_events",
                        to="orm.domainevent",
                    ),
                ),
            ],
            options={
                "db_table": "processed_projection_events",
                "ordering": ["-processed_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="domainevent",
            constraint=models.UniqueConstraint(
                fields=("organization", "sequence"), name="domain_events_org_sequence_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="domainevent",
            index=models.Index(
                fields=["organization", "sequence"], name="domain_events_org_seq_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="domainevent",
            index=models.Index(
                fields=["tenant_id", "event_type"], name="domain_events_tenant_type_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="domainevent",
            index=models.Index(
                fields=["aggregate_type", "aggregate_id", "sequence"],
                name="domain_events_agg_seq_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="projectioncursor",
            constraint=models.UniqueConstraint(
                fields=("projection_name", "organization"),
                name="projection_cursor_name_org_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="projectioncursor",
            index=models.Index(
                fields=["organization", "projection_name"], name="projection_cursor_org_name_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="processedprojectionevent",
            constraint=models.UniqueConstraint(
                fields=("projection_name", "event"), name="uniq_projection_event_once"
            ),
        ),
    ]
