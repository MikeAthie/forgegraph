from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models

HERMES_GATEWAY_DOCS_URL = "https://github.com/NousResearch/hermes-agent/tree/main/gateway/platforms"


CAPABILITY_SEEDS = [
    ("api_server", "api_server", "API Server", "api_server", ["send", "inbound_webhook"]),
    ("bluebubbles", "bluebubbles", "BlueBubbles", "bluebubbles", ["send", "inbound_webhook", "sidecar"]),
    ("dingtalk", "dingtalk", "DingTalk", "dingtalk", ["send", "inbound_webhook"]),
    ("email", "gmail", "Gmail", "gmail", ["send", "poll", "media"]),
    ("email", "smtp", "SMTP Email", "gmail", ["send"]),
    ("feishu", "feishu", "Feishu", "feishu", ["send", "inbound_webhook", "media"]),
    ("feishu_comment", "feishu", "Feishu Comments", "feishu", ["send", "poll"]),
    ("homeassistant", "homeassistant", "Home Assistant", "homeassistant", ["send", "health_check"]),
    ("matrix", "matrix", "Matrix", "matrix", ["send", "poll", "media"]),
    ("msgraph_webhook", "microsoft_graph", "Microsoft Graph", "microsoft_graph", ["send", "inbound_webhook"]),
    ("qqbot", "qqbot", "QQ Bot", "qqbot", ["send", "inbound_webhook"]),
    ("signal", "signal", "Signal", "signal", ["send", "poll", "sidecar"]),
    ("slack", "slack", "Slack", "slack", ["send", "inbound_webhook", "media", "typing"]),
    ("sms", "twilio", "SMS", "twilio", ["send", "inbound_webhook"]),
    ("telegram", "telegram", "Telegram", "telegram", ["send", "inbound_webhook", "media"]),
    ("webhook", "generic_webhook", "Generic Webhook", "generic_webhook", ["send", "inbound_webhook"]),
    ("wecom", "wecom", "WeCom", "wecom", ["send", "inbound_webhook"]),
    ("weixin", "weixin", "Weixin", "weixin", ["send", "inbound_webhook"]),
    ("whatsapp", "whatsapp_cloud_api", "WhatsApp Cloud API", "whatsapp", ["send", "inbound_webhook", "media"]),
    ("whatsapp", "twilio", "Twilio WhatsApp", "twilio", ["send", "inbound_webhook"]),
    ("yuanbao", "yuanbao", "Yuanbao", "yuanbao", ["send", "poll", "media"]),
]


SETUP_REQUIREMENTS = {
    "api_server": ["API_SERVER_KEY"],
    "bluebubbles": ["BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_PASSWORD"],
    "dingtalk": ["DINGTALK_ACCESS_TOKEN", "DINGTALK_SECRET"],
    "email:gmail": ["GMAIL_ACCESS_TOKEN"],
    "email:smtp": ["EMAIL_SMTP_HOST", "EMAIL_ADDRESS", "EMAIL_PASSWORD"],
    "feishu": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN"],
    "feishu_comment": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    "homeassistant": ["HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"],
    "matrix": ["MATRIX_HOMESERVER", "MATRIX_ACCESS_TOKEN", "MATRIX_USER_ID"],
    "msgraph_webhook": ["MSGRAPH_ACCESS_TOKEN", "MSGRAPH_CLIENT_STATE"],
    "qqbot": ["QQBOT_APP_ID", "QQBOT_TOKEN", "QQBOT_APP_SECRET"],
    "signal": ["SIGNAL_HTTP_URL", "SIGNAL_ACCOUNT"],
    "slack": ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"],
    "sms": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    "telegram": ["TELEGRAM_BOT_TOKEN"],
    "webhook": ["GENERIC_WEBHOOK_SECRET"],
    "wecom": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET"],
    "weixin": ["WEIXIN_APP_ID", "WEIXIN_APP_SECRET", "WEIXIN_TOKEN"],
    "whatsapp:whatsapp_cloud_api": ["WHATSAPP_CLOUD_API_TOKEN", "WHATSAPP_CLOUD_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN"],
    "whatsapp:twilio": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    "yuanbao": ["YUANBAO_COOKIE", "YUANBAO_DEVICE_ID"],
}


