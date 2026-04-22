from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0048_processed_runtime_intents"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="dispatch_graph_json",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
