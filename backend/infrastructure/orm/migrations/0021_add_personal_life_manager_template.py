"""
Add Personal Life Manager template to quick start.
"""

import uuid

from django.db import migrations
from django.db.models import F


def add_personal_life_manager_template(apps, schema_editor):
    GraphTemplate = apps.get_model("orm", "GraphTemplate")

    # Shift existing templates down to make room at position 0
    GraphTemplate.objects.filter(is_active=True).update(display_order=F("display_order") + 1)

    template = {
        "name": "Personal Life Manager",
        "description": "AI assistant that manages emails, calendar, and tasks with voice and text support.",
        "category": "productivity",
        "tags": ["assistant", "email", "calendar", "tasks", "voice", "featured"],
        "estimated_minutes": 3,
        "sample_input": {
            "message": "What's on my calendar today and do I have any unread emails?",
            "user_name": "Alex",
            "timezone": "America/New_York",
        },
        "graph_json": {
            "metadata": {
                "name": "Personal Life Manager",
                "description": "A personal AI assistant that helps manage your digital life - emails, calendar, and tasks.",
            },
            "nodes": [
                {
                    "id": "intent_classifier",
                    "type": "prompt",
                    "name": "Understand Request",
                    "config": {
                        "prompt_template": (
                            "You are a personal assistant named Jackie helping {{input.user_name}}.\n\n"
                            "User message: {{input.message}}\n\n"
                            "Analyze this request and determine what the user needs help with.\n"
                            "Categories: email, calendar, tasks, general_chat\n\n"
                            "Respond with:\n"
                            "1. Intent category (one or more from above)\n"
                            "2. Specific action needed (summarize, create, list, etc.)\n"
                            "3. Any extracted parameters (dates, names, priorities)\n\n"
                            "Format as structured analysis."
                        ),
                        "system_prompt": (
                            "You are Jackie, a helpful personal AI assistant. "
                            "You help users manage their emails, calendar events, and tasks. "
                            "Be concise and action-oriented."
                        ),
                        "model": "gpt-4",
                        "temperature": 0.2,
                        "max_tokens": 400,
                    },
                },
                {
                    "id": "email_tool",
                    "type": "tool",
                    "name": "Check Emails",
                    "config": {
                        "tool_name": "gmail_reader",
                        "description": "Fetches unread emails with sender, date, subject, and summary",
                        "parameters": {
                            "max_results": 10,
                            "unread_only": True,
                        },
                    },
                },
                {
                    "id": "calendar_tool",
                    "type": "tool",
                    "name": "Check Calendar",
                    "config": {
                        "tool_name": "google_calendar",
                        "description": "Retrieves calendar events for the specified date range",
                        "parameters": {
                            "days_ahead": 7,
                            "timezone": "{{input.timezone}}",
                        },
                    },
                },
                {
                    "id": "tasks_tool",
                    "type": "tool",
                    "name": "Manage Tasks",
                    "config": {
                        "tool_name": "google_tasks",
                        "description": "List or create tasks in Google Tasks",
                        "parameters": {
                            "action": "list",
                            "include_completed": False,
                        },
                    },
                },
                {
                    "id": "response_generator",
                    "type": "prompt",
                    "name": "Generate Response",
                    "config": {
                        "prompt_template": (
                            "You are Jackie, a personal assistant for {{input.user_name}}.\n\n"
                            "Original request: {{input.message}}\n\n"
                            "Intent analysis:\n{{nodes.intent_classifier.output}}\n\n"
                            "Available data:\n"
                            "- Emails: {{nodes.email_tool.output}}\n"
                            "- Calendar: {{nodes.calendar_tool.output}}\n"
                            "- Tasks: {{nodes.tasks_tool.output}}\n\n"
                            "Current timezone: {{input.timezone}}\n\n"
                            "Generate a helpful, conversational response that:\n"
                            "1. Directly addresses the user's request\n"
                            "2. Summarizes relevant information clearly\n"
                            "3. Suggests next actions if appropriate\n"
                            "4. Keeps the tone friendly but professional"
                        ),
                        "system_prompt": (
                            "You are Jackie, a personal AI assistant. "
                            "Provide clear, actionable responses. "
                            "Use bullet points for lists. "
                            "Be concise but thorough."
                        ),
                        "model": "gpt-4",
                        "temperature": 0.4,
                        "max_tokens": 800,
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "name": "Assistant Response",
                    "config": {},
                },
            ],
            "edges": [
                {"id": "e1", "from": "intent_classifier", "to": "email_tool"},
                {"id": "e2", "from": "intent_classifier", "to": "calendar_tool"},
                {"id": "e3", "from": "intent_classifier", "to": "tasks_tool"},
                {"id": "e4", "from": "email_tool", "to": "response_generator"},
                {"id": "e5", "from": "calendar_tool", "to": "response_generator"},
                {"id": "e6", "from": "tasks_tool", "to": "response_generator"},
                {"id": "e7", "from": "response_generator", "to": "output"},
            ],
        },
    }

    GraphTemplate.objects.create(
        id=uuid.uuid4(),
        name=template["name"],
        description=template["description"],
        category=template["category"],
        tags=template["tags"],
        estimated_minutes=template["estimated_minutes"],
        graph_json=template["graph_json"],
        sample_input=template["sample_input"],
        display_order=0,  # Top of the list
        is_active=True,
    )


def remove_personal_life_manager_template(apps, schema_editor):
    GraphTemplate = apps.get_model("orm", "GraphTemplate")
    GraphTemplate.objects.filter(name="Personal Life Manager").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0020_graph_templates"),
    ]

    operations = [
        migrations.RunPython(
            add_personal_life_manager_template,
            remove_personal_life_manager_template,
        ),
    ]
