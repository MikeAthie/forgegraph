from __future__ import annotations

from django.db import migrations, models


def backfill_marketplace_release_contract(apps, schema_editor):
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    kind_by_execution_type = {
        "http": "template_http",
        "prompt": "template_prompt",
        "tool": "runtime_tool",
        "transform": "runtime_transform",
    }

    for release in NodeRegistryRelease.objects.all().iterator():
        package_kind = kind_by_execution_type.get(release.execution_node_type, "template_http")
        cloud_allowed = release.execution_node_type != "transform"
        NodeRegistryRelease.objects.filter(pk=release.pk).update(
            package_kind=package_kind,
            manifest_version=1,
            cloud_allowed=cloud_allowed,
            review_notes="",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0039_external_workflow_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="noderegistryrelease",
            name="cloud_allowed",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="noderegistryrelease",
            name="manifest_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="noderegistryrelease",
            name="package_kind",
            field=models.CharField(
                choices=[
                    ("template_http", "Template HTTP"),
                    ("template_prompt", "Template Prompt"),
                    ("runtime_tool", "Runtime Tool"),
                    ("runtime_transform", "Runtime Transform"),
                ],
                default="template_http",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="noderegistryrelease",
            name="review_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="noderegistryrelease",
            name="runtime_manifest",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunPython(
            backfill_marketplace_release_contract,
            migrations.RunPython.noop,
        ),
    ]
