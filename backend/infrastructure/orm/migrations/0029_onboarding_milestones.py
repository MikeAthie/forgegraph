import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0028_template_library_v1"),
    ]

    operations = [
        migrations.CreateModel(
            name="OnboardingMilestone",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("milestone", models.CharField(max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("completed_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="onboarding_milestones",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "onboarding_milestones",
            },
        ),
        migrations.AddIndex(
            model_name="onboardingmilestone",
            index=models.Index(fields=["tenant_id", "milestone"], name="onboarding_milestone_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="onboardingmilestone",
            unique_together={("user", "milestone")},
        ),
    ]
