"""
Graphs API URLs.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import path

from adapters.api.graphs.views import (
    GraphDetailView,
    GraphListCreateView,
    GraphValidateView,
    GraphVersionDetailView,
    GraphVersionLatestView,
    GraphVersionListCreateView,
)

urlpatterns = [
    path("", GraphListCreateView.as_view(), name="graph-list-create"),
    path("validate", GraphValidateView.as_view(), name="graph-validate"),
    path("<uuid:graph_id>", GraphDetailView.as_view(), name="graph-detail"),
    path(
        "<uuid:graph_id>/versions",
        GraphVersionListCreateView.as_view(),
        name="graph-version-list-create",
    ),
    path(
        "<uuid:graph_id>/versions/latest",
        GraphVersionLatestView.as_view(),
        name="graph-version-latest",
    ),
    path(
        "<uuid:graph_id>/versions/<uuid:version_id>",
        GraphVersionDetailView.as_view(),
        name="graph-version-detail",
    ),
]
