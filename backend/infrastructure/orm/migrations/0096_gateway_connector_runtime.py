from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

HERMES_RUNTIME_PLATFORMS = {
    "hermes-api-server-gateway": "api_server",
    "hermes-bluebubbles-gateway": "bluebubbles",
    "hermes-dingtalk-gateway": "dingtalk",
    "hermes-email-gateway": "email",
    "hermes-feishu-gateway": "feishu",
    "hermes-feishu-comment-gateway": "feishu_comment",
    "hermes-homeassistant-gateway": "homeassistant",
    "hermes-matrix-gateway": "matrix",
    "hermes-msgraph-webhook-gateway": "msgraph_webhook",
    "hermes-qqbot-gateway": "qqbot",
    "hermes-signal-gateway": "signal",
    "hermes-slack-gateway": "slack",
    "hermes-sms-gateway": "sms",
    "hermes-telegram-gateway": "telegram",
    "hermes-webhook-gateway": "webhook",
    "hermes-wecom-gateway": "wecom",
    "hermes-weixin-gateway": "weixin",
    "hermes-whatsapp-gateway": "whatsapp",
    "hermes-yuanbao-gateway": "yuanbao",
}


def seed_runtime_releases(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    packages = {
        package.slug: package
        for package in NodeRegistryPackage.objects.filter(slug__in=HERMES_RUNTIME_PLATFORMS)
    }
    for slug, platform in HERMES_RUNTIME_PLATFORMS.items():
        package = packages.get(slug)
        if package is None:
            continue
        tool_id = f"gateway.{platform}.send"
        NodeRegistryRelease.objects.update_or_create(
            package=package,
            version="1.1.0",
            defaults={
                "status": "approved",
                "package_kind": "runtime_tool",
                "execution_node_type": "tool",
                "manifest_version": 2,
                "cloud_allowed": True,
                "changelog": "Upgraded Hermes gateway connector to backend-owned runtime tool.",
                "ui_schema": {
                    "label": package.name,
                    "description": package.summary,
                    "category": "gateway",
                    "source": "NousResearch/hermes-agent",
                    "runtime_tool_id": tool_id,
                    "adapter_note": (
                        "Live connector: durable state, idempotency, liveness, and receipts "
                        "are backend-owned."
                    ),
                },
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string"},
                        "credential_id": {"type": "string"},
                        "connection_id": {"type": "string"},
                    },
                },
                "config_defaults": {
                    "provider": platform,
                    "tool_id": tool_id,
                },
                "runtime_manifest": {
                    "name": tool_id,
                    "version": "1.1.0",
                    "category": "communication",
                    "description": package.summary,
                    "visibility": "tenant",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "to": {"type": ["string", "array"]},
                            "text": {"type": "string"},
                            "subject": {"type": "string"},
                            "provider": {"type": "string"},
                            "credential_id": {"type": "string"},
                            "connection_id": {"type": "string"},
                            "metadata": {"type": "object"},
                        },
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "provider_message_id": {"type": "string"},
                            "sanitized": {"type": "boolean"},
                        },
                    },
                    "execution": {
                        "type": "local",
                        "timeout_seconds": 30,
                        "local": {"handler": tool_id},
                    },
                    "side_effects": {"type": "external", "idempotent": True},
                    "agent_hints": {
                        "tool_id": tool_id,
                        "requires_backend_receipt": True,
                        "requires_human_approval_for_live_send": True,
                    },
                },
            },
        )


