"""Projected task API URLs."""

from django.urls import path

from adapters.api.tasks.views import (
    TaskDetailView,
    TaskJudgeEvaluationView,
    TaskJudgeView,
    TaskListView,
)

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("<uuid:task_id>", TaskDetailView.as_view(), name="task-detail"),
    path("<uuid:task_id>/judge", TaskJudgeView.as_view(), name="task-judge"),
    path(
        "<uuid:task_id>/judge/evaluate",
        TaskJudgeEvaluationView.as_view(),
        name="task-judge-evaluate",
    ),
]
