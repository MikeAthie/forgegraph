"""
Health API URLs.
"""

from django.urls import path

from adapters.api.health.memory_health import MemoryHealthView

urlpatterns = [
    path("memory", MemoryHealthView.as_view(), name="memory-health"),
]
