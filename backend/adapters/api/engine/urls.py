from django.urls import path

from adapters.api.engine.views import (
    EngineCredentialDetailView,
    EngineMemoryEntryView,
    EngineNodeCacheDetailView,
    EngineRunCheckpointView,
    EngineRunDetailView,
    EngineRunNodeRunDetailView,
    EngineRunNodeRunListView,
    EngineRunPauseStateView,
    EngineRunSnapshotView,
)

urlpatterns = [
    path(
        "credentials/<uuid:credential_id>",
        EngineCredentialDetailView.as_view(),
        name="engine-credential-detail",
    ),
    path("runs/<uuid:run_id>", EngineRunDetailView.as_view(), name="engine-run-detail"),
    path(
        "runs/<uuid:run_id>/pause-state",
        EngineRunPauseStateView.as_view(),
        name="engine-run-pause-state",
    ),
    path(
        "runs/<uuid:run_id>/checkpoint",
        EngineRunCheckpointView.as_view(),
        name="engine-run-checkpoint",
    ),
    path(
        "runs/<uuid:run_id>/snapshot",
        EngineRunSnapshotView.as_view(),
        name="engine-run-snapshot",
    ),
    path(
        "runs/<uuid:run_id>/node-runs",
        EngineRunNodeRunListView.as_view(),
        name="engine-run-node-run-list",
    ),
    path(
        "runs/<uuid:run_id>/node-runs/<str:node_id>",
        EngineRunNodeRunDetailView.as_view(),
        name="engine-run-node-run-detail",
    ),
    path(
        "node-cache/<str:cache_key>",
        EngineNodeCacheDetailView.as_view(),
        name="engine-node-cache-detail",
    ),
    path(
        "memory/entries",
        EngineMemoryEntryView.as_view(),
        name="engine-memory-entry",
    ),
]
