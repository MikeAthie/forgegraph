from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("orm", "0016_vector_config"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemorySession",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("session_id", models.UUIDField(unique=True, db_index=True)),
                ("agent_id", models.UUIDField(null=True, blank=True, db_index=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="memory_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "memory_sessions",
            },
        ),
        migrations.AddIndex(
            model_name="memorysession",
            index=models.Index(fields=["owner", "session_id"], name="memory_sessions_owner_idx"),
        ),
    ]
