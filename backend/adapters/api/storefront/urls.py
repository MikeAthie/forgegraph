"""Public storefront URL configuration."""

from django.urls import path

from adapters.api.storefront.views import (
    StorefrontCheckoutSessionView,
    StorefrontOrderStatusView,
    StorefrontProductsView,
    StripeWebhookView,
)

urlpatterns = [
    path(
        "stripe/webhook",
        StripeWebhookView.as_view(),
        name="storefront-stripe-webhook",
    ),
    path(
        "<slug:company_slug>/orders/<str:public_status_token>",
        StorefrontOrderStatusView.as_view(),
        name="storefront-order-status",
    ),
    path(
        "<slug:company_slug>/products",
        StorefrontProductsView.as_view(),
        name="storefront-products",
    ),
    path(
        "<slug:company_slug>/checkout-sessions",
        StorefrontCheckoutSessionView.as_view(),
        name="storefront-checkout-sessions",
    ),
]
