from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0057_task_lifecycle_retry_recovery"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceMetricSample",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("metric_name", models.CharField(max_length=128)),
                ("source", models.CharField(max_length=64)),
                ("value", models.FloatField(default=0.0)),
                ("unit", models.CharField(blank=True, default="", max_length=32)),
                ("dimensions", models.JSONField(blank=True, default=dict)),
                ("observed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="service_metric_samples",
                        to="orm.organization",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="service_metric_samples",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "service_metric_samples",
                "ordering": ["-observed_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="servicemetricsample",
            index=models.Index(fields=["metric_name", "observed_at"], name="svc_metric_name_time_idx"),
        ),
        migrations.AddIndex(
            model_name="servicemetricsample",
            index=models.Index(fields=["source", "observed_at"], name="svc_metric_source_time_idx"),
        ),
        migrations.AddIndex(
            model_name="servicemetricsample",
            index=models.Index(
                fields=["organization", "metric_name", "observed_at"],
                name="svc_metric_org_name_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servicemetricsample",
            index=models.Index(fields=["run", "metric_name"], name="svc_metric_run_name_idx"),
        ),
    ]
