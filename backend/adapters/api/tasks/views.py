"""Projected task API views."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.os_projections import refresh_phase1_projections, task_summary
from infrastructure.orm.models import TaskRecord, User


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        tasks = TaskRecord.objects.filter(organization=bundle.organization).select_related(
            "agent", "execution", "current_step", "current_decision", "lifecycle_task"
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        return success_response([task_summary(task) for task in tasks.order_by("-created_at")])


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, task_id: UUID) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        try:
            task = TaskRecord.objects.select_related(
                "agent", "execution", "current_step", "current_decision", "lifecycle_task"
            ).get(id=task_id, organization=bundle.organization)
        except TaskRecord.DoesNotExist:
            return error_response("NOT_FOUND", "Task not found", status=404)
        return success_response(task_summary(task))
