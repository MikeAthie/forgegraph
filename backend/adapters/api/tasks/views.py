"""Projected task API views."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.tasks.serializers import TaskJudgeSerializer
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.os_projections import projection_organization_for_user, task_summary
from application.services.task_judges import (
    configure_task_judge,
    evaluate_task_judge,
    task_judge_payload,
)
from infrastructure.orm.models import TaskJudge, TaskRecord, User


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        organization = projection_organization_for_user(cast(User, request.user))
        tasks = TaskRecord.objects.filter(
            organization=organization,
            execution__graph_version__graph__in=accessible_company_queryset(cast(User, request.user)),
        ).select_related(
            "agent", "execution", "current_step", "current_decision", "lifecycle_task", "judge"
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        return success_response([task_summary(task) for task in tasks.order_by("-created_at")])


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, task_id: UUID) -> Response:
        organization = projection_organization_for_user(cast(User, request.user))
        try:
            task = TaskRecord.objects.select_related(
                "agent", "execution", "current_step", "current_decision", "lifecycle_task", "judge"
            ).get(
                id=task_id,
                organization=organization,
                execution__graph_version__graph__in=accessible_company_queryset(
                    cast(User, request.user)
                ),
            )
        except TaskRecord.DoesNotExist:
            return error_response("NOT_FOUND", "Task not found", status=404)
        return success_response(task_summary(task))


def _serializer_details(serializer: TaskJudgeSerializer) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for field, errors in serializer.errors.items():
        if isinstance(errors, list):
            issue = ", ".join(str(error) for error in errors)
        else:
            issue = str(errors)
        details.append({"field": str(field), "issue": issue})
    return details


def _task_for_user(user: User, task_id: UUID) -> TaskRecord | Response:
    organization = projection_organization_for_user(user)
    try:
        return TaskRecord.objects.select_related(
            "agent",
            "execution",
            "current_step",
            "current_decision",
            "lifecycle_task",
            "judge",
        ).get(
            id=task_id,
            organization=organization,
            execution__graph_version__graph__in=accessible_company_queryset(user),
        )
    except TaskRecord.DoesNotExist:
        return error_response("NOT_FOUND", "Task not found", status=404)


class TaskJudgeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, task_id: UUID) -> Response:
        task_or_response = _task_for_user(cast(User, request.user), task_id)
        if isinstance(task_or_response, Response):
            return task_or_response
        judge = getattr(task_or_response, "judge", None)
        return success_response({"judge": task_judge_payload(judge)})

    def put(self, request: Request, task_id: UUID) -> Response:
        user = cast(User, request.user)
        task_or_response = _task_for_user(user, task_id)
        if isinstance(task_or_response, Response):
            return task_or_response
        task = task_or_response
        if not has_company_access(user, task.execution.graph_version.graph, minimum_role="member"):
            return error_response(
                "FORBIDDEN",
                "You don't have permission to configure judges for this task.",
                status=403,
            )

        serializer = TaskJudgeSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "VALIDATION_ERROR",
                "The request contains invalid judge fields.",
                status=400,
                details=_serializer_details(serializer),
            )

        existing = TaskJudge.objects.filter(task=task).exists()
        judge = configure_task_judge(
            task=task,
            user=user,
            title=str(serializer.validated_data.get("title") or f"Judge: {task.title}"),
            instructions=str(serializer.validated_data.get("instructions") or ""),
            criteria=serializer.validated_data["criteria"],
            pass_threshold=int(serializer.validated_data["pass_threshold"]),
            evidence_snapshot=serializer.validated_data.get("evidence_snapshot") or {},
        )
        return success_response(
            {"judge": task_judge_payload(judge)},
            status=200 if existing else 201,
        )

    def delete(self, request: Request, task_id: UUID) -> Response:
        user = cast(User, request.user)
        task_or_response = _task_for_user(user, task_id)
        if isinstance(task_or_response, Response):
            return task_or_response
        task = task_or_response
        if not has_company_access(user, task.execution.graph_version.graph, minimum_role="member"):
            return error_response(
                "FORBIDDEN",
                "You don't have permission to remove judges from this task.",
                status=403,
            )
        TaskJudge.objects.filter(task=task).delete()
        return success_response({"judge": None})


class TaskJudgeEvaluationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, task_id: UUID) -> Response:
        user = cast(User, request.user)
        task_or_response = _task_for_user(user, task_id)
        if isinstance(task_or_response, Response):
            return task_or_response
        task = task_or_response
        if not has_company_access(user, task.execution.graph_version.graph, minimum_role="member"):
            return error_response(
                "FORBIDDEN",
                "You don't have permission to evaluate judges for this task.",
                status=403,
            )
        try:
            judge = task.judge
        except TaskJudge.DoesNotExist:
            return error_response("NOT_FOUND", "Task judge not found", status=404)
        judge = evaluate_task_judge(judge=judge, user=user)
        return success_response({"judge": task_judge_payload(judge)})
