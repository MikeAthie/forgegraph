"""URL configuration for routing APIs."""

from django.urls import path

from adapters.api.routing.views import (
    RoutingInboxView,
    RoutingPolicyDetailView,
    RoutingPolicyListCreateView,
    RoutingRecordDetailView,
)

urlpatterns = [
    path("inbox", RoutingInboxView.as_view(), name="routing-inbox"),
    path("policies", RoutingPolicyListCreateView.as_view(), name="routing-policy-list-create"),
    path("policies/<uuid:policy_id>", RoutingPolicyDetailView.as_view(), name="routing-policy-detail"),
    path("records/<uuid:record_id>", RoutingRecordDetailView.as_view(), name="routing-record-detail"),
]
