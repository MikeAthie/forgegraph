"""Portfolio API URLs."""

from django.urls import path

from adapters.api.portfolio.views import (
    CompanyAssignmentDetailView,
    CompanyAssignmentListCreateView,
    CredentialHealthView,
    CrossCompanyQueuesView,
    PortfolioHealthView,
    PortfolioListView,
    PortfolioViewListView,
)

urlpatterns = [
    path("portfolios", PortfolioListView.as_view(), name="portfolio-list"),
    path("portfolio-views", PortfolioViewListView.as_view(), name="portfolio-view-list"),
    path("portfolio-health", PortfolioHealthView.as_view(), name="portfolio-health"),
    path("cross-company-queues", CrossCompanyQueuesView.as_view(), name="cross-company-queues"),
    path("credential-health", CredentialHealthView.as_view(), name="credential-health"),
    path(
        "company-assignments",
        CompanyAssignmentListCreateView.as_view(),
        name="company-assignment-list-create",
    ),
    path(
        "company-assignments/<uuid:assignment_id>",
        CompanyAssignmentDetailView.as_view(),
        name="company-assignment-detail",
    ),
]
