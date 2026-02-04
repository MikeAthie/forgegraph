"""
Analytics API routes.
"""

from django.urls import path

from adapters.api.analytics.llm_analytics import (
    LLMBudgetView,
    LLMCostsAnalyticsView,
    LLMQuotaView,
    LLMUsageExportView,
    LLMUsageAnalyticsView,
)
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
    path("llm/usage", LLMUsageAnalyticsView.as_view(), name="llm-analytics-usage"),
    path("llm/export", LLMUsageExportView.as_view(), name="llm-analytics-export"),
    path("llm/costs", LLMCostsAnalyticsView.as_view(), name="llm-analytics-costs"),
    path("llm/budget", LLMBudgetView.as_view(), name="llm-analytics-budget"),
    path("llm/quota", LLMQuotaView.as_view(), name="llm-analytics-quota"),
]
