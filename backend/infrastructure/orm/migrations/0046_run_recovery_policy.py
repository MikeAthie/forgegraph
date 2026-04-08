from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0045_run_liveness_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="recovery_policy",
            field=models.CharField(
                choices=[("fail", "Fail"), ("retry", "Retry"), ("resume", "Resume")],
                default="fail",
                max_length=16,
            ),
        ),
    ]
