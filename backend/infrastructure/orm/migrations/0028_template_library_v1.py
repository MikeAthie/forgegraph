import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def backfill_template_versions(apps, schema_editor):
    GraphTemplate = apps.get_model("orm", "GraphTemplate")
    for template in GraphTemplate.objects.all():
        template.group_id = template.id
        template.version = template.version or 1
        template.is_latest = True
        if not template.visibility:
            template.visibility = "public"
        template.save(
            update_fields=[
                "group_id",
                "version",
                "is_latest",
                "visibility",
            ]
        )


def seed_template_guides(apps, schema_editor):
    GraphTemplate = apps.get_model("orm", "GraphTemplate")
    guides = {
        "Investor Update Email (Human Gate)": [
            "Connect an LLM credential for the draft step.",
            "Run the workflow and approve the draft in the approvals queue.",
            "Copy the final output into your email client.",
        ],
        "Research Brief": [
            "Paste a topic and source material.",
            "Run the workflow to generate the executive summary.",
            "Share the brief with stakeholders.",
        ],
        "Customer FAQ Generator": [
            "Add a short product description.",
            "Run the workflow to produce FAQs.",
            "Review and export the final FAQ list.",
        ],
    }

    for name, guide_steps in guides.items():
        GraphTemplate.objects.filter(name=name).update(guide_steps=guide_steps)


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0027_sso_scim_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="graphtemplate",
            name="group_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="guide_steps",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="changelog",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="is_latest",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("organization", "Organization"),
                    ("private", "Private"),
                ],
                default="public",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="graphtemplate",
            name="owner_organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="graph_templates",
                to="orm.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="graphtemplate",
            index=models.Index(fields=["group_id", "version"], name="graph_templates_group_idx"),
        ),
        migrations.AddIndex(
            model_name="graphtemplate",
            index=models.Index(
                fields=["is_latest", "visibility"], name="graph_templates_latest_idx"
            ),
        ),
        migrations.CreateModel(
            name="TemplateShare",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="template_shares",
                        to="orm.organization",
                    ),
                ),
                (
                    "shared_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="shared_templates",
                        to="orm.user",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="shares",
                        to="orm.graphtemplate",
                    ),
                ),
            ],
            options={
                "db_table": "template_shares",
            },
        ),
        migrations.CreateModel(
            name="TemplateUsage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "graph",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="template_usage_events",
                        to="orm.graph",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="template_usage_events",
                        to="orm.organization",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="usage_events",
                        to="orm.graphtemplate",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="template_usage_events",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "template_usage",
            },
        ),
        migrations.CreateModel(
            name="TemplateRating",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                (
                    "rating",
                    models.PositiveIntegerField(
                        validators=[MinValueValidator(1), MaxValueValidator(5)]
                    ),
                ),
                ("comment", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="template_ratings",
                        to="orm.organization",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="ratings",
                        to="orm.graphtemplate",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="template_ratings",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "template_ratings",
            },
        ),
        migrations.AddIndex(
            model_name="templateshare",
            index=models.Index(fields=["organization"], name="template_shares_org_idx"),
        ),
        migrations.AddIndex(
            model_name="templateusage",
            index=models.Index(
                fields=["template", "created_at"], name="template_usage_template_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="templateusage",
            index=models.Index(
                fields=["organization", "created_at"], name="template_usage_org_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="templaterating",
            index=models.Index(fields=["template", "rating"], name="template_ratings_template_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="templateshare",
            unique_together={("template", "organization")},
        ),
        migrations.AlterUniqueTogether(
            name="templaterating",
            unique_together={("template", "user")},
        ),
        migrations.RunPython(backfill_template_versions, migrations.RunPython.noop),
        migrations.RunPython(seed_template_guides, migrations.RunPython.noop),
    ]
