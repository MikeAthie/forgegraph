"""URL configuration for generic service catalog and engagements."""

from django.urls import path

from adapters.api.service_engagements.views import (
    ServiceCatalogDetailView,
    ServiceCatalogListCreateView,
    ServiceDeliverableListCreateView,
    ServiceEngagementDetailView,
    ServiceEngagementListCreateView,
)

urlpatterns = [
    path("service-catalog", ServiceCatalogListCreateView.as_view(), name="service-catalog-list-create"),
    path("service-catalog/<uuid:service_id>", ServiceCatalogDetailView.as_view(), name="service-catalog-detail"),
    path(
        "service-engagements",
        ServiceEngagementListCreateView.as_view(),
        name="service-engagement-list-create",
    ),
    path(
        "service-engagements/<uuid:engagement_id>",
        ServiceEngagementDetailView.as_view(),
        name="service-engagement-detail",
    ),
    path(
        "service-engagements/<uuid:engagement_id>/deliverables",
        ServiceDeliverableListCreateView.as_view(),
        name="service-engagement-deliverables",
    ),
]
