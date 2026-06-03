from __future__ import annotations

from django.db import migrations


HERMES_GATEWAY_DOCS_URL = "https://github.com/NousResearch/hermes-agent/tree/main/gateway/platforms"


HERMES_GATEWAY_CONNECTORS = [
    {
        "slug": "hermes-api-server-gateway",
        "name": "Hermes API Server Gateway",
        "summary": "Expose a gateway HTTP API endpoint for programmatic chat ingress and delivery callbacks.",
        "icon": "api",
        "url": "https://gateway.example.com/messages",
        "body": '{"conversation_id":"{{input.conversation_id}}","text":"{{input.text}}","metadata":{{input.metadata}}}',
        "output_key": "hermes_api_server_response",
        "source_file": "gateway/platforms/api_server.py",
        "setup_fields": ["API_SERVER_ENABLED", "API_SERVER_KEY", "API_SERVER_HOST", "API_SERVER_PORT"],
    },
    {
        "slug": "hermes-bluebubbles-gateway",
        "name": "Hermes BlueBubbles Gateway",
        "summary": "Send and receive iMessage conversations through the BlueBubbles gateway adapter.",
        "icon": "bluebubbles",
        "url": "{{credential.server_url}}/api/v1/message/text",
        "body": '{"chatGuid":"{{input.chat_guid}}","message":"{{input.text}}"}',
        "output_key": "bluebubbles_message",
        "source_file": "gateway/platforms/bluebubbles.py",
        "setup_fields": ["BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_PASSWORD"],
    },
    {
        "slug": "hermes-dingtalk-gateway",
        "name": "Hermes DingTalk Gateway",
        "summary": "Route agent messages into DingTalk group and direct-message workflows.",
        "icon": "dingtalk",
        "url": "https://oapi.dingtalk.com/robot/send?access_token={{credential.api_key}}",
        "body": '{"msgtype":"text","text":{"content":"{{input.text}}"}}',
        "output_key": "dingtalk_message",
        "source_file": "gateway/platforms/dingtalk.py",
        "setup_fields": ["DINGTALK_ACCESS_TOKEN", "DINGTALK_SECRET"],
    },
    {
        "slug": "hermes-email-gateway",
        "name": "Hermes Email Gateway",
        "summary": "Send gateway replies and workflow summaries through SMTP or mailbox-backed email delivery.",
        "icon": "email",
        "url": "smtp://{{credential.smtp_host}}:{{credential.smtp_port}}",
        "body": '{"to":"{{input.to}}","subject":"{{input.subject}}","text":"{{input.text}}"}',
        "output_key": "email_delivery",
        "source_file": "gateway/platforms/email.py",
        "setup_fields": ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "IMAP_HOST"],
    },
    {
        "slug": "hermes-feishu-gateway",
        "name": "Hermes Feishu Gateway",
        "summary": "Connect Feishu chats, group messages, and app events to ForgeGraph workflows.",
        "icon": "feishu",
        "url": "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={{input.receive_id_type}}",
        "body": '{"receive_id":"{{input.receive_id}}","msg_type":"text","content":"{\\"text\\":\\"{{input.text}}\\"}"}',
        "output_key": "feishu_message",
        "source_file": "gateway/platforms/feishu.py",
        "setup_fields": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN"],
    },
    {
        "slug": "hermes-feishu-comment-gateway",
        "name": "Hermes Feishu Comment Gateway",
        "summary": "Watch Feishu document comments and route review threads back to the agent workspace.",
        "icon": "feishu",
        "url": "https://open.feishu.cn/open-apis/drive/v1/files/{{input.file_token}}/comments",
        "body": '{"reply":"{{input.text}}","comment_id":"{{input.comment_id}}"}',
        "output_key": "feishu_comment_reply",
        "source_file": "gateway/platforms/feishu_comment.py",
        "setup_fields": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_COMMENT_RULES"],
    },
    {
        "slug": "hermes-homeassistant-gateway",
        "name": "Hermes Home Assistant Gateway",
        "summary": "Deliver workflow actions to Home Assistant services and automation endpoints.",
        "icon": "homeassistant",
        "url": "{{credential.base_url}}/api/services/{{input.domain}}/{{input.service}}",
        "body": "{{input.service_data}}",
        "output_key": "homeassistant_service_call",
        "source_file": "gateway/platforms/homeassistant.py",
        "setup_fields": ["HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"],
    },
    {
        "slug": "hermes-matrix-gateway",
        "name": "Hermes Matrix Gateway",
        "summary": "Bridge Matrix rooms and encrypted chat workflows into the agent gateway.",
        "icon": "matrix",
        "url": "{{credential.homeserver_url}}/_matrix/client/v3/rooms/{{input.room_id}}/send/m.room.message/{{input.txn_id}}",
        "body": '{"msgtype":"m.text","body":"{{input.text}}"}',
        "output_key": "matrix_message",
        "source_file": "gateway/platforms/matrix.py",
        "setup_fields": ["MATRIX_HOMESERVER", "MATRIX_ACCESS_TOKEN", "MATRIX_USER_ID"],
    },
    {
        "slug": "hermes-msgraph-webhook-gateway",
        "name": "Hermes Microsoft Graph Gateway",
        "summary": "Receive Microsoft Graph webhook events and send Teams-compatible chat updates.",
        "icon": "microsoft",
        "url": "https://graph.microsoft.com/v1.0/chats/{{input.chat_id}}/messages",
        "body": '{"body":{"contentType":"text","content":"{{input.text}}"}}',
        "output_key": "msgraph_message",
        "source_file": "gateway/platforms/msgraph_webhook.py",
        "setup_fields": ["MSGRAPH_TENANT_ID", "MSGRAPH_CLIENT_ID", "MSGRAPH_CLIENT_SECRET"],
    },
    {
        "slug": "hermes-qqbot-gateway",
        "name": "Hermes QQ Bot Gateway",
        "summary": "Connect QQ Bot channels and guild messages to the ForgeGraph operator surface.",
        "icon": "qq",
        "url": "https://api.sgroup.qq.com/channels/{{input.channel_id}}/messages",
        "body": '{"content":"{{input.text}}"}',
        "output_key": "qqbot_message",
        "source_file": "gateway/platforms/qqbot/",
        "setup_fields": ["QQBOT_APP_ID", "QQBOT_TOKEN", "QQBOT_APP_SECRET"],
    },
    {
        "slug": "hermes-signal-gateway",
        "name": "Hermes Signal Gateway",
        "summary": "Send Signal messages through a signal-cli backed gateway adapter with rate-limit awareness.",
        "icon": "signal",
        "url": "{{credential.signal_cli_rest_url}}/v2/send",
        "body": '{"number":"{{credential.phone_number}}","recipients":["{{input.recipient}}"],"message":"{{input.text}}"}',
        "output_key": "signal_message",
        "source_file": "gateway/platforms/signal.py",
        "setup_fields": ["SIGNAL_CLI_REST_URL", "SIGNAL_PHONE_NUMBER"],
    },
    {
        "slug": "hermes-slack-gateway",
        "name": "Hermes Slack Gateway",
        "summary": "Route Slack app mentions, channel messages, and workflow notifications through the gateway.",
        "icon": "slack",
        "url": "https://slack.com/api/chat.postMessage",
        "body": '{"channel":"{{input.channel}}","text":"{{input.text}}"}',
        "output_key": "slack_message",
        "source_file": "gateway/platforms/slack.py",
        "setup_fields": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"],
    },
    {
        "slug": "hermes-sms-gateway",
        "name": "Hermes SMS Gateway",
        "summary": "Send SMS responses and alerts through the gateway messaging adapter.",
        "icon": "sms",
        "url": "https://api.twilio.com/2010-04-01/Accounts/{{credential.account_sid}}/Messages.json",
        "body": "To={{input.to}}&From={{credential.from_number}}&Body={{input.text}}",
        "output_key": "sms_message",
        "source_file": "gateway/platforms/sms.py",
        "setup_fields": ["SMS_PROVIDER", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
    },
    {
        "slug": "hermes-telegram-gateway",
        "name": "Hermes Telegram Gateway",
        "summary": "Connect Telegram bot conversations, voice messages, and channel delivery to workflows.",
        "icon": "telegram",
        "url": "https://api.telegram.org/bot{{credential.api_key}}/sendMessage",
        "body": '{"chat_id":"{{input.chat_id}}","text":"{{input.text}}"}',
        "output_key": "telegram_message",
        "source_file": "gateway/platforms/telegram.py",
        "setup_fields": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"],
    },
    {
        "slug": "hermes-webhook-gateway",
        "name": "Hermes Webhook Gateway",
        "summary": "Accept generic webhooks and dispatch agent responses to arbitrary HTTP endpoints.",
        "icon": "webhook",
        "url": "{{input.webhook_url}}",
        "body": '{"text":"{{input.text}}","context":{{input.context}}}',
        "output_key": "webhook_dispatch",
        "source_file": "gateway/platforms/webhook.py",
        "setup_fields": ["WEBHOOK_SHARED_SECRET", "WEBHOOK_BASE_URL"],
    },
    {
        "slug": "hermes-wecom-gateway",
        "name": "Hermes WeCom Gateway",
        "summary": "Bridge WeCom callbacks and application messages into gateway conversations.",
        "icon": "wecom",
        "url": "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={{credential.access_token}}",
        "body": '{"touser":"{{input.to_user}}","msgtype":"text","agentid":"{{credential.agent_id}}","text":{"content":"{{input.text}}"}}',
        "output_key": "wecom_message",
        "source_file": "gateway/platforms/wecom.py",
        "setup_fields": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET", "WECOM_TOKEN", "WECOM_AES_KEY"],
    },
    {
        "slug": "hermes-weixin-gateway",
        "name": "Hermes Weixin Gateway",
        "summary": "Connect Weixin official account messages and callback replies to the agent gateway.",
        "icon": "weixin",
        "url": "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={{credential.access_token}}",
        "body": '{"touser":"{{input.open_id}}","msgtype":"text","text":{"content":"{{input.text}}"}}',
        "output_key": "weixin_message",
        "source_file": "gateway/platforms/weixin.py",
        "setup_fields": ["WEIXIN_APP_ID", "WEIXIN_APP_SECRET", "WEIXIN_TOKEN", "WEIXIN_AES_KEY"],
    },
    {
        "slug": "hermes-whatsapp-gateway",
        "name": "Hermes WhatsApp Gateway",
        "summary": "Route WhatsApp conversations and customer replies through the gateway adapter.",
        "icon": "whatsapp",
        "url": "https://graph.facebook.com/v20.0/{{credential.phone_number_id}}/messages",
        "body": '{"messaging_product":"whatsapp","to":"{{input.to}}","type":"text","text":{"body":"{{input.text}}"}}',
        "output_key": "whatsapp_message",
        "source_file": "gateway/platforms/whatsapp.py",
        "setup_fields": ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN"],
    },
    {
        "slug": "hermes-yuanbao-gateway",
        "name": "Hermes Yuanbao Gateway",
        "summary": "Connect Yuanbao chat, media, protocol, and sticker events through the gateway platform.",
        "icon": "yuanbao",
        "url": "https://yuanbao.tencent.com/api/chat/send",
        "body": '{"conversation_id":"{{input.conversation_id}}","content":"{{input.text}}"}',
        "output_key": "yuanbao_message",
        "source_file": "gateway/platforms/yuanbao.py",
        "setup_fields": ["YUANBAO_COOKIE", "YUANBAO_DEVICE_ID"],
    },
]


