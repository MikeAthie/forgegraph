from django.urls import path

from adapters.api.ops.views import (
    OpsDeadLetterDetailView,
    OpsDeadLetterListView,
    OpsDeadLetterReplayView,
    OpsDeadLetterResolveView,
    OpsEventSpoolView,
    OpsProjectionLagView,
    OpsRuntimeIntentLagView,
)

urlpatterns = [
    path("dead-letters", OpsDeadLetterListView.as_view(), name="ops-dead-letters"),
    path(
        "dead-letters/<str:dead_letter_key>",
        OpsDeadLetterDetailView.as_view(),
        name="ops-dead-letter-detail",
    ),
    path(
        "dead-letters/<str:dead_letter_key>/replay",
        OpsDeadLetterReplayView.as_view(),
        name="ops-dead-letter-replay",
    ),
    path(
        "dead-letters/<str:dead_letter_key>/resolve",
        OpsDeadLetterResolveView.as_view(),
        name="ops-dead-letter-resolve",
    ),
    path("projection-lag", OpsProjectionLagView.as_view(), name="ops-projection-lag"),
    path("event-spool", OpsEventSpoolView.as_view(), name="ops-event-spool"),
    path("runtime-intent-lag", OpsRuntimeIntentLagView.as_view(), name="ops-runtime-intent-lag"),
]
