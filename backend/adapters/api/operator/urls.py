from django.urls import path

from adapters.api.operator.views import (
    OperatorDeadLetterListView,
    OperatorEventDeadLetterAcknowledgeView,
    OperatorEventDeadLetterReplayView,
    OperatorForceCancelRunView,
    OperatorForceFailRunView,
    OperatorForceRehydrateRunView,
    OperatorOrgLoadView,
    OperatorRunStateView,
    OperatorRuntimeIntentAcknowledgeView,
    OperatorRuntimeIntentBacklogView,
    OperatorRuntimeIntentReplayView,
    OperatorTaskStateView,
    OperatorWebSocketSubscribersView,
)

urlpatterns = [
    path("runs/<uuid:run_id>/state", OperatorRunStateView.as_view(), name="operator-run-state"),
    path("tasks/<uuid:task_id>/state", OperatorTaskStateView.as_view(), name="operator-task-state"),
    path(
        "runtime-intents/backlog",
        OperatorRuntimeIntentBacklogView.as_view(),
        name="operator-runtime-intent-backlog",
    ),
    path("dead-letters", OperatorDeadLetterListView.as_view(), name="operator-dead-letters"),
    path(
        "event-dead-letters/<uuid:dead_letter_id>/replay",
        OperatorEventDeadLetterReplayView.as_view(),
        name="operator-event-dead-letter-replay",
    ),
    path(
        "event-dead-letters/<uuid:dead_letter_id>/acknowledge",
        OperatorEventDeadLetterAcknowledgeView.as_view(),
        name="operator-event-dead-letter-acknowledge",
    ),
    path(
        "runtime-intents/<uuid:intent_id>/replay",
        OperatorRuntimeIntentReplayView.as_view(),
        name="operator-runtime-intent-replay",
    ),
    path(
        "runtime-intents/<uuid:intent_id>/acknowledge",
        OperatorRuntimeIntentAcknowledgeView.as_view(),
        name="operator-runtime-intent-acknowledge",
    ),
    path(
        "runs/<uuid:run_id>/force-fail",
        OperatorForceFailRunView.as_view(),
        name="operator-force-fail-run",
    ),
    path(
        "runs/<uuid:run_id>/force-cancel",
        OperatorForceCancelRunView.as_view(),
        name="operator-force-cancel-run",
    ),
    path(
        "runs/<uuid:run_id>/force-rehydrate",
        OperatorForceRehydrateRunView.as_view(),
        name="operator-force-rehydrate-run",
    ),
    path(
        "ws/subscribers", OperatorWebSocketSubscribersView.as_view(), name="operator-ws-subscribers"
    ),
    path("org-load", OperatorOrgLoadView.as_view(), name="operator-org-load"),
]
