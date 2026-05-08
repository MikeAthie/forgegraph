"""Authenticated commerce URL configuration."""

from django.urls import path

from adapters.api.commerce.views import (
    CommerceOrderDetailView,
    CommerceOrdersView,
    CommerceOverviewView,
    FulfillmentBlockView,
    FulfillmentDeliverView,
    FulfillmentReadyView,
    FulfillmentShipView,
    OperatorCheckoutSessionView,
    OperatorNoteView,
)

urlpatterns = [
    path(
        "checkout-sessions",
        OperatorCheckoutSessionView.as_view(),
        name="commerce-checkout-sessions",
    ),
    path("overview", CommerceOverviewView.as_view(), name="commerce-overview"),
    path("orders", CommerceOrdersView.as_view(), name="commerce-orders"),
    path("orders/<uuid:order_id>", CommerceOrderDetailView.as_view(), name="commerce-order-detail"),
    path(
        "orders/<uuid:order_id>/fulfillment/block",
        FulfillmentBlockView.as_view(),
        name="commerce-order-fulfillment-block",
    ),
    path(
        "orders/<uuid:order_id>/fulfillment/mark-ready",
        FulfillmentReadyView.as_view(),
        name="commerce-order-fulfillment-ready",
    ),
    path(
        "orders/<uuid:order_id>/fulfillment/ship",
        FulfillmentShipView.as_view(),
        name="commerce-order-fulfillment-ship",
    ),
    path(
        "orders/<uuid:order_id>/fulfillment/deliver",
        FulfillmentDeliverView.as_view(),
        name="commerce-order-fulfillment-deliver",
    ),
    path(
        "orders/<uuid:order_id>/operator-note",
        OperatorNoteView.as_view(),
        name="commerce-order-operator-note",
    ),
]
