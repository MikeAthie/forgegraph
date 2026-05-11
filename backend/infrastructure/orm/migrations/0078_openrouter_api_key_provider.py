from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0077_taskjudge"),
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
                    ("openrouter", "OpenRouter"),
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
                    ("stripe", "Stripe"),
                ],
                max_length=32,
            ),
        ),
    ]
