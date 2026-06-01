"""Company alias API URLs."""

from django.urls import path

from adapters.api.companies.views import (
    CompanyDetailView,
    CompanyListCreateView,
    CompanyOperatingModelVersionCreateView,
    CompanyOperatingModelVersionLatestView,
)

urlpatterns = [
    path("", CompanyListCreateView.as_view(), name="company-list-create"),
    path("<uuid:company_id>", CompanyDetailView.as_view(), name="company-detail"),
    path(
        "<uuid:company_id>/operating-model-versions",
        CompanyOperatingModelVersionCreateView.as_view(),
        name="company-operating-model-version-create",
    ),
    path(
        "<uuid:company_id>/operating-model-versions/latest",
        CompanyOperatingModelVersionLatestView.as_view(),
        name="company-operating-model-version-latest",
    ),
]
