"""
API URL configuration.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import include, path

urlpatterns = [
    path("auth/", include("adapters.api.auth.urls")),
    path("graphs/", include("adapters.api.graphs.urls")),
    path("prompts/", include("adapters.api.prompts.urls")),
    path("runs/", include("adapters.api.runs.urls")),
    path("approvals/", include("adapters.api.approvals.urls")),
]