def unseed_runtime_releases(apps, schema_editor):
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")
    NodeRegistryRelease.objects.filter(
        package__slug__in=HERMES_RUNTIME_PLATFORMS,
        version="1.1.0",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0095_hermes_gateway_connectors"),
    ]

    operations = [
        migrations.CreateModel(
            name="GatewayConnection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("provider", models.CharField(max_length=64)),
                ("name", models.CharField(blank=True, default="", max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("enabled", "Enabled"),
                            ("disabled", "Disabled"),
                            ("degraded", "Degraded"),
                            ("error", "Error"),
                        ],
                        default="enabled",
                        max_length=32,
                    ),
                ),
                ("config_json", models.JSONField(blank=True, default=dict)),
                ("allowlist_json", models.JSONField(blank=True, default=list)),
                ("webhook_secret_hash", models.CharField(blank=True, default="", max_length=128)),
                ("verify_token_hash", models.CharField(blank=True, default="", max_length=128)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_health_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=96)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "credential",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gateway_connections",
                        to="orm.apikey",
                    ),
                ),
                (
                    "graph_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gateway_connections",
                        to="orm.graphversion",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gateway_connections",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "gateway_connections",
            },
        ),
        migrations.CreateModel(
            name="GatewayConversation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("external_conversation_id", models.CharField(max_length=255)),
                ("thread_id", models.UUIDField(db_index=True)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("last_message_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversations",
                        to="orm.gatewayconnection",
                    ),
                ),
                (
                    "graph_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gateway_conversations",
                        to="orm.graphversion",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gateway_conversations",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "gateway_conversations",
            },
        ),
        migrations.CreateModel(
            name="GatewayInboundReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("provider", models.CharField(blank=True, default="", max_length=64)),
                ("external_event_id", models.CharField(max_length=255)),
                ("external_conversation_id", models.CharField(blank=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("processing", "Processing"),
                            ("accepted", "Accepted"),
                            ("ignored", "Ignored"),
                            ("failed", "Failed"),
                        ],
                        default="received",
                        max_length=32,
                    ),
                ),
                ("event_json", models.JSONField(blank=True, default=dict)),
                ("error_json", models.JSONField(blank=True, default=dict)),
                ("received_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inbound_receipts",
                        to="orm.gatewayconnection",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gateway_inbound_receipts",
                        to="orm.organization",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gateway_inbound_receipts",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "gateway_inbound_receipts",
            },
        ),
        migrations.CreateModel(
            name="GatewayPollCursor",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("cursor_key", models.CharField(max_length=128)),
                ("cursor_value", models.CharField(blank=True, default="", max_length=512)),
                ("state_json", models.JSONField(blank=True, default=dict)),
                ("last_polled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="poll_cursors",
                        to="orm.gatewayconnection",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gateway_poll_cursors",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "gateway_poll_cursors",
            },
        ),
        migrations.AddIndex(
            model_name="gatewayconnection",
            index=models.Index(fields=["organization", "platform"], name="gw_conn_org_platform_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnection",
            index=models.Index(fields=["organization", "status"], name="gw_conn_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnection",
            index=models.Index(fields=["credential"], name="gw_conn_credential_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnection",
            index=models.Index(fields=["graph_version"], name="gw_conn_graphver_idx"),
        ),
        migrations.AddConstraint(
            model_name="gatewayconnection",
            constraint=models.UniqueConstraint(
                fields=("organization", "platform", "provider", "name"),
                name="gw_conn_org_platform_provider_name_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="gatewayconversation",
            index=models.Index(fields=["organization", "thread_id"], name="gw_conv_org_thread_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconversation",
            index=models.Index(fields=["connection", "updated_at"], name="gw_conv_conn_updated_idx"),
        ),
        migrations.AddConstraint(
            model_name="gatewayconversation",
            constraint=models.UniqueConstraint(
                fields=("organization", "platform", "external_conversation_id"),
                name="gw_conv_org_platform_external_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="gatewayinboundreceipt",
            index=models.Index(fields=["organization", "status"], name="gw_inbound_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayinboundreceipt",
            index=models.Index(fields=["connection", "received_at"], name="gw_inbound_conn_recv_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayinboundreceipt",
            index=models.Index(fields=["run"], name="gw_inbound_run_idx"),
        ),
        migrations.AddConstraint(
            model_name="gatewayinboundreceipt",
            constraint=models.UniqueConstraint(
                fields=("organization", "platform", "idempotency_key"),
                name="gw_inbound_org_platform_idem_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="gatewaypollcursor",
            index=models.Index(fields=["organization", "platform"], name="gw_cursor_org_platform_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaypollcursor",
            index=models.Index(fields=["connection", "updated_at"], name="gw_cursor_conn_updated_idx"),
        ),
        migrations.AddConstraint(
            model_name="gatewaypollcursor",
            constraint=models.UniqueConstraint(
                fields=("connection", "cursor_key"),
                name="gw_cursor_connection_key_uniq",
            ),
        ),
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
                    ("api_server", "API Server"),
                    ("bluebubbles", "BlueBubbles"),
                    ("dingtalk", "DingTalk"),
                    ("feishu", "Feishu"),
                    ("generic_webhook", "Generic Webhook"),
                    ("homeassistant", "Home Assistant"),
                    ("matrix", "Matrix"),
                    ("microsoft_graph", "Microsoft Graph"),
                    ("qqbot", "QQ Bot"),
                    ("signal", "Signal"),
                    ("sms", "SMS"),
                    ("stripe", "Stripe"),
                    ("wecom", "WeCom"),
                    ("weixin", "Weixin"),
                    ("whatsapp", "WhatsApp"),
                    ("yuanbao", "Yuanbao"),
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
                    ("microsoft_graph", "Microsoft Graph"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(seed_runtime_releases, unseed_runtime_releases),
    ]
