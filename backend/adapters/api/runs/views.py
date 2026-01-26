"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, When
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.runs.serializers import (
    RunDetailWithNodeRunsSerializer,
    RunEventSerializer,
    RunListSerializer,
    RunResumeSerializer,
    RunStartSerializer,
)
from adapters.gateways.grpc_engine_client import (
    EngineConnectionError,
    EngineExecutionError,
    GrpcEngineClient,
)
from adapters.ws.runs.broadcast import broadcast_node_run_updated, broadcast_run_updated
from infrastructure.orm.models import ApprovalTask, GraphVersion, NodeRun, Run

logger = logging.getLogger(__name__)


def get_engine_client(callback_url: str = "") -> GrpcEngineClient:
    """Get an engine client instance. Can be mocked in tests."""
    return GrpcEngineClient(
        host=settings.ENGINE_HOST,
        port=settings.ENGINE_PORT,
        callback_url=callback_url,
    )


START_NODE_ID = "START"
END_NODE_ID = "END"


def strip_sentinel_edges(graph_json: dict) -> dict:
    """
    Remove LangGraph-style START/END edges before sending a graph to the engine.

    The current engine execution model derives start nodes from indegree==0 and
    end nodes from sinks; START/END sentinel endpoints are editor/export-only.
    """
    edges = graph_json.get("edges")
    if not isinstance(edges, list):
        return graph_json

    filtered_edges = [
        edge
        for edge in edges
        if isinstance(edge, dict)
        and edge.get("from") != START_NODE_ID
        and edge.get("to") != END_NODE_ID
    ]

    if filtered_edges == edges:
        return graph_json

    cleaned = dict(graph_json)
    cleaned["edges"] = filtered_edges
    return cleaned


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's runs."""
        runs = Run.objects.filter(owner=request.user).select_related("graph_version__graph")

        status_filter = request.query_params.get("status")
        if status_filter:
            runs = runs.filter(status=status_filter)

        runs = runs.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "-started_at",
        )

        total_count = runs.count()

        limit_param = request.query_params.get("limit")
        offset_param = request.query_params.get("offset")
        limit: int | None = None
        offset = 0

        if offset_param is not None:
            try:
                offset = max(int(offset_param), 0)
            except (TypeError, ValueError):
                offset = 0

        if limit_param is not None:
            try:
                parsed_limit = int(limit_param)
            except (TypeError, ValueError):
                parsed_limit = 0

            if parsed_limit > 0:
                limit = parsed_limit

        if offset or limit is not None:
            end = None if limit is None else offset + limit
            runs = runs[offset:end]

        result = []
        for run in runs:
            graph_version = run.graph_version
            graph = graph_version.graph
            result.append(
                {
                    "id": run.id,
                    "graph_id": graph.id,
                    "graph_name": graph.name,
                    "graph_version_id": graph_version.id,
                    "graph_version": graph_version.version,
                    "status": run.status,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "duration_ms": run.duration_ms,
                }
            )

        serialized_data = RunListSerializer(result, many=True).data
        return success_response(serialized_data, meta={"total": total_count})


