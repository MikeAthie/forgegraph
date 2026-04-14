from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0046_run_recovery_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="run",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("paused", "Paused"),
                    ("resume_requested", "Resume Requested"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("canceled", "Canceled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="runeventprojection",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("paused", "Paused"),
                    ("resume_requested", "Resume Requested"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("canceled", "Canceled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="run",
            name="recovery_reason",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="run",
            name="resume_attempt_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="run",
            name="resume_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
