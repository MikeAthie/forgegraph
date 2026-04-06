"""Projected task API URLs."""

from django.urls import path

from adapters.api.tasks.views import TaskDetailView, TaskListView

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("<uuid:task_id>", TaskDetailView.as_view(), name="task-detail"),
]