class RunDetailView(APIView):
    """Get run details (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id) -> Response:
        """Get run details with node runs."""
        node_runs_queryset = NodeRun.objects.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "started_at",
            "attempt",
        )

        try:
            run = (
                Run.objects.select_related("graph_version__graph")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id, owner=request.user)
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        graph_version = run.graph_version
        graph = graph_version.graph

        # Get pause_payload from the waiting node run if available
        pause_payload = None
        if run.paused_node_id:
            waiting_node_run = run.node_runs.filter(
                node_id=run.paused_node_id, status="waiting"
            ).first()
            if waiting_node_run and waiting_node_run.output_json:
                pause_payload = waiting_node_run.output_json.get("pause_payload")

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "graph_id": graph.id,
            "graph_name": graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": run.input_json,
            "output_json": run.output_json,
            "error_message": run.error_message,
            "duration_ms": run.duration_ms,
            "paused_node_id": run.paused_node_id,
            "pause_payload": pause_payload,
            "node_runs": [
                {
                    "id": node_run.id,
                    "node_id": node_run.node_id,
                    "node_type": node_run.node_type,
                    "status": node_run.status,
                    "attempt": node_run.attempt,
                    "started_at": node_run.started_at,
                    "ended_at": node_run.ended_at,
                    "duration_ms": node_run.duration_ms,
                    "input_json": node_run.input_json,
                    "output_json": node_run.output_json,
                    "error_json": node_run.error_json,
                }
                for node_run in run.node_runs.all()
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data)


class RunStartView(APIView):
    """Start a run."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Start a new run."""
        serializer = RunStartSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        graph_version_id = serializer.validated_data["graph_version_id"]
        input_json = serializer.validated_data.get("input_json") or {}

        try:
            graph_version = GraphVersion.objects.select_related("graph").get(
                id=graph_version_id, graph__owner=request.user
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"GraphVersion with id '{graph_version_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        run = Run.objects.create(
            owner=request.user,
            graph_version=graph_version,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=input_json,
            output_json=None,
            error_message="",
        )
        broadcast_run_updated(run)

        # Send run to the engine
        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=run.id)
        try:
            with get_engine_client(callback_url) as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=strip_sentinel_edges(graph_version.graph_json),
                    input_json=input_json,
                )
                # Update status to running once engine accepts
                run.status = "running"
                run.save(update_fields=["status"])
                broadcast_run_updated(run)

        except EngineConnectionError as e:
            logger.error(f"Engine connection failed for run {run.id}: {e}")
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine connection failed: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except EngineExecutionError as e:
            logger.error(f"Engine rejected run {run.id}: {e}")
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine rejected run: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": run.input_json,
            "output_json": run.output_json,
            "error_message": run.error_message,
            "duration_ms": run.duration_ms,
            "node_runs": [],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data, status=status.HTTP_201_CREATED)


