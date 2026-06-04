"""Integration API URL configuration."""

from django.urls import path

from adapters.api.integrations.gateway_views import GatewayWebhookView
from adapters.api.integrations.http_test_views import HttpNodeTestView
from adapters.api.integrations.telegram_views import TelegramWebhookView
from adapters.api.integrations.webhook_views import GenericWebhookView
from adapters.api.integrations.whatsapp_views import WhatsAppWebhookView

urlpatterns = [
    path("http/test", HttpNodeTestView.as_view(), name="http-node-test"),
    path(
        "telegram/webhook/<uuid:graph_version_id>",
        TelegramWebhookView.as_view(),
        name="telegram-webhook",
    ),
    path(
        "whatsapp/webhook/<uuid:graph_version_id>",
        WhatsAppWebhookView.as_view(),
        name="whatsapp-webhook",
    ),
    path("webhook/<uuid:graph_version_id>", GenericWebhookView.as_view(), name="generic-webhook"),
    path(
        "gateway/<str:platform>/webhook/<uuid:graph_version_id>",
        GatewayWebhookView.as_view(),
        name="gateway-webhook",
    ),
]
