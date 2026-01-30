"""
Memory API routes.
"""

from django.urls import path

from adapters.api.memory.usage_views import MemoryUsageView

urlpatterns = [
    path("usage", MemoryUsageView.as_view(), name="memory-usage"),
]
