from django.urls import path

from adapters.api.billing.views import (
    BillingCheckoutView,
    BillingPlansView,
    BillingPortalView,
    BillingSubscriptionView,
    StripeWebhookView,
)

urlpatterns = [
    path("plans", BillingPlansView.as_view(), name="billing-plans"),
    path("subscription", BillingSubscriptionView.as_view(), name="billing-subscription"),
    path("checkout", BillingCheckoutView.as_view(), name="billing-checkout"),
    path("portal", BillingPortalView.as_view(), name="billing-portal"),
    path("webhook", StripeWebhookView.as_view(), name="billing-webhook"),
]
