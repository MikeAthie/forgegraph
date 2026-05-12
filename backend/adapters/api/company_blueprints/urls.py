"""Company blueprint URL configuration."""

from django.urls import path

from adapters.api.company_blueprints.views import (
    CompanyBlueprintCompileView,
    CompanyFromBlueprintView,
)

urlpatterns = [
    path(
        "company-blueprints/compile",
        CompanyBlueprintCompileView.as_view(),
        name="company-blueprints-compile",
    ),
    path(
        "companies/from-blueprint",
        CompanyFromBlueprintView.as_view(),
        name="companies-from-blueprint",
    ),
]
