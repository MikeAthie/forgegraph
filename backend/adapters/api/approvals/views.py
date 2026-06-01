"""
Approvals API views for Human Gate tasks.

Clean Architecture: Interface Adapters layer.
"""

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.approvals.serializers import ApprovalResolveSerializer
from adapters.api.responses import error_response, success_response
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from application.services.task_lifecycle import resolve_backend_approval_task
from infrastructure.orm.models import ApprovalTask, User


class ApprovalListView(APIView):
    """List pending approval tasks for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get list of pending approvals for the current user."""
        # Filter by assignee (current user) and status
        status_filter = request.query_params.get("status", "pending")
        user = cast(User, request.user)

        tasks = (
            ApprovalTask.objects.filter(
                run__graph_version__graph__in=accessible_company_queryset(user),
            )
            .select_related("run__graph_version__graph")
            .order_by("-created_at")
        )

        # Apply status filter if specified
        if status_filter != "all":
            tasks = tasks.filter(status=status_filter)

        # Build response data with graph/run names
        result = []
        for task in tasks:
            if not _can_view_approval(user=user, task=task):
                continue
            run = task.run
            graph_version = run.graph_version
            graph = graph_version.graph if graph_version else None

            # Extract node name from graph JSON if available
            node_name = _node_name(task)

            result.append(
                {
                    "id": task.id,
                    "run_id": run.id,
                    "run_name": f"Run {str(run.id)[:8]}",
                    "graph_name": graph.name if graph else "Unknown",
                    "node_id": task.node_id,
                    "node_name": node_name,
                    "status": task.status,
                    "prompt_message": task.payload.get("prompt_message", ""),
                    "payload": sanitize_outbox_payload(
                        task.payload if isinstance(task.payload, dict) else {}
                    ),
                    "result": sanitize_outbox_payload(
                        task.result if isinstance(task.result, dict) else None
                    ),
                    "resolution_mode": _approval_resolution_mode(task),
                    "created_at": task.created_at,
                    "resolved_at": task.resolved_at,
                }
            )

        return success_response(result)


