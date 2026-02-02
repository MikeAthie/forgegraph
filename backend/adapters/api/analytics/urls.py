"""
Analytics API routes.
"""

from django.urls import path

from adapters.api.analytics.memory_analytics import (
    MemoryCostsAnalyticsView,
    MemoryPerformanceAnalyticsView,
    MemoryUsageAnalyticsView,
)

urlpatterns = [
    path("memory/usage", MemoryUsageAnalyticsView.as_view(), name="memory-analytics-usage"),
    path("memory/costs", MemoryCostsAnalyticsView.as_view(), name="memory-analytics-costs"),
    path(
        "memory/performance",
        MemoryPerformanceAnalyticsView.as_view(),
        name="memory-analytics-performance",
    ),
]
