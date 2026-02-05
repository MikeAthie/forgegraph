"""
Template API routes.
"""

from django.urls import path

from adapters.api.templates.views import (
    TemplateCloneView,
    TemplateListView,
    TemplateRatingView,
    TemplateShareView,
    TemplateVersionsView,
)

urlpatterns = [
    path("", TemplateListView.as_view(), name="template-list"),
    path("<uuid:template_id>/clone", TemplateCloneView.as_view(), name="template-clone"),
    path("<uuid:template_id>/versions", TemplateVersionsView.as_view(), name="template-versions"),
    path("<uuid:template_id>/ratings", TemplateRatingView.as_view(), name="template-rating"),
    path("<uuid:template_id>/shares", TemplateShareView.as_view(), name="template-share"),
    path(
        "<uuid:template_id>/shares/<uuid:organization_id>",
        TemplateShareView.as_view(),
        name="template-unshare",
    ),
]
