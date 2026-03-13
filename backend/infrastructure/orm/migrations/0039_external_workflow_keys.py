from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0038_p2_integrations_expansion"),
    ]

    operations = [
        migrations.AddField(
            model_name="graph",
            name="external_ref",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="graph",
            name="external_source",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="graphversion",
            name="external_idempotency_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddConstraint(
            model_name="graph",
            constraint=models.UniqueConstraint(
                condition=models.Q(external_ref__gt=""),
                fields=("owner", "external_source", "external_ref"),
                name="graphs_owner_source_external_ref_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="graphversion",
            constraint=models.UniqueConstraint(
                condition=models.Q(external_idempotency_key__gt=""),
                fields=("graph", "external_idempotency_key"),
                name="graph_versions_idempotency_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="graph",
            index=models.Index(
                fields=["owner", "external_source", "external_ref"],
                name="graphs_external_ref_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="graphversion",
            index=models.Index(
                fields=["graph", "external_idempotency_key"],
                name="graph_versions_idempotency_idx",
            ),
        ),
    ]
