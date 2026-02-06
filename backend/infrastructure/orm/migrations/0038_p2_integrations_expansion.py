from __future__ import annotations

import uuid

from django.db import migrations, models


def seed_p2_marketplace_integrations(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    packages = [
        {
            "slug": "whatsapp-send-message",
            "name": "WhatsApp Send Message",
            "summary": "Send WhatsApp replies using Twilio credentials and message metadata.",
            "category": "communication",
            "icon": "whatsapp",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "twilio",
                "method": "POST",
                "url": "https://api.twilio.com/2010-04-01/Accounts/{{input.account_sid}}/Messages.json",
                "headers": {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                "body": "To={{input.to}}&From={{input.from}}&Body={{input.body}}",
                "output_key": "whatsapp_send_response",
            },
        },
        {
            "slug": "gmail-list-unread",
            "name": "Gmail List Unread",
            "summary": "Fetch unread Gmail messages for triage workflows.",
            "category": "communication",
            "icon": "gmail",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "gmail",
                "method": "GET",
                "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults=5",
                "headers": {},
                "output_key": "gmail_unread_messages",
            },
        },
        {
            "slug": "google-calendar-list-events",
            "name": "Google Calendar List Events",
            "summary": "List calendar events for a date range.",
            "category": "productivity",
            "icon": "calendar",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "google_calendar",
                "method": "GET",
                "url": "https://www.googleapis.com/calendar/v3/calendars/primary/events?singleEvents=true&orderBy=startTime&timeMin={{input.time_min}}&timeMax={{input.time_max}}",
                "headers": {},
                "output_key": "google_calendar_events",
            },
        },
        {
            "slug": "google-calendar-create-event",
            "name": "Google Calendar Create Event",
            "summary": "Create calendar events with title, schedule, and attendees.",
            "category": "productivity",
            "icon": "calendar-plus",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "google_calendar",
                "method": "POST",
                "url": "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                "headers": {"Content-Type": "application/json"},
                "body": "{{input.event_json}}",
                "output_key": "google_calendar_create_response",
            },
        },
        {
            "slug": "google-tasks-list",
            "name": "Google Tasks List",
            "summary": "List tasks from a Google Tasks list.",
            "category": "productivity",
            "icon": "check-square",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "google_tasks",
                "method": "GET",
                "url": "https://tasks.googleapis.com/tasks/v1/lists/{{input.task_list_id}}/tasks?showCompleted={{input.show_completed}}",
                "headers": {},
                "output_key": "google_tasks_items",
            },
        },
        {
            "slug": "google-tasks-create",
            "name": "Google Tasks Create",
            "summary": "Create tasks with due date and notes.",
            "category": "productivity",
            "icon": "check-plus",
            "execution_node_type": "http",
            "config_defaults": {
                "provider": "google_tasks",
                "method": "POST",
                "url": "https://tasks.googleapis.com/tasks/v1/lists/{{input.task_list_id}}/tasks",
                "headers": {"Content-Type": "application/json"},
                "body": "{{input.task_json}}",
                "output_key": "google_tasks_create_response",
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
                "changelog": "Initial P2 integration release.",
                "ui_schema": {
                    "label": item["name"],
                    "description": item["summary"],
                    "category": "integration",
                },
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string"},
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
        ("orm", "0037_oauth_and_marketplace_expansion"),
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
                    ("google_calendar", "Google Calendar"),
                    ("google_tasks", "Google Tasks"),
                    ("notion", "Notion"),
                    ("slack", "Slack"),
                    ("jira", "Jira"),
                    ("linear", "Linear"),
                    ("hubspot", "HubSpot"),
                    ("google_drive", "Google Drive"),
                    ("telegram", "Telegram"),
                    ("twilio", "Twilio"),
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
                    ("google_calendar", "Google Calendar"),
                    ("google_tasks", "Google Tasks"),
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
        migrations.RunPython(seed_p2_marketplace_integrations, migrations.RunPython.noop),
    ]
