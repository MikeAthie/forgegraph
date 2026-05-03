from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0055_archive_learning_idempotency"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuntimeIntentOutcome",
            fields=[
                ("intent_id", models.UUIDField(primary_key=True, serialize=False)),
                (
                    "intent_type",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "attempt_id",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("processed", "Processed"),
                            ("duplicate", "Duplicate"),
                            ("ignored", "Ignored"),
                            ("invalid", "Invalid"),
                            ("dead_lettered", "Dead Lettered"),
                        ],
                        max_length=32,
                    ),
                ),
                ("reason", models.TextField(blank=True, default="")),
                (
                    "error_class",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "trace_id",
                    models.CharField(blank=True, default="", max_length=32),
                ),
                (
                    "stream_message_id",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runtime_intent_outcomes",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "runtime_intent_outcomes",
                "ordering": ["processed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="runtimeintentoutcome",
            index=models.Index(
                fields=["run", "processed_at"],
                name="rt_outcomes_run_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="runtimeintentoutcome",
            index=models.Index(
                fields=["outcome", "processed_at"],
                name="rt_outcomes_status_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="runtimeintentoutcome",
            index=models.Index(
                fields=["intent_type", "processed_at"],
                name="rt_outcomes_type_time_idx",
            ),
        ),
    ]
