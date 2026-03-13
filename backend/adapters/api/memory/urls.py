"""
Memory API routes.
"""

from django.urls import path

from adapters.api.memory.gc_views import MemoryGCView
from adapters.api.memory.observation_views import (
    MemoryObservationContextView,
    MemoryObservationDetailView,
    MemoryObservationListCreateView,
    MemoryObservationSearchView,
    MemoryObservationTimelineView,
)
from adapters.api.memory.usage_views import MemoryUsageView

urlpatterns = [
    path("usage", MemoryUsageView.as_view(), name="memory-usage"),
    path("gc", MemoryGCView.as_view(), name="memory-gc"),
    path("observations", MemoryObservationListCreateView.as_view(), name="memory-observation-list"),
    path(
        "observations/search",
        MemoryObservationSearchView.as_view(),
        name="memory-observation-search",
    ),
    path(
        "observations/timeline",
        MemoryObservationTimelineView.as_view(),
        name="memory-observation-timeline",
    ),
    path(
        "observations/context",
        MemoryObservationContextView.as_view(),
        name="memory-observation-context",
    ),
    path(
        "observations/<uuid:observation_id>",
        MemoryObservationDetailView.as_view(),
        name="memory-observation-detail",
    ),
]
