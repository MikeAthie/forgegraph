"""
Health API URLs.
"""

from django.urls import path

from adapters.api.health.memory_health import MemoryHealthView
from adapters.api.health.readiness import ReadinessView

urlpatterns = [
    path("memory", MemoryHealthView.as_view(), name="memory-health"),
    path("ready", ReadinessView.as_view(), name="readiness"),
]
