"""Shared integration webhook run dispatch helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from adapters.api.responses import error_response, success_response
from adapters.api.runs import views as run_views
from adapters.api.runs.serializers import RunDetailWithNodeRunsSerializer
from adapters.gateways.grpc_engine_client import EngineConnectionError, EngineExecutionError
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.metrics import record_run_completed, record_run_started
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    SubgraphResolutionError,
    build_memory_config_json,
    prepare_graph_for_engine,
    upsert_memory_session,
    validate_prompt_credentials,
)
from application.services.run_queue import enqueue_run
from application.services.run_state_machine import apply_run_status_transition
from application.services.schema_validation import (
    SchemaError,
    extract_schema_metadata,
    validate_json_schema,
)
from application.services.telemetry import start_backend_span
from application.services.tool_executions import (
    ToolExecutionDispatchBlocked,
    prepare_tool_executions_for_dispatch,
)
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import GraphVersion, Run, User

RunPayloadBuilder = Callable[[Run, GraphVersion], dict[str, Any]]


@dataclass(frozen=True)
class PreparedIntegrationGraph:
    graph_json: dict[str, Any]
    trace_metadata: dict[str, str]


@dataclass(frozen=True)
class IntegrationRunContext:
    tenant_id: str
    run: Run
    prepared_graph: dict[str, Any]
    trace_metadata: dict[str, str]


def integration_policy_response(owner: User) -> tuple[str, Response | None]:
    tenant_id = run_views.get_tenant_id_for_user(owner)
    rate_limit_response = run_views._apply_rate_limit(
        scope="run_start",
        tenant_id=tenant_id,
        limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
        window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
    )
    if rate_limit_response is not None:
        return tenant_id, rate_limit_response

    for check in (
        run_views.check_entitlements,
        run_views.check_llm_quota,
        run_views.check_llm_budget,
    ):
        gate_response = check(owner)
        if gate_response is not None:
            return tenant_id, gate_response
    return tenant_id, None


def input_schema_response(
    graph_version: GraphVersion, input_json: dict[str, Any]
) -> Response | None:
    input_schema, _, _, _ = extract_schema_metadata(graph_version.graph_json)
    if not input_schema:
        return None

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
    return None


def prepare_integration_graph(
    *,
    graph_version: GraphVersion,
    owner: User,
    request: Request,
) -> PreparedIntegrationGraph | Response:
    try:
        prepared_graph = prepare_graph_for_engine(
            graph_version.graph_json,
            owner,
            company_id=graph_version.graph_id,
            traceparent=request.headers.get("traceparent"),
            tracestate=request.headers.get("tracestate"),
        )
    except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
        return run_views._run_preparation_error_response(exc)

    trace_data = prepared_graph.get("metadata", {}).get("trace", {})
    trace_metadata = ensure_trace_context(
        traceparent=str(trace_data.get("traceparent", "")).strip() or None,
        tracestate=str(trace_data.get("tracestate", "")).strip() or None,
    )
    return PreparedIntegrationGraph(graph_json=prepared_graph, trace_metadata=trace_metadata)


def credential_response(prepared_graph: dict[str, Any], owner: User) -> Response | None:
    credential_errors = validate_prompt_credentials(prepared_graph, owner)
    if not credential_errors:
        return None
    return error_response(
        code="INVALID_CREDENTIALS",
        message="Prompt node credentials are missing or invalid.",
        status=status.HTTP_400_BAD_REQUEST,
        details=credential_errors,
    )


def create_pending_integration_run(
    *,
    owner: User,
    graph_version: GraphVersion,
    thread_id: UUID | None,
    input_json: dict[str, Any],
    prepared_graph: dict[str, Any],
    trace_id: str | None,
) -> Run:
    return Run.objects.create(
        owner=owner,
        graph_version=graph_version,
        thread_id=thread_id,
        status="pending",
        started_at=timezone.now(),
        ended_at=None,
        input_json=input_json,
        dispatch_graph_json=prepared_graph,
        output_json=None,
        error_message="",
        trace_id=trace_id or "",
    )


def prepare_integration_tool_dispatch(
    run: Run, graph_json: dict[str, Any]
) -> dict[str, Any] | Response:
    try:
        prepared_graph = prepare_tool_executions_for_dispatch(run=run, graph_json=graph_json)
        return run_views._attach_operation_context_pack(run, prepared_graph)
    except ToolExecutionDispatchBlocked as exc:
        transition = apply_run_status_transition(run, "failed")
        run.ended_at = timezone.now()
        run.error_message = str(exc)
        run.save(
            update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"]))
        )
        return error_response(
            code="TOOL_EXECUTION_DISPATCH_BLOCKED",
            message=str(exc),
            status=status.HTTP_409_CONFLICT,
        )


def prepare_integration_run_context(
    *,
    graph_version: GraphVersion,
    owner: User,
    request: Request,
    input_json: dict[str, Any],
    thread_id: UUID | None,
) -> IntegrationRunContext | Response:
    tenant_id, policy_response = integration_policy_response(owner)
    if policy_response is not None:
        return policy_response

    schema_response = input_schema_response(graph_version, input_json)
    if schema_response is not None:
        return schema_response

    prepared = prepare_integration_graph(
        graph_version=graph_version,
        owner=owner,
        request=request,
    )
    if not isinstance(prepared, PreparedIntegrationGraph):
        return prepared

    credentials_response = credential_response(prepared.graph_json, owner)
    if credentials_response is not None:
        return credentials_response

    run = create_pending_integration_run(
        owner=owner,
        graph_version=graph_version,
        thread_id=thread_id,
        input_json=input_json,
        prepared_graph=prepared.graph_json,
        trace_id=prepared.trace_metadata["trace_id"],
    )
    prepared_graph = prepare_integration_tool_dispatch(run, prepared.graph_json)
    if isinstance(prepared_graph, Response):
        return prepared_graph

    return IntegrationRunContext(
        tenant_id=tenant_id,
        run=run,
        prepared_graph=prepared_graph,
        trace_metadata=prepared.trace_metadata,
    )


def finalize_integration_run(
    *,
    context: IntegrationRunContext,
    graph_version: GraphVersion,
    owner: User,
    session_id: str | None,
    input_json: dict[str, Any],
    channel: str,
    span_name: str,
    log_label: str,
    logger: logging.Logger,
    run_payload: RunPayloadBuilder,
    record_audit: Callable[[Run, str], Any],
) -> Response:
    broadcast_run_updated(context.run)
    record_audit(context.run, context.tenant_id)
    upsert_memory_session(owner, session_id)

    queue_response = queued_integration_response(
        run=context.run,
        graph_version=graph_version,
        tenant_id=context.tenant_id,
        channel=channel,
        run_payload=run_payload,
    )
    if queue_response is not None:
        return queue_response

    dispatch_response = dispatch_integration_run_to_engine(
        run=context.run,
        graph_version=graph_version,
        owner=owner,
        tenant_id=context.tenant_id,
        session_id=session_id,
        input_json=input_json,
        prepared_graph=context.prepared_graph,
        trace_metadata=context.trace_metadata,
        channel=channel,
        span_name=span_name,
        log_label=log_label,
        logger=logger,
    )
    if dispatch_response is not None:
        return dispatch_response

    serialized_data = RunDetailWithNodeRunsSerializer(run_payload(context.run, graph_version)).data
    return success_response(
        serialized_data,
        status=status.HTTP_202_ACCEPTED,
        meta={"channel": channel},
    )


def queued_integration_response(
    *,
    run: Run,
    graph_version: GraphVersion,
    tenant_id: str,
    channel: str,
    run_payload: RunPayloadBuilder,
) -> Response | None:
    if not getattr(settings, "RUN_QUEUE_ENABLED", False):
        return None

    queue_entry = enqueue_run(run, tenant_id=tenant_id)
    serialized_data = RunDetailWithNodeRunsSerializer(
        {
            **run_payload(run, graph_version),
            "queue_status": queue_entry.status,
            "queue_attempts": queue_entry.attempts,
            "queue_available_at": queue_entry.available_at,
        }
    ).data
    return success_response(
        serialized_data,
        status=status.HTTP_202_ACCEPTED,
        meta={"queued": True, "channel": channel},
    )


def dispatch_integration_run_to_engine(
    *,
    run: Run,
    graph_version: GraphVersion,
    owner: User,
    tenant_id: str,
    session_id: str | None,
    input_json: dict[str, Any],
    prepared_graph: dict[str, Any],
    trace_metadata: dict[str, str],
    channel: str,
    span_name: str,
    log_label: str,
    logger: logging.Logger,
) -> Response | None:
    callback_url = run_views.resolve_engine_callback_url(run_id=str(run.id))
    memory_config_json = build_memory_config_json(
        graph_version.graph,
        owner,
        session_id=session_id,
    )
    try:
        with start_backend_span(
            span_name,
            traceparent=trace_metadata["traceparent"],
            tracestate=trace_metadata["tracestate"],
            attributes={
                "forgegraph.run_id": str(run.id),
                "forgegraph.graph_version_id": str(graph_version.id),
                "forgegraph.channel": channel,
            },
        ):
            selected_engine_id, engine_client = run_views.get_engine_assignment(
                run_id=str(run.id),
                callback_url=callback_url,
            )
            with engine_client as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=prepared_graph,
                    input_json=run.input_json if isinstance(run.input_json, dict) else input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    traceparent=trace_metadata["traceparent"],
                    tracestate=trace_metadata["tracestate"],
                )
                transition = apply_run_status_transition(run, "running")
                update_fields = transition.update_fields
                update_fields.extend(
                    run_views.touch_run_liveness(
                        run,
                        recovery_state=run_views.recovery_state_for_status("running"),
                        engine_instance_id=selected_engine_id,
                    )
                )
                run.save(update_fields=sorted(set(update_fields)))
                record_run_started()
                broadcast_run_updated(run)
    except EngineConnectionError as exc:
        logger.error("Engine connection failed for %s run %s: %s", log_label, run.id, exc)
        _mark_engine_dispatch_failed(run, f"Engine connection failed: {exc}")
        return error_response(
            code="ENGINE_UNAVAILABLE",
            message="The execution engine is not available. Please try again later.",
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except EngineExecutionError as exc:
        logger.error("Engine rejected %s run %s: %s", log_label, run.id, exc)
        _mark_engine_dispatch_failed(run, f"Engine rejected run: {exc}")
        return error_response(
            code="ENGINE_ERROR",
            message=str(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _mark_engine_dispatch_failed(run: Run, message: str) -> None:
    transition = apply_run_status_transition(run, "failed")
    run.ended_at = timezone.now()
    run.error_message = message
    run.save(update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"])))
    record_run_completed("failed", run.duration_ms)
    broadcast_run_updated(run)
