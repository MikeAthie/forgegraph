from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0032_alter_nodepackageinstallation_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntegrationOAuthProviderConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenant_id", models.UUIDField()),
                (
                    "provider",
                    models.CharField(
                        choices=[("gmail", "Gmail"), ("notion", "Notion")],
                        max_length=32,
                    ),
                ),
                ("client_id", models.CharField(max_length=255)),
                ("encrypted_client_secret", models.BinaryField()),
                ("authorize_url", models.URLField()),
                ("token_url", models.URLField()),
                ("redirect_uri", models.URLField(blank=True, default="")),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("authorize_extra_params", models.JSONField(blank=True, default=dict)),
                ("token_extra_params", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "integration_oauth_provider_configs",
                "unique_together": {("tenant_id", "provider")},
            },
        ),
        migrations.AddIndex(
            model_name="integrationoauthproviderconfig",
            index=models.Index(
                fields=["tenant_id", "provider"],
                name="int_oauth_tenant_provider_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="integrationoauthproviderconfig",
            index=models.Index(
                fields=["tenant_id", "enabled"],
                name="int_oauth_tenant_enabled_idx",
            ),
        ),
    ]
