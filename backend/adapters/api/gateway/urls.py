"""Gateway platform API routes."""

from django.urls import path

from adapters.api.gateway.views import (
    GatewayCapabilityListView,
    GatewayConnectionDetailView,
    GatewayConnectionDiagnosticsView,
    GatewayConnectionHealthView,
    GatewayConnectionListCreateView,
    GatewayScheduleDetailView,
    GatewayScheduleListCreateView,
    GatewayScheduleRunNowView,
)

urlpatterns = [
    path("capabilities", GatewayCapabilityListView.as_view(), name="gateway-capabilities"),
    path("connections", GatewayConnectionListCreateView.as_view(), name="gateway-connections"),
    path(
        "connections/<uuid:connection_id>",
        GatewayConnectionDetailView.as_view(),
        name="gateway-connection-detail",
    ),
    path(
        "connections/<uuid:connection_id>/health-check",
        GatewayConnectionHealthView.as_view(),
        name="gateway-connection-health",
    ),
    path(
        "connections/<uuid:connection_id>/diagnostics",
        GatewayConnectionDiagnosticsView.as_view(),
        name="gateway-connection-diagnostics",
    ),
    path("schedules", GatewayScheduleListCreateView.as_view(), name="gateway-schedules"),
    path(
        "schedules/<uuid:schedule_id>",
        GatewayScheduleDetailView.as_view(),
        name="gateway-schedule-detail",
    ),
    path(
        "schedules/<uuid:schedule_id>/run-now",
        GatewayScheduleRunNowView.as_view(),
        name="gateway-schedule-run-now",
    ),
]
