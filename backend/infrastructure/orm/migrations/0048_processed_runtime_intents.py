from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0047_run_resume_requested_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedRuntimeIntent",
            fields=[
                ("intent_id", models.UUIDField(primary_key=True, serialize=False)),
                ("intent_type", models.CharField(max_length=64)),
                ("attempt_id", models.CharField(blank=True, default="", max_length=64)),
                ("trace_id", models.CharField(blank=True, default="", max_length=32)),
                ("stream_message_id", models.CharField(blank=True, default="", max_length=64)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="processed_runtime_intents",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "processed_runtime_intents",
                "ordering": ["processed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="processedruntimeintent",
            index=models.Index(
                fields=["run", "processed_at"],
                name="rt_intents_run_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="processedruntimeintent",
            index=models.Index(
                fields=["intent_type", "processed_at"],
                name="rt_intents_type_time_idx",
            ),
        ),
    ]
