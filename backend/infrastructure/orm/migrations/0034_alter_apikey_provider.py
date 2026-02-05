from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0033_integrationoauthproviderconfig"),
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
                    ("telegram", "Telegram"),
                ],
                max_length=32,
            ),
        ),
    ]
