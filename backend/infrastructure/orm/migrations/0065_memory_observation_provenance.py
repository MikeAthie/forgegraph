from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0064_idempotency_boundaries"),
    ]

    operations = [
        migrations.AddField(
            model_name="memoryobservation",
            name="cost_metadata_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="memoryobservation",
            name="fact_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="memoryobservation",
            name="provenance_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="memoryobservation",
            name="retention_policy_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="memoryobservation",
            name="source_event_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="memoryobservation",
            name="source_event_type",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddIndex(
            model_name="memoryobservation",
            index=models.Index(
                fields=["tenant_id", "source_event_id"],
                name="mem_obs_source_event_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryobservation",
            index=models.Index(
                fields=["tenant_id", "fact_hash"],
                name="mem_obs_fact_hash_idx",
            ),
        ),
    ]