COMMON_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "method": {"type": "string"},
        "url": {"type": "string"},
        "headers": {"type": "object"},
        "body": {"type": "string"},
        "output_key": {"type": "string"},
        "setup_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["method", "url"],
}


def seed_hermes_gateway_connectors(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    for connector in HERMES_GATEWAY_CONNECTORS:
        package, _ = NodeRegistryPackage.objects.update_or_create(
            slug=connector["slug"],
            defaults={
                "name": connector["name"],
                "summary": connector["summary"],
                "category": "communication",
                "icon": connector["icon"],
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
                "package_kind": "template_http",
                "execution_node_type": "http",
                "manifest_version": 2,
                "cloud_allowed": True,
                "changelog": "Seeded from NousResearch Hermes Agent gateway platform catalog.",
                "ui_schema": {
                    "label": connector["name"],
                    "description": connector["summary"],
                    "category": "gateway",
                    "source": "NousResearch/hermes-agent",
                    "source_path": connector["source_file"],
                    "setup_fields": connector["setup_fields"],
                    "adapter_note": "Template connector: credentials and durable install state remain backend-owned.",
                },
                "config_schema": COMMON_CONFIG_SCHEMA,
                "config_defaults": {
                    "method": "POST",
                    "url": connector["url"],
                    "headers": {"Content-Type": "application/json"},
                    "body": connector["body"],
                    "output_key": connector["output_key"],
                    "setup_fields": connector["setup_fields"],
                },
            },
        )


def unseed_hermes_gateway_connectors(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryPackage.objects.filter(slug__in=[item["slug"] for item in HERMES_GATEWAY_CONNECTORS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0094_product_operation"),
    ]

    operations = [
        migrations.RunPython(seed_hermes_gateway_connectors, unseed_hermes_gateway_connectors),
    ]
