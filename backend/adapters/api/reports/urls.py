from django.urls import path

from adapters.api.reports.views import StrategyReportGenerateView

urlpatterns = [
    path("strategy-report", StrategyReportGenerateView.as_view(), name="strategy-report-generate"),
]
