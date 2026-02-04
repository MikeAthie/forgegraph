"""
Template API routes.
"""

from django.urls import path

from adapters.api.templates.views import TemplateCloneView, TemplateListView

urlpatterns = [
    path("", TemplateListView.as_view(), name="template-list"),
    path("<uuid:template_id>/clone", TemplateCloneView.as_view(), name="template-clone"),
]
