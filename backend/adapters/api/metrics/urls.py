from django.urls import path

from adapters.api.metrics.views import MetricsSloView, MetricsSummaryView

urlpatterns = [
    path("summary", MetricsSummaryView.as_view(), name="metrics-summary"),
    path("slo", MetricsSloView.as_view(), name="metrics-slo"),
]
