"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

import asyncio
import copy
import json as pyjson
import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, When
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from adapters.api.responses import error_response, success_response
from adapters.api.runs.serializers import (
    RunDetailWithNodeRunsSerializer,
    RunEventSerializer,
    RunInvokeSerializer,
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
from application.services.schema_validation import (
    SchemaError,
    extract_schema_metadata,
    validate_json_schema,
)
from infrastructure.orm.models import (
    ApprovalTask,
    GraphVersion,
    MemoryConfiguration,
    MemorySession,
    NodeRun,
    Run,
    RunCheckpoint,
    RunEvent,
)

logger = logging.getLogger(__name__)


def get_engine_client(callback_url: str = "") -> GrpcEngineClient:
    """Get an engine client instance. Can be mocked in tests."""
    return GrpcEngineClient(
        host=settings.ENGINE_HOST,
        port=settings.ENGINE_PORT,
        callback_url=callback_url,
    )


def get_tenant_id(request: Request) -> str:
    """Get tenant ID from the authenticated user."""
    user = request.user
    if hasattr(user, "tenant_id") and user.tenant_id:
        return str(user.tenant_id)
    return str(user.id)


def get_memory_config_for_graph(graph, user):
    if hasattr(graph, "memory_config") and graph.memory_config:
        return graph.memory_config
    default_config = MemoryConfiguration.objects.filter(user=user).first()
    if default_config:
        return default_config
    return None


def build_memory_config_json(graph, user, session_id: str | None = None) -> str:
    config = get_memory_config_for_graph(graph, user)
    if not config:
        return ""

    cross_session_enabled = session_id is not None

    payload = {
        "tier1": {
            "enabled": config.buffer_enabled,
            "buffer_size": config.buffer_size,
            "auto_prepend": config.auto_prepend,
        },
        "tier2": {
            "enabled": config.redis_enabled,
            "namespace": "",
            "summary_ttl_seconds": config.redis_summary_ttl,
            "facts_ttl_seconds": config.redis_facts_ttl,
        },
        "tier3": {
            "enabled": config.vector_enabled,
            "top_k": config.vector_top_k,
            "threshold": config.vector_threshold,
            "recency_weight": config.vector_recency_weight,
            "embedding_model": config.embedding_model,
        },
        "summarization": {
            "enabled": config.summarization_enabled,
            "trigger_threshold": config.summarization_threshold,
            "keep_recent_count": config.summarization_keep_recent,
            "model": config.summarization_model,
        },
        "cross_session": {
            "enabled": cross_session_enabled,
            "session_ttl_hours": 24,
            "share_with_agent": False,
        },
    }
    return pyjson.dumps(payload)


def upsert_memory_session(user, session_id: str | None, ttl_hours: int = 24) -> None:
    if not session_id:
        return
    expires_at = timezone.now() + timedelta(hours=ttl_hours)
    MemorySession.objects.update_or_create(
        session_id=session_id,
        defaults={"owner": user, "expires_at": expires_at},
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


def expand_subgraphs(graph_json: dict, owner) -> dict:
    """Inline subgraph graph_json for subgraph nodes."""
    if not isinstance(graph_json, dict):
        return graph_json

    data = copy.deepcopy(graph_json)
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return data

    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") != "subgraph":
            continue

        config = node.get("config")
        if not isinstance(config, dict):
            config = {}

        if isinstance(config.get("graph_json"), dict):
            config["graph_json"] = expand_subgraphs(config["graph_json"], owner)
            node["config"] = config
            continue

        graph_version_id = config.get("graph_version_id")
        graph_id = config.get("graph_id")
        graph_version = None
        if graph_version_id:
            graph_version = (
                GraphVersion.objects.select_related("graph")
                .filter(id=graph_version_id, graph__owner=owner)
                .first()
            )
        elif graph_id:
            graph_version = (
                GraphVersion.objects.select_related("graph")
                .filter(graph_id=graph_id, graph__owner=owner)
                .order_by("-version")
                .first()
            )

        if graph_version is None:
            raise ValueError("Subgraph reference is invalid or not accessible.")

        subgraph_json = strip_sentinel_edges(graph_version.graph_json)
        config["graph_json"] = expand_subgraphs(subgraph_json, owner)
        config["graph_id"] = str(graph_version.graph_id)
        config["graph_version_id"] = str(graph_version.id)
        config["graph_version"] = graph_version.version
        node["config"] = config

    return data


def apply_memory_namespace_prefix(graph_json: dict, owner_id) -> dict:
    """Ensure memory nodes are isolated per user via namespace_prefix."""
    if not isinstance(graph_json, dict):
        return graph_json

    data = copy.deepcopy(graph_json)
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return data

    prefix = f"user:{owner_id}"

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        config = node.get("config")
        if not isinstance(config, dict):
            config = {}

        if node_type == "memory":
            config["namespace_prefix"] = prefix
            node["config"] = config
        elif node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
            config["graph_json"] = apply_memory_namespace_prefix(config["graph_json"], owner_id)
            node["config"] = config

    return data


def prepare_graph_for_engine(graph_json: dict, owner) -> dict:
    """Prepare graph JSON for engine execution (strip sentinels, expand subgraphs, enforce memory isolation)."""
    cleaned = strip_sentinel_edges(graph_json)
    expanded = expand_subgraphs(cleaned, owner)
    return apply_memory_namespace_prefix(expanded, owner.id)


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
                    "thread_id": run.thread_id,
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
            "thread_id": run.thread_id,
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
        thread_id = serializer.validated_data.get("thread_id")
        session_id = str(thread_id) if thread_id else None

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

        input_schema, _, _, _ = extract_schema_metadata(graph_version.graph_json)
        if input_schema:
            try:
                schema_errors = validate_json_schema(input_json, input_schema)
            except SchemaError as exc:
                return error_response(
                    code="INVALID_SCHEMA",
                    message="Input schema is invalid.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=[{"message": str(exc)}],
                )

            if schema_errors:
                return error_response(
                    code="INVALID_INPUT_SCHEMA",
                    message="Input does not match the required schema.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=schema_errors,
                )

        run = Run.objects.create(
            owner=request.user,
            graph_version=graph_version,
            thread_id=thread_id,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=input_json,
            output_json=None,
            error_message="",
        )
        broadcast_run_updated(run)

        # Prepare graph for engine (inline subgraphs, enforce memory namespace)
        try:
            prepared_graph = prepare_graph_for_engine(graph_version.graph_json, request.user)
        except ValueError as exc:
            return error_response(
                code="INVALID_SUBGRAPH",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Track memory session for cross-run buffers.
        upsert_memory_session(request.user, session_id)

        # Send run to the engine
        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=run.id)
        memory_config_json = build_memory_config_json(
            graph_version.graph, request.user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with get_engine_client(callback_url) as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=prepared_graph,
                    input_json=input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=tenant_id,
                    session_id=session_id,
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
            "thread_id": run.thread_id,
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


class RunInvokeView(APIView):
    """Invoke a threaded run using persisted state."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = RunInvokeSerializer(data=request.data)
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

        thread_id = serializer.validated_data["thread_id"]
        session_id = str(thread_id)
        input_json = serializer.validated_data.get("input_json") or {}

        if input_json and not isinstance(input_json, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="input_json must be a JSON object",
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_run = (
            Run.objects.filter(
                owner=request.user,
                thread_id=thread_id,
                status__in=["pending", "running", "paused"],
            )
            .order_by("-started_at")
            .first()
        )
        if active_run:
            return error_response(
                code="INVALID_STATE",
                message=f"Thread '{thread_id}' has an active run ({active_run.id}).",
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest_run = (
            Run.objects.filter(owner=request.user, thread_id=thread_id)
            .select_related("graph_version__graph")
            .order_by(
                Case(
                    When(started_at__isnull=True, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                "-started_at",
            )
            .first()
        )

        if latest_run is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Thread with id '{thread_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            checkpoint = latest_run.checkpoint
        except RunCheckpoint.DoesNotExist:
            checkpoint = None

        if checkpoint is None:
            return error_response(
                code="NO_CHECKPOINT",
                message="No persisted state found for this thread.",
                status=status.HTTP_409_CONFLICT,
            )

        graph_version = latest_run.graph_version
        try:
            graph_json = prepare_graph_for_engine(graph_version.graph_json, request.user)
        except ValueError as exc:
            return error_response(
                code="INVALID_SUBGRAPH",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        checkpoint_graph_json = pyjson.dumps(graph_json)

        input_schema, _, _, _ = extract_schema_metadata(graph_version.graph_json)
        if input_schema:
            try:
                schema_errors = validate_json_schema(input_json, input_schema)
            except SchemaError as exc:
                return error_response(
                    code="INVALID_SCHEMA",
                    message="Input schema is invalid.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=[{"message": str(exc)}],
                )

            if schema_errors:
                return error_response(
                    code="INVALID_INPUT_SCHEMA",
                    message="Input does not match the required schema.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=schema_errors,
                )

        seed_state = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        seed_state = dict(seed_state)
        for key, value in input_json.items():
            seed_state[f"input.{key}"] = value

        with transaction.atomic():
            run = Run.objects.create(
                owner=request.user,
                graph_version=graph_version,
                thread_id=thread_id,
                status="pending",
                started_at=timezone.now(),
                ended_at=None,
                input_json=input_json,
                output_json=None,
                error_message="",
            )

            RunCheckpoint.objects.create(
                run=run,
                node_id="seed",
                step_index=0,
                state_json=seed_state,
                completed_nodes=[],
                skipped_nodes=[],
                graph_json=checkpoint_graph_json,
            )

        broadcast_run_updated(run)

        upsert_memory_session(request.user, session_id)

        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=run.id)
        memory_config_json = build_memory_config_json(
            graph_version.graph, request.user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with get_engine_client(callback_url) as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=graph_json,
                    input_json=input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=tenant_id,
                    session_id=session_id,
                )
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
            "thread_id": run.thread_id,
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
            "thread_id": run.thread_id,
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

            output_schema = None
            schema_mode = "warn"
            try:
                _, output_schema, _, schema_mode = extract_schema_metadata(
                    run.graph_version.graph_json
                )
            except Exception:
                output_schema = None

            schema_errors: list[dict] | None = None
            if output_schema and payload.get("status") == "succeeded" and "output_json" in payload:
                try:
                    schema_errors = validate_json_schema(payload.get("output_json"), output_schema)
                except SchemaError as exc:
                    logger.warning("Invalid output schema for run %s: %s", run.id, exc)

            if schema_errors:
                try:
                    RunEvent.objects.create(
                        run=run,
                        event_type="run.schema_validation",
                        payload={"errors": schema_errors, "mode": schema_mode},
                    )
                except Exception as exc:  # pragma: no cover - log and continue
                    logger.warning("Failed to persist schema validation event: %s", exc)

                if schema_mode == "strict":
                    run.status = "failed"
                    run.error_message = (
                        f"Output schema validation failed: {schema_errors[0]['message']}"
                    )
                    run.save(update_fields=["status", "error_message"])
                    payload["status"] = run.status
                    payload["error_message"] = run.error_message

            try:
                RunEvent.objects.create(
                    run=run,
                    event_type=event_type,
                    payload=payload,
                )
            except Exception as exc:  # pragma: no cover - log and continue
                logger.warning("Failed to persist run event: %s", exc)

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

                RunEvent.objects.create(
                    run=run,
                    event_type=event_type,
                    payload=payload,
                )

            message = broadcast_node_run_updated(run=run, node_run=node_run)
            return success_response(message)

        if event_type == "run.schema_validation":
            payload = serializer.validated_data.get("payload") or {}
            try:
                RunEvent.objects.create(
                    run=run,
                    event_type=event_type,
                    payload=payload,
                )
            except Exception as exc:  # pragma: no cover - log and continue
                logger.warning("Failed to persist schema validation event: %s", exc)

            return success_response({"received": True})

        return error_response(
            code="VALIDATION_ERROR",
            message="Unknown event_type",
            status=status.HTTP_400_BAD_REQUEST,
        )


def _build_stream_message(*, run: Run, event: RunEvent) -> dict:
    payload = event.payload or {}
    message = {
        "event_id": str(event.id),
        "timestamp": event.created_at.isoformat(),
        "type": event.event_type,
        "run_id": str(run.id),
    }
    if event.event_type == "run.updated":
        message["run"] = payload
    elif event.event_type == "node_run.updated":
        message["node_run"] = payload
    else:
        message["payload"] = payload
    return message


def _format_sse(message: dict, event_name: str | None = None) -> str:
    payload = pyjson.dumps(message, default=str)
    lines = []
    if event_name:
        lines.append(f"event: {event_name}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def _get_user_from_request(request: Request):
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user

    token = request.query_params.get("token")
    if not token:
        return None

    try:
        access_token = AccessToken(token)
    except TokenError:
        return None

    user_id_claim = getattr(settings, "SIMPLE_JWT", {}).get("USER_ID_CLAIM", "user_id")
    user_id = access_token.get(user_id_claim)
    if not user_id:
        return None

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return None


async def _receive_with_timeout(channel_layer, channel_name: str, timeout: float):
    try:
        return await asyncio.wait_for(channel_layer.receive(channel_name), timeout=timeout)
    except TimeoutError:
        return None


class RunEventsStreamView(APIView):
    """Stream run events over Server-Sent Events (SSE)."""

    permission_classes = [AllowAny]

    def get(self, request: Request, run_id) -> StreamingHttpResponse | Response:
        user = _get_user_from_request(request)
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            run = Run.objects.get(id=run_id, owner=user)
        except Run.DoesNotExist:
            return Response({"detail": "Run not found"}, status=status.HTTP_404_NOT_FOUND)

        since_param = request.query_params.get("since")
        since = parse_datetime(since_param) if since_param else None

        def event_stream():
            yield _format_sse(
                {
                    "type": "connected",
                    "run_id": str(run.id),
                    "timestamp": timezone.now().isoformat(),
                },
                event_name="connected",
            )

            if since:
                for event in RunEvent.objects.filter(run=run, created_at__gt=since).order_by(
                    "created_at"
                ):
                    message = _build_stream_message(run=run, event=event)
                    yield _format_sse(message, event_name=event.event_type)

            channel_layer = get_channel_layer()
            if channel_layer is None:
                return

            channel_name = async_to_sync(channel_layer.new_channel)()
            async_to_sync(channel_layer.group_add)(f"run_{run.id}", channel_name)

            try:
                while True:
                    event = async_to_sync(_receive_with_timeout)(channel_layer, channel_name, 15)
                    if event is None:
                        yield ": ping\n\n"
                        continue

                    message = event.get("message")
                    if message is None:
                        continue

                    event_type = message.get("type")
                    yield _format_sse(message, event_name=str(event_type) if event_type else None)
            except GeneratorExit:
                return
            finally:
                async_to_sync(channel_layer.group_discard)(f"run_{run.id}", channel_name)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response
