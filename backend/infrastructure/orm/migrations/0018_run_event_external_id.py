from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0017_memory_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="runevent",
            name="external_id",
            field=models.CharField(
                blank=True,
                help_text="Idempotency key from engine events (event_id).",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="runevent",
            index=models.Index(fields=["run", "external_id"], name="run_events_run_external_idx"),
        ),
        migrations.AddConstraint(
            model_name="runevent",
            constraint=models.UniqueConstraint(
                fields=["run", "external_id"],
                name="run_events_run_external_uniq",
            ),
        ),
    ]
