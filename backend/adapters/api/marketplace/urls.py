"""Marketplace API routes."""

from django.urls import path

from adapters.api.marketplace.views import (
    MarketplaceCatalogView,
    MarketplaceInstalledView,
    MarketplaceInstallView,
    MarketplaceReleaseListCreateView,
    MarketplaceReleaseReviewView,
)

urlpatterns = [
    path("packages", MarketplaceCatalogView.as_view(), name="marketplace-packages"),
    path(
        "packages/<slug:package_slug>/install",
        MarketplaceInstallView.as_view(),
        name="marketplace-install",
    ),
    path("installed", MarketplaceInstalledView.as_view(), name="marketplace-installed"),
    path("releases", MarketplaceReleaseListCreateView.as_view(), name="marketplace-releases"),
    path(
        "releases/<uuid:release_id>/review",
        MarketplaceReleaseReviewView.as_view(),
        name="marketplace-release-review",
    ),
]