TOOLSET_PACKAGES = [
    (
        "forgegraph-toolset-messaging",
        "ForgeGraph Messaging Toolset",
        "Reviewed backend package grouping gateway messaging tools and connection diagnostics.",
        "message",
        ["gateway.telegram.send", "gateway.slack.send", "gateway.whatsapp.send", "gateway.sms.send", "gateway.email.send"],
    ),
    (
        "forgegraph-toolset-media",
        "ForgeGraph Media Toolset",
        "Reviewed backend package for gateway media artifact normalization and delivery evidence.",
        "image",
        ["gateway.telegram.send", "gateway.slack.send", "gateway.whatsapp.send", "gateway.email.send"],
    ),
    (
        "forgegraph-toolset-memory",
        "ForgeGraph Memory Toolset",
        "Reviewed backend package for curated gateway conversation observations and context packs.",
        "memory",
        [],
    ),
    (
        "forgegraph-toolset-automation",
        "ForgeGraph Automation Toolset",
        "Reviewed backend package for backend-owned gateway automation schedules.",
        "schedule",
        [],
    ),
    (
        "forgegraph-toolset-homeassistant",
        "ForgeGraph Home Assistant Toolset",
        "Reviewed backend package for Home Assistant gateway service calls.",
        "homeassistant",
        ["gateway.homeassistant.send"],
    ),
]


def _setup_requirements(platform: str, provider: str) -> list[str]:
    return SETUP_REQUIREMENTS.get(f"{platform}:{provider}") or SETUP_REQUIREMENTS.get(platform) or []


def _inbound_modes(capabilities: list[str]) -> list[str]:
    modes: list[str] = []
    if "inbound_webhook" in capabilities:
        modes.append("webhook")
    if "poll" in capabilities:
        modes.append("poll")
    return modes


def seed_capabilities_and_toolsets(apps, schema_editor):
    GatewayConnectorCapability = apps.get_model("orm", "GatewayConnectorCapability")
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    for platform, provider, display_name, credential_provider, capabilities in CAPABILITY_SEEDS:
        sidecar_required = "sidecar" in capabilities
        GatewayConnectorCapability.objects.update_or_create(
            platform=platform,
            provider=provider,
            defaults={
                "display_name": display_name,
                "credential_provider": credential_provider,
                "runtime_tool_id": f"gateway.{platform}.send",
                "capabilities_json": {
                    "send": "send" in capabilities,
                    "inbound_webhook": "inbound_webhook" in capabilities,
                    "poll": "poll" in capabilities,
                    "media": "media" in capabilities,
                    "typing": "typing" in capabilities,
                    "files": "media" in capabilities,
                    "health_check": True,
                    "sidecar_required": sidecar_required,
                },
                "setup_requirements_json": _setup_requirements(platform, provider),
                "inbound_modes_json": _inbound_modes(capabilities),
                "outbound_modes_json": ["send"] if "send" in capabilities else [],
                "sidecar_required": sidecar_required,
                "sidecar_health_path": "/health" if sidecar_required else "",
                "docs_url": HERMES_GATEWAY_DOCS_URL,
                "enabled": True,
            },
        )

    for slug, name, summary, icon, tool_ids in TOOLSET_PACKAGES:
        package, _ = NodeRegistryPackage.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "summary": summary,
                "category": "productivity",
                "icon": icon,
                "docs_url": HERMES_GATEWAY_DOCS_URL,
                "homepage_url": "https://github.com/NousResearch/hermes-agent",
                "is_active": True,
            },
        )
        NodeRegistryRelease.objects.update_or_create(
            package=package,
            version="1.0.0",
            defaults={
                "status": "approved",
                "package_kind": "template_prompt",
                "execution_node_type": "prompt",
                "manifest_version": 2,
                "cloud_allowed": True,
                "changelog": "Seeded reviewed backend-owned Hermes-inspired toolset package.",
                "ui_schema": {
                    "label": name,
                    "description": summary,
                    "category": "toolset",
                    "source": "NousResearch/hermes-agent",
                    "backend_owned": True,
                    "tool_ids": tool_ids,
                },
                "config_schema": {"type": "object"},
                "config_defaults": {"toolset": slug, "tool_ids": tool_ids},
                "runtime_manifest": None,
            },
        )


