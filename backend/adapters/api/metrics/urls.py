from django.urls import path

from adapters.api.metrics.views import MetricsSummaryView

urlpatterns = [
    path("summary", MetricsSummaryView.as_view(), name="metrics-summary"),
]
