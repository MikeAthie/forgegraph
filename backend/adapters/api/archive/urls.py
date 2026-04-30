"""Company archive URL configuration."""

from django.urls import path

from adapters.api.archive.views import (
    AssetDetailView,
    AssetListView,
    AssetVersionListView,
    ContextPackDetailView,
    EvidenceLinkListView,
)

urlpatterns = [
    path("assets", AssetListView.as_view(), name="archive-assets"),
    path("assets/<uuid:asset_id>", AssetDetailView.as_view(), name="archive-asset-detail"),
    path(
        "assets/<uuid:asset_id>/versions",
        AssetVersionListView.as_view(),
        name="archive-asset-versions",
    ),
    path(
        "context-packs/<uuid:context_pack_id>",
        ContextPackDetailView.as_view(),
        name="archive-context-pack-detail",
    ),
    path("evidence-links", EvidenceLinkListView.as_view(), name="archive-evidence-links"),
]