def unseed_capabilities_and_toolsets(apps, schema_editor):
    GatewayConnectorCapability = apps.get_model("orm", "GatewayConnectorCapability")
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    GatewayConnectorCapability.objects.filter(
        platform__in={item[0] for item in CAPABILITY_SEEDS}
    ).delete()
    NodeRegistryPackage.objects.filter(slug__in=[item[0] for item in TOOLSET_PACKAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0096_gateway_connector_runtime"),
    ]

    operations = [
        migrations.CreateModel(
            name="GatewayConnectorCapability",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("provider", models.CharField(max_length=64)),
                ("display_name", models.CharField(max_length=120)),
                ("credential_provider", models.CharField(blank=True, default="", max_length=64)),
                ("runtime_tool_id", models.CharField(blank=True, default="", max_length=128)),
                ("capabilities_json", models.JSONField(blank=True, default=dict)),
                ("setup_requirements_json", models.JSONField(blank=True, default=list)),
                ("inbound_modes_json", models.JSONField(blank=True, default=list)),
                ("outbound_modes_json", models.JSONField(blank=True, default=list)),
                ("sidecar_required", models.BooleanField(default=False)),
                ("sidecar_health_path", models.CharField(blank=True, default="", max_length=255)),
                ("docs_url", models.URLField(blank=True, default="")),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "gateway_connector_capabilities"},
        ),
        migrations.CreateModel(
            name="GatewayMediaArtifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("provider", models.CharField(blank=True, default="", max_length=64)),
                ("direction", models.CharField(choices=[("inbound", "Inbound"), ("outbound", "Outbound")], max_length=16)),
                ("media_kind", models.CharField(blank=True, default="", max_length=32)),
                ("content_type", models.CharField(blank=True, default="", max_length=128)),
                ("size_bytes", models.PositiveBigIntegerField(blank=True, null=True)),
                ("source_id_hash", models.CharField(blank=True, default="", max_length=96)),
                ("content_sha256", models.CharField(blank=True, default="", max_length=96)),
                ("filename_hint", models.CharField(blank=True, default="", max_length=255)),
                ("storage_ref", models.CharField(blank=True, default="", max_length=255)),
                ("external_media_id", models.CharField(blank=True, default="", max_length=255)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_media_artifacts", to="orm.asset")),
                ("asset_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_media_artifacts", to="orm.assetversion")),
                ("connection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="media_artifacts", to="orm.gatewayconnection")),
                ("inbound_receipt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="media_artifacts", to="orm.gatewayinboundreceipt")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gateway_media_artifacts", to="orm.organization")),
                ("tool_execution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_media_artifacts", to="orm.toolexecution")),
                ("transcript_observation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_media_artifacts", to="orm.memoryobservation")),
            ],
            options={"db_table": "gateway_media_artifacts"},
        ),
        migrations.CreateModel(
            name="GatewayAutomationSchedule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(max_length=64)),
                ("provider", models.CharField(blank=True, default="", max_length=64)),
                ("name", models.CharField(max_length=160)),
                ("status", models.CharField(choices=[("enabled", "Enabled"), ("disabled", "Disabled"), ("error", "Error")], default="enabled", max_length=32)),
                ("schedule_type", models.CharField(choices=[("once", "Once"), ("interval", "Interval"), ("cron", "Cron")], max_length=16)),
                ("schedule_json", models.JSONField(blank=True, default=dict)),
                ("timezone", models.CharField(blank=True, default="UTC", max_length=64)),
                ("input_template_json", models.JSONField(blank=True, default=dict)),
                ("next_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_fire_key", models.CharField(blank=True, default="", max_length=255)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=96)),
                ("last_error_message", models.TextField(blank=True, default="")),
                ("last_error_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("connection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="automation_schedules", to="orm.gatewayconnection")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_automation_schedules", to="orm.user")),
                ("graph_version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gateway_automation_schedules", to="orm.graphversion")),
                ("last_materialized_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gateway_automation_schedules", to="orm.run")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gateway_automation_schedules", to="orm.organization")),
            ],
            options={"db_table": "gateway_automation_schedules"},
        ),
        migrations.AddConstraint(
            model_name="gatewayconnectorcapability",
            constraint=models.UniqueConstraint(fields=("platform", "provider"), name="gw_cap_platform_provider_uniq"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnectorcapability",
            index=models.Index(fields=["enabled", "platform"], name="gw_cap_enabled_platform_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnectorcapability",
            index=models.Index(fields=["credential_provider"], name="gw_cap_credential_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayconnectorcapability",
            index=models.Index(fields=["runtime_tool_id"], name="gw_cap_tool_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaymediaartifact",
            index=models.Index(fields=["organization", "platform"], name="gw_media_org_platform_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaymediaartifact",
            index=models.Index(fields=["connection", "created_at"], name="gw_media_conn_time_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaymediaartifact",
            index=models.Index(fields=["inbound_receipt"], name="gw_media_receipt_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaymediaartifact",
            index=models.Index(fields=["tool_execution"], name="gw_media_tool_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewaymediaartifact",
            index=models.Index(fields=["source_id_hash"], name="gw_media_source_hash_idx"),
        ),
        migrations.AddConstraint(
            model_name="gatewayautomationschedule",
            constraint=models.UniqueConstraint(fields=("organization", "name"), name="gw_schedule_org_name_uniq"),
        ),
        migrations.AddIndex(
            model_name="gatewayautomationschedule",
            index=models.Index(fields=["organization", "status"], name="gw_sched_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayautomationschedule",
            index=models.Index(fields=["status", "next_run_at"], name="gw_sched_due_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayautomationschedule",
            index=models.Index(fields=["connection", "status"], name="gw_sched_conn_status_idx"),
        ),
        migrations.AddIndex(
            model_name="gatewayautomationschedule",
            index=models.Index(fields=["last_materialized_run"], name="gw_sched_last_run_idx"),
        ),
        migrations.RunPython(seed_capabilities_and_toolsets, unseed_capabilities_and_toolsets),
    ]