class ApprovalDetailView(APIView):
    """Get details of a specific approval task."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, approval_id: UUID) -> Response:
        """Get approval task details."""
        try:
            task = ApprovalTask.objects.select_related("run__graph_version__graph").get(
                id=approval_id
            )
        except ApprovalTask.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Approval task not found",
                status=404,
            )

        # Check permission - user must be assignee or run owner
        user = cast(User, request.user)
        graph = task.run.graph_version.graph if task.run.graph_version_id else None
        if graph is None or not has_company_access(user, graph, minimum_role="viewer"):
            return error_response(
                code="NOT_FOUND",
                message="Approval task not found",
                status=404,
            )
        if not _can_view_approval(user=user, task=task):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view this approval",
                status=403,
            )

        run = task.run
        graph_version = run.graph_version
        graph = graph_version.graph if graph_version else None

        # Extract node name from graph JSON
        node_name = _node_name(task)

        return success_response(
            {
                "id": task.id,
                "run_id": run.id,
                "run_name": f"Run {str(run.id)[:8]}",
                "graph_name": graph.name if graph else "Unknown",
                "node_id": task.node_id,
                "node_name": node_name,
                "status": task.status,
                "payload": task.payload,
                "result": task.result,
                "created_at": task.created_at,
                "resolved_at": task.resolved_at,
                "resolution_mode": _approval_resolution_mode(task),
            }
        )


class ApprovalResolveView(APIView):
    """Resolve a pending approval task with a durable human decision."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, approval_id: UUID) -> Response:
        if not idempotency_key_from_request(request):
            return error_response(
                code="IDEMPOTENCY_KEY_REQUIRED",
                message="Idempotency-Key is required for approval resolution.",
                status=400,
            )
        user = cast(User, request.user)
        task, load_error = _load_approval_for_resolution(user=user, approval_id=approval_id)
        if load_error is not None:
            return load_error
        assert task is not None
        organization = task.run.organization or task.run.graph_version.graph.organization

        serializer = ApprovalResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="Request payload is invalid.",
                status=400,
                details=[
                    {"field": str(key), "issue": str(value)}
                    for key, value in dict(serializer.errors).items()
                ],
            )
        context = build_idempotency_context(
            request=request,
            organization=organization,
            action=f"approval.resolve:{task.id}",
            request_payload=request.data,
        )
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return error_response(
                code="IDEMPOTENCY_CONFLICT",
                message=str(exc),
                status=409,
                details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
            )
        if replay is not None:
            return replay

        approved = bool(serializer.validated_data.get("approved", True))
        status_value = "approved" if approved else "rejected"
        result = sanitize_outbox_payload(
            {
                **dict(serializer.validated_data.get("result") or {}),
                "approved": approved,
                "notes": str(serializer.validated_data.get("notes") or ""),
            }
        )
        if task.status != "pending":
            if task.status == status_value and task.result == result:
                response = success_response(
                    {"approval": _approval_payload(task), "duplicate": True}
                )
                return record_processed_command(
                    context=context,
                    response=response,
                    resource_type="approval",
                    resource_id=str(task.id),
                )
            return error_response(
                code="DECISION_CONFLICT",
                message="Approval task has already been resolved differently.",
                status=409,
            )

        task = resolve_backend_approval_task(
            approval_task=task,
            status=status_value,
            result=result,
            organization=organization,
        )
        if task.status != status_value or task.result != result:
            return error_response(
                code="DECISION_CONFLICT",
                message="Approval task has already been resolved differently.",
                status=409,
            )
        response = success_response({"approval": _approval_payload(task)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="approval",
            resource_id=str(task.id),
        )


class ApprovalCountView(APIView):
    """Get count of pending approvals for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get count of pending approvals."""
        user = cast(User, request.user)
        count = ApprovalTask.objects.filter(
            assignee=user,
            status="pending",
            run__graph_version__graph__in=accessible_company_queryset(user),
        ).count()

        return success_response({"count": count})


def _approval_payload(task: ApprovalTask) -> dict[str, object]:
    run = task.run
    graph = run.graph_version.graph if run.graph_version_id else None
    payload = sanitize_outbox_payload(task.payload if isinstance(task.payload, dict) else {})
    return {
        "id": str(task.id),
        "run_id": str(run.id),
        "run_name": f"Run {str(run.id)[:8]}",
        "graph_name": graph.name if graph else "Unknown",
        "node_id": task.node_id,
        "node_name": _node_name(task),
        "status": task.status,
        "prompt_message": payload.get("prompt_message", ""),
        "payload": payload,
        "result": sanitize_outbox_payload(task.result if isinstance(task.result, dict) else {}),
        "resolution_mode": _approval_resolution_mode(task),
        "created_at": task.created_at.isoformat(),
        "resolved_at": task.resolved_at.isoformat() if task.resolved_at else None,
    }


def _load_approval_for_resolution(
    *,
    user: User,
    approval_id: UUID,
) -> tuple[ApprovalTask | None, Response | None]:
    try:
        task = ApprovalTask.objects.select_related(
            "run__graph_version__graph",
            "run__organization",
            "assignee",
        ).get(id=approval_id)
    except ApprovalTask.DoesNotExist:
        return None, error_response(code="NOT_FOUND", message="Approval task not found", status=404)

    graph = task.run.graph_version.graph if task.run.graph_version_id else None
    organization = task.run.organization or getattr(graph, "organization", None)
    organization_id = getattr(organization, "id", None)
    if (
        graph is None
        or organization is None
        or not has_company_access(user, graph, minimum_role="member")
    ):
        return None, error_response(code="NOT_FOUND", message="Approval task not found", status=404)
    if not has_min_role(user, "member", str(organization_id) if organization_id else None):
        return None, _approval_forbidden()
    if _approval_resolution_mode(task) != "direct":
        return None, _approval_forbidden()
    if task.assignee_id and task.assignee_id != user.id and task.run.owner_id != user.id:
        return None, _approval_forbidden()
    return task, None


def _approval_resolution_mode(task: ApprovalTask) -> str:
    payload = task.payload if isinstance(task.payload, dict) else {}
    return "direct" if payload.get("whiteboard_id") else "resume_run"


def _can_view_approval(*, user: User, task: ApprovalTask) -> bool:
    graph = task.run.graph_version.graph if task.run.graph_version_id else None
    organization = task.run.organization or getattr(graph, "organization", None)
    organization_id = getattr(organization, "id", None)
    if (
        graph is None
        or organization is None
        or not has_company_access(user, graph, minimum_role="viewer")
    ):
        return False
    if task.assignee_id == user.id or task.run.owner_id == user.id:
        return True
    return (
        _approval_resolution_mode(task) == "direct"
        and task.assignee_id is None
        and has_company_access(user, graph, minimum_role="member")
        and has_min_role(user, "member", str(organization_id) if organization_id else None)
    )


def _node_name(task: ApprovalTask) -> str:
    graph_version = task.run.graph_version
    if graph_version and graph_version.graph_json:
        nodes = graph_version.graph_json.get("nodes", [])
        for node in nodes:
            if node.get("id") == task.node_id:
                return str(node.get("name", task.node_id))
    payload = task.payload if isinstance(task.payload, dict) else {}
    return str(payload.get("phase_id") or payload.get("node_name") or task.node_id)


def _approval_forbidden() -> Response:
    return error_response(
        code="FORBIDDEN",
        message="You don't have permission to resolve this approval",
        status=403,
    )