class RunCancelView(APIView):
    """Cancel a run."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id) -> Response:
        """Cancel a running run."""
        node_runs_queryset = NodeRun.objects.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "started_at",
            "attempt",
        )

        try:
            run = (
                Run.objects.select_related("graph_version__graph")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id, owner=request.user)
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        if run.status in {"succeeded", "failed", "canceled"}:
            return error_response(
                code="INVALID_STATE",
                message=f"Cannot cancel a run in status '{run.status}'.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tell the engine to cancel the run
        try:
            with get_engine_client() as engine:
                engine.cancel_run(run_id=run.id)

        except EngineConnectionError as e:
            logger.warning(f"Engine connection failed when canceling run {run.id}: {e}")
            # Still proceed to mark as canceled in the control plane

        except EngineExecutionError as e:
            logger.warning(f"Engine failed to cancel run {run.id}: {e}")
            # Still proceed to mark as canceled in the control plane

        if not run.started_at:
            run.started_at = timezone.now()

        run.status = "canceled"
        run.ended_at = timezone.now()
        if not run.error_message:
            run.error_message = "Canceled by user."

        run.save(update_fields=["status", "started_at", "ended_at", "error_message"])
        broadcast_run_updated(run)

        graph_version = run.graph_version
        graph = graph_version.graph

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "graph_id": graph.id,
            "graph_name": graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": run.input_json,
            "output_json": run.output_json,
            "error_message": run.error_message,
            "duration_ms": run.duration_ms,
            "node_runs": [
                {
                    "id": node_run.id,
                    "node_id": node_run.node_id,
                    "node_type": node_run.node_type,
                    "status": node_run.status,
                    "attempt": node_run.attempt,
                    "started_at": node_run.started_at,
                    "ended_at": node_run.ended_at,
                    "duration_ms": node_run.duration_ms,
                    "input_json": node_run.input_json,
                    "output_json": node_run.output_json,
                    "error_json": node_run.error_json,
                }
                for node_run in run.node_runs.all()
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data)


class RunResumeView(APIView):
    """Resume a paused run (human gate approval/rejection)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id) -> Response:
        """Resume a paused run with human decision."""
        serializer = RunResumeSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        # Get the run
        try:
            run = Run.objects.select_related("graph_version__graph").get(
                id=run_id, owner=request.user
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify run is paused
        if run.status != "paused":
            return error_response(
                code="INVALID_STATE",
                message=f"Cannot resume a run in status '{run.status}'. Run must be paused.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        node_id = serializer.validated_data["node_id"]
        input_json = serializer.validated_data.get("input_json", {})

        # Verify node_id matches paused node
        if run.paused_node_id and run.paused_node_id != node_id:
            return error_response(
                code="INVALID_NODE",
                message=f"Node '{node_id}' does not match paused node '{run.paused_node_id}'",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call engine ResumeRun
        try:
            with get_engine_client() as engine:
                engine.resume_run(run_id=run.id, node_id=node_id, input_json=input_json)
        except EngineConnectionError as e:
            logger.error(f"Engine connection failed when resuming run {run.id}: {e}")
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except EngineExecutionError as e:
            logger.error(f"Engine failed to resume run {run.id}: {e}")
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update ApprovalTask
        approval_task = run.approval_tasks.filter(node_id=node_id, status="pending").first()
        if approval_task:
            approved = input_json.get("approved", True)
            approval_task.status = "approved" if approved else "rejected"
            approval_task.result = input_json
            approval_task.resolved_at = timezone.now()
            approval_task.save(update_fields=["status", "result", "resolved_at"])

        return success_response({"resumed": True, "run_id": str(run.id)})


class RunEventsView(APIView):
    """Persist + broadcast Run/NodeRun delta events."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id) -> Response:
        serializer = RunEventSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        try:
            run = Run.objects.get(id=run_id, owner=request.user)
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        event_type = serializer.validated_data["event_type"]

        if event_type == "run.updated":
            payload = serializer.validated_data["run"]
            update_fields: list[str] = []

            for field in ["status", "started_at", "ended_at", "output_json", "error_message"]:
                if field not in payload:
                    continue
                setattr(run, field, payload[field])
                update_fields.append(field)

            # Handle pause_state fields for human gate
            if "paused_node_id" in payload:
                run.paused_node_id = payload["paused_node_id"]
                update_fields.append("paused_node_id")
            if "pause_state_json" in payload:
                run.pause_state_json = payload["pause_state_json"]
                update_fields.append("pause_state_json")

            if update_fields:
                run.save(update_fields=update_fields)

            # Create ApprovalTask when run is paused (human gate)
            if payload.get("status") == "paused":
                pause_output = payload.get("pause_payload", {})
                node_id = run.paused_node_id or pause_output.get("node_id", "")

                if node_id:
                    # Extract pause payload from the event or find the waiting node
                    prompt_message = pause_output.get("prompt_message", "")
                    required_fields = pause_output.get("required_fields", [])

                    # Create ApprovalTask (idempotent)
                    ApprovalTask.objects.get_or_create(
                        run=run,
                        node_id=node_id,
                        status="pending",
                        defaults={
                            "assignee": run.owner,
                            "payload": {
                                "prompt_message": prompt_message,
                                "required_fields": required_fields,
                            },
                        },
                    )

            message = broadcast_run_updated(run)
            return success_response(message)

        if event_type == "node_run.updated":
            payload = serializer.validated_data["node_run"]
            node_id = payload["node_id"]
            node_type = payload["node_type"]
            attempt = payload["attempt"]

            with transaction.atomic():
                node_run, created = NodeRun.objects.get_or_create(
                    run=run,
                    node_id=node_id,
                    attempt=attempt,
                    defaults={
                        "node_type": node_type,
                        "status": payload["status"],
                    },
                )

                update_fields: list[str] = []

                if not created and node_run.node_type != node_type:
                    node_run.node_type = node_type
                    update_fields.append("node_type")

                node_run.status = payload["status"]
                update_fields.append("status")

                if "started_at" in payload:
                    node_run.started_at = payload["started_at"]
                    update_fields.append("started_at")
                if "ended_at" in payload:
                    node_run.ended_at = payload["ended_at"]
                    update_fields.append("ended_at")
                if "input_json" in payload:
                    node_run.input_json = payload["input_json"]
                    update_fields.append("input_json")
                if "output_json" in payload:
                    node_run.output_json = payload["output_json"]
                    update_fields.append("output_json")
                if "error_json" in payload:
                    node_run.error_json = payload["error_json"]
                    update_fields.append("error_json")

                node_run.save(update_fields=sorted(set(update_fields)))

            message = broadcast_node_run_updated(run=run, node_run=node_run)
            return success_response(message)

        return error_response(
            code="VALIDATION_ERROR",
            message="Unknown event_type",
            status=status.HTTP_400_BAD_REQUEST,
        )
