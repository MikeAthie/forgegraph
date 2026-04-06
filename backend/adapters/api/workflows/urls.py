"""Workflow alias API URLs."""

from django.urls import include, path

urlpatterns = [
    path("", include("adapters.api.graphs.urls")),
]
