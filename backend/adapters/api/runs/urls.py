"""
Runs API URLs (stub for Phase 4).

Clean Architecture: Interface Adapters layer.
"""

from django.urls import path

from adapters.api.runs.views import (
    RunCancelView,
    RunDetailView,
    RunListView,
    RunResumeView,
    RunStartView,
)

urlpatterns = [
    path("", RunListView.as_view(), name="run-list"),
    path("start", RunStartView.as_view(), name="run-start"),
    path("<uuid:run_id>", RunDetailView.as_view(), name="run-detail"),
    path("<uuid:run_id>/cancel", RunCancelView.as_view(), name="run-cancel"),
    path("<uuid:run_id>/resume", RunResumeView.as_view(), name="run-resume"),
]
