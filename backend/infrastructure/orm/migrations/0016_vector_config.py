from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0015_memory_chunks"),
    ]

    operations = [
        migrations.AddField(
            model_name="memoryconfiguration",
            name="vector_recency_weight",
            field=models.FloatField(default=0.2),
        ),
        migrations.AddField(
            model_name="memoryconfiguration",
            name="embedding_model",
            field=models.CharField(default="text-embedding-ada-002", max_length=50),
        ),
    ]
