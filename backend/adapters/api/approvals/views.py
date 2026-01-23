"""
Approvals API views for Human Gate tasks.

Clean Architecture: Interface Adapters layer.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import success_response
from infrastructure.orm.models import ApprovalTask


class ApprovalListView(APIView):
    """List pending approval tasks for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get list of pending approvals for the current user."""
        # Filter by assignee (current user) and status
        status_filter = request.query_params.get("status", "pending")

        tasks = ApprovalTask.objects.filter(
            assignee=request.user,
        ).select_related(
            "run__graph_version__graph"
        ).order_by("-created_at")

        # Apply status filter if specified
        if status_filter != "all":
            tasks = tasks.filter(status=status_filter)

        # Build response data with graph/run names
        result = []
        for task in tasks:
            run = task.run
            graph_version = run.graph_version
            graph = graph_version.graph if graph_version else None

            # Extract node name from graph JSON if available
            node_name = task.node_id
            if graph_version and graph_version.graph_json:
                nodes = graph_version.graph_json.get("nodes", [])
                for node in nodes:
                    if node.get("id") == task.node_id:
                        node_name = node.get("name", task.node_id)
                        break

            result.append({
                "id": task.id,
                "run_id": run.id,
                "run_name": f"Run {str(run.id)[:8]}",
                "graph_name": graph.name if graph else "Unknown",
                "node_id": task.node_id,
                "node_name": node_name,
                "status": task.status,
                "prompt_message": task.payload.get("prompt_message", ""),
                "created_at": task.created_at,
            })

        return success_response(result)


class ApprovalDetailView(APIView):
    """Get details of a specific approval task."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, approval_id) -> Response:
        """Get approval task details."""
        from adapters.api.responses import error_response

        try:
            task = ApprovalTask.objects.select_related(
                "run__graph_version__graph"
            ).get(id=approval_id)
        except ApprovalTask.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Approval task not found",
                status_code=404,
            )

        # Check permission - user must be assignee or run owner
        if task.assignee != request.user and task.run.owner != request.user:
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view this approval",
                status_code=403,
            )

        run = task.run
        graph_version = run.graph_version
        graph = graph_version.graph if graph_version else None

        # Extract node name from graph JSON
        node_name = task.node_id
        if graph_version and graph_version.graph_json:
            nodes = graph_version.graph_json.get("nodes", [])
            for node in nodes:
                if node.get("id") == task.node_id:
                    node_name = node.get("name", task.node_id)
                    break

        return success_response({
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
        })


class ApprovalCountView(APIView):
    """Get count of pending approvals for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Get count of pending approvals."""
        count = ApprovalTask.objects.filter(
            assignee=request.user,
            status="pending",
        ).count()

        return success_response({"count": count})
