from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0034_alter_apikey_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="encrypted_refresh_token",
            field=models.BinaryField(
                blank=True,
                help_text="Fernet-encrypted OAuth refresh token",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="apikey",
            name="token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="apikey",
            name="token_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
