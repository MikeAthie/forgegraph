from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0062_domain_event_projections"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationStateFeedSequence",
            fields=[
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="state_feed_sequence",
                        serialize=False,
                        to="orm.organization",
                    ),
                ),
                ("next_sequence", models.BigIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "organization_state_feed_sequences",
            },
        ),
        migrations.CreateModel(
            name="OrganizationStateFeedEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("event_id", models.CharField(max_length=128)),
                ("state_version", models.PositiveBigIntegerField()),
                ("type", models.CharField(max_length=96)),
                ("resource_type", models.CharField(blank=True, default="", max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=128)),
                ("requires_refetch", models.BooleanField(default=True)),
                ("message", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_state_feed_events",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "organization_state_feed_events",
                "ordering": ["organization_id", "state_version"],
            },
        ),
        migrations.AddConstraint(
            model_name="organizationstatefeedevent",
            constraint=models.UniqueConstraint(
                fields=("organization", "state_version"),
                name="org_state_feed_org_version_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationstatefeedevent",
            constraint=models.UniqueConstraint(
                fields=("organization", "event_id"),
                name="org_state_feed_org_event_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationstatefeedevent",
            index=models.Index(
                fields=["organization", "state_version"],
                name="org_state_feed_org_ver_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationstatefeedevent",
            index=models.Index(
                fields=["organization", "type", "state_version"],
                name="org_state_feed_type_ver_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationstatefeedevent",
            index=models.Index(
                fields=["organization", "resource_type", "resource_id"],
                name="org_state_feed_resource_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationstatefeedevent",
            index=models.Index(
                fields=["organization", "created_at"],
                name="org_state_feed_created_idx",
            ),
        ),
    ]
