"""
Add indexes for run history queries.

Phase 4 (Observability MVP): optimize common run list/detail access patterns.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0002_seed_builtin_prompts"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="run",
            index=models.Index(fields=["owner", "started_at"], name="runs_owner_started_idx"),
        ),
        migrations.AddIndex(
            model_name="run",
            index=models.Index(fields=["owner", "status"], name="runs_owner_status_idx"),
        ),
        migrations.AddIndex(
            model_name="noderun",
            index=models.Index(
                fields=["run", "started_at", "attempt"], name="node_runs_run_time_idx"
            ),
        ),
    ]
