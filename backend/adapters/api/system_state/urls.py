"""System state API URLs."""

from django.urls import path

from adapters.api.system_state.views import SystemStateOverviewView

urlpatterns = [
    path("overview", SystemStateOverviewView.as_view(), name="system-state-overview"),
]
