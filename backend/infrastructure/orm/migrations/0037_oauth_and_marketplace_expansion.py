from __future__ import annotations

import uuid

from django.db import migrations, models


def seed_additional_marketplace_integrations(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    packages = [
        {
            "slug": "gmail-send-email",
            "name": "Gmail Send Email",
            "summary": "Send templated emails via Gmail OAuth credentials.",
            "category": "communication",
            "icon": "gmail",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                "headers": {"Content-Type": "application/json"},
                "body": '{"raw":"{{input.raw_message_base64url}}"}',
                "output_key": "gmail_send_response",
            },
        },
        {
            "slug": "google-drive-file-create",
            "name": "Google Drive File Create",
            "summary": "Create files in Google Drive using OAuth credentials.",
            "category": "storage",
            "icon": "google-drive",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                "headers": {"Content-Type": "multipart/related"},
                "body": "{{input.multipart_body}}",
                "output_key": "google_drive_file",
            },
        },
        {
            "slug": "hubspot-contact-upsert",
            "name": "HubSpot Contact Upsert",
            "summary": "Create or update HubSpot contacts from workflow data.",
            "category": "crm",
            "icon": "hubspot",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://api.hubapi.com/crm/v3/objects/contacts",
                "headers": {"Content-Type": "application/json"},
                "body": '{"properties":{{input.properties}}}',
                "output_key": "hubspot_contact",
            },
        },
        {
            "slug": "telegram-send-message",
            "name": "Telegram Send Message",
            "summary": "Send Telegram bot messages using API-key style credentials.",
            "category": "communication",
            "icon": "telegram",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://api.telegram.org/bot{{credential.api_key}}/sendMessage",
                "headers": {"Content-Type": "application/json"},
                "body": '{"chat_id":"{{input.chat_id}}","text":"{{input.text}}"}',
                "output_key": "telegram_response",
            },
        },
        {
            "slug": "github-issue-create",
            "name": "GitHub Issue Create",
            "summary": "Create GitHub issues from failures and support requests.",
            "category": "developer",
            "icon": "github",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://api.github.com/repos/{{input.owner}}/{{input.repo}}/issues",
                "headers": {"Content-Type": "application/json"},
                "body": '{"title":"{{input.title}}","body":"{{input.body}}"}',
                "output_key": "github_issue",
            },
        },
        {
            "slug": "salesforce-record-upsert",
            "name": "Salesforce Record Upsert",
            "summary": "Upsert Salesforce records for CRM sync workflows.",
            "category": "crm",
            "icon": "salesforce",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "PATCH",
                "url": "https://{{input.instance_url}}/services/data/v59.0/sobjects/{{input.object}}/{{input.external_id}}",
                "headers": {"Content-Type": "application/json"},
                "body": "{{input.fields_json}}",
                "output_key": "salesforce_record",
            },
        },
    ]

    for item in packages:
        package, _ = NodeRegistryPackage.objects.get_or_create(
            slug=item["slug"],
            defaults={
                "id": uuid.uuid4(),
                "name": item["name"],
                "summary": item["summary"],
                "category": item["category"],
                "icon": item["icon"],
                "is_active": True,
            },
        )

        NodeRegistryRelease.objects.get_or_create(
            package=package,
            version="1.0.0",
            defaults={
                "status": "approved",
                "execution_node_type": item["execution_node_type"],
                "changelog": "Initial integration release.",
                "ui_schema": {
                    "label": item["name"],
                    "description": item["summary"],
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
                "config_defaults": item["config_defaults"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0036_integration_expansion"),
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
                    ("hubspot", "HubSpot"),
                    ("google_drive", "Google Drive"),
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
                    ("hubspot", "HubSpot"),
                    ("google_drive", "Google Drive"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(seed_additional_marketplace_integrations, migrations.RunPython.noop),
    ]
