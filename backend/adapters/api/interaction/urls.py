"""Interaction layer URL configuration."""

from django.urls import path

from adapters.api.interaction.views import CurrentOperatingBriefView, InteractionEventCreateView

urlpatterns = [
    path("briefs/current", CurrentOperatingBriefView.as_view(), name="interaction-brief-current"),
    path("events", InteractionEventCreateView.as_view(), name="interaction-event-create"),
]
