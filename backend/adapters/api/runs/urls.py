"""
Runs API URLs (stub for Phase 4).

Clean Architecture: Interface Adapters layer.
"""

from django.urls import path

from adapters.api.runs.views import (
    EngineRunEventsView,
    RunCancelView,
    RunDetailView,
    RunEventsStreamView,
    RunEventsView,
    RunInvokeView,
    RunListView,
    RunReplayView,
    RunResumeView,
    RunStartView,
)

urlpatterns = [
    path("", RunListView.as_view(), name="run-list"),
    path("start", RunStartView.as_view(), name="run-start"),
    path("invoke", RunInvokeView.as_view(), name="run-invoke"),
    path("<uuid:run_id>", RunDetailView.as_view(), name="run-detail"),
    path("<uuid:run_id>/cancel", RunCancelView.as_view(), name="run-cancel"),
    path("<uuid:run_id>/events", RunEventsView.as_view(), name="run-events"),
    path("engine-events", EngineRunEventsView.as_view(), name="run-engine-events"),
    path("<uuid:run_id>/stream", RunEventsStreamView.as_view(), name="run-stream"),
    path("<uuid:run_id>/resume", RunResumeView.as_view(), name="run-resume"),
    path("<uuid:run_id>/replay", RunReplayView.as_view(), name="run-replay"),
]
