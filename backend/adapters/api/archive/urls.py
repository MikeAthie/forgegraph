"""Company archive URL configuration."""

from django.urls import path

from adapters.api.archive.views import (
    AssetDetailView,
    AssetListView,
    AssetVersionContentView,
    AssetVersionListView,
    ContextPackDetailView,
    EvidenceLinkListView,
    MediaGenerationCreateView,
    MediaGenerationDetailView,
    MediaGenerationPollView,
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
        "assets/<uuid:asset_id>/versions/<uuid:version_id>/content",
        AssetVersionContentView.as_view(),
        name="archive-asset-version-content",
    ),
    path(
        "media-generations",
        MediaGenerationCreateView.as_view(),
        name="archive-media-generations",
    ),
    path(
        "media-generations/<uuid:job_id>",
        MediaGenerationDetailView.as_view(),
        name="archive-media-generation-detail",
    ),
    path(
        "media-generations/<uuid:job_id>/poll",
        MediaGenerationPollView.as_view(),
        name="archive-media-generation-poll",
    ),
    path(
        "context-packs/<uuid:context_pack_id>",
        ContextPackDetailView.as_view(),
        name="archive-context-pack-detail",
    ),
    path("evidence-links", EvidenceLinkListView.as_view(), name="archive-evidence-links"),
]
