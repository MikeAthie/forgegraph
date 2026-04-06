"""Decision ledger API URLs."""

from django.urls import path

from adapters.api.decisions.views import DecisionCountView, DecisionDetailView, DecisionListView

urlpatterns = [
    path("", DecisionListView.as_view(), name="decision-list"),
    path("count", DecisionCountView.as_view(), name="decision-count"),
    path("<uuid:decision_id>", DecisionDetailView.as_view(), name="decision-detail"),
]
