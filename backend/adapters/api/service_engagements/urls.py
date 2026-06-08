"""URL configuration for generic service catalog and engagements."""

from django.urls import path

from adapters.api.service_engagements.views import (
    AtlasDeliverableAssembleView,
    ServiceCatalogDetailView,
    ServiceCatalogListCreateView,
    ServiceDeliverableActionView,
    ServiceDeliverableListCreateView,
    ServiceEngagementDepartmentPipelineStageActionView,
    ServiceEngagementDepartmentPipelineView,
    ServiceEngagementDetailView,
    ServiceEngagementListCreateView,
)

urlpatterns = [
    path(
        "service-catalog",
        ServiceCatalogListCreateView.as_view(),
        name="service-catalog-list-create",
    ),
    path(
        "service-catalog/<uuid:service_id>",
        ServiceCatalogDetailView.as_view(),
        name="service-catalog-detail",
    ),
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
        "service-engagements/<uuid:engagement_id>/department-pipeline",
        ServiceEngagementDepartmentPipelineView.as_view(),
        name="service-engagement-department-pipeline",
    ),
    path(
        "service-engagements/<uuid:engagement_id>/department-pipeline/stages/<str:stage_id>/<str:action>",
        ServiceEngagementDepartmentPipelineStageActionView.as_view(),
        name="service-engagement-department-pipeline-stage-action",
    ),
    path(
        "service-engagements/<uuid:engagement_id>/deliverables",
        ServiceDeliverableListCreateView.as_view(),
        name="service-engagement-deliverables",
    ),
    path(
        "service-deliverables/<uuid:deliverable_id>/actions",
        ServiceDeliverableActionView.as_view(),
        name="service-deliverable-actions",
    ),
    path(
        "whiteboards/<uuid:whiteboard_id>/atlas-deliverables/assemble",
        AtlasDeliverableAssembleView.as_view(),
        name="whiteboard-atlas-deliverables-assemble",
    ),
]
