from __future__ import annotations

import uuid

from django.db import migrations, models


def seed_linear_marketplace_package(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    package, _ = NodeRegistryPackage.objects.get_or_create(
        slug="linear-issue-create",
        defaults={
            "id": uuid.uuid4(),
            "name": "Linear Issue Create",
            "summary": "Create Linear issues from workflow outputs and incidents.",
            "category": "developer",
            "icon": "linear",
            "is_active": True,
        },
    )

    NodeRegistryRelease.objects.get_or_create(
        package=package,
        version="1.0.0",
        defaults={
            "status": "approved",
            "execution_node_type": "http",
            "changelog": "Initial Linear integration release.",
            "ui_schema": {
                "label": "Linear Issue Create",
                "description": "Create issues in Linear",
                "category": "integration",
            },
            "config_schema": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "url": {"type": "string"},
                    "headers": {"type": "object"},
                    "body": {"type": "string"},
                    "output_key": {"type": "string"},
                },
                "required": ["method", "url"],
            },
            "config_defaults": {
                "method": "POST",
                "url": "https://api.linear.app/graphql",
                "headers": {"Content-Type": "application/json"},
                "body": '{"query":"mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier title } } }","variables":{"input":{{input.issue}}}}',
                "output_key": "linear_issue",
            },
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0035_apikey_oauth_token_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apikey",
            name="provider",
            field=models.CharField(
                choices=[
                    ("openai", "OpenAI"),
                    ("anthropic", "Anthropic"),
                    ("google", "Google AI"),
                    ("gmail", "Gmail"),
                    ("notion", "Notion"),
                    ("slack", "Slack"),
                    ("jira", "Jira"),
                    ("linear", "Linear"),
                    ("telegram", "Telegram"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="integrationoauthproviderconfig",
            name="provider",
            field=models.CharField(
                choices=[
                    ("gmail", "Gmail"),
                    ("notion", "Notion"),
                    ("slack", "Slack"),
                    ("jira", "Jira"),
                    ("linear", "Linear"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(seed_linear_marketplace_package, migrations.RunPython.noop),
    ]
