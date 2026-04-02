"""Agent registry API URLs."""

from django.urls import path

from adapters.api.agents.views import AgentDetailView, AgentListView

urlpatterns = [
    path("", AgentListView.as_view(), name="agent-list"),
    path("<uuid:agent_id>", AgentDetailView.as_view(), name="agent-detail"),
]
