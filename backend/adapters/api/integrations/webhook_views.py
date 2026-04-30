"""Generic webhook integration adapters."""

from __future__ import annotations

import hmac
import logging
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.runs import views as run_views
from adapters.api.runs.serializers import RunDetailWithNodeRunsSerializer
from adapters.gateways.grpc_engine_client import EngineConnectionError, EngineExecutionError
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.audit_log import record_audit_log
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

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_webhook_config(graph_json: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(graph_json.get("metadata"))
    integrations = _as_dict(metadata.get("integrations"))
    return _as_dict(integrations.get("webhook"))


def _thread_id_for_webhook_source(*, graph_version_id: UUID, raw_value: str) -> UUID | None:
    value = raw_value.strip()
    if not value:
        return None
    return uuid5(NAMESPACE_URL, f"webhook:{graph_version_id}:{value}")


def _normalize_webhook_input(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(request.data, dict):
        payload = {str(key): value for key, value in request.data.items()}

    query = {str(key): values for key, values in request.query_params.lists()}
    headers = {str(key).lower(): str(value) for key, value in request.headers.items() if key}

    return {
        "channel": "webhook",
        "message": _as_str(payload.get("message") or payload.get("text")),
        "webhook": {
            "method": request.method,
            "path": request.path,
            "query": query,
            "headers": headers,
            "payload": payload,
        },
        "payload": payload,
    }


def _run_payload(run: Run, graph_version: GraphVersion) -> dict[str, Any]:
    return {
        "id": run.id,
        "owner_id": run.owner_id,
        "thread_id": run.thread_id,
        "graph_id": graph_version.graph_id,
        "graph_name": graph_version.graph.name,
        "graph_version_id": graph_version.id,
        "graph_version": graph_version.version,
        "status": run.status,
        **run_views._queue_payload(run),
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "input_json": run.input_json,
        "output_json": run.output_json,
        "error_message": run.error_message,
        "duration_ms": run.duration_ms,
        "trace_id": run.trace_id,
        "node_runs": [],
    }


class GenericWebhookView(APIView):
    """Receive generic webhook payloads and dispatch graph runs."""

    permission_classes = [AllowAny]

    def post(self, request: Request, graph_version_id: UUID) -> Response:
        payload_raw = request.data
        if payload_raw not in ({}, None) and not isinstance(payload_raw, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="Webhook payload must be a JSON object.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            graph_version = GraphVersion.objects.select_related("graph__owner").get(
                id=graph_version_id
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"GraphVersion with id '{graph_version_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        webhook_config = _extract_webhook_config(graph_version.graph_json)
        expected_secret = _as_str(
            webhook_config.get("secret") or getattr(settings, "GENERIC_WEBHOOK_SECRET", "")
        )
        if not expected_secret:
            return error_response(
                code="CONFIG_ERROR",
                message="Webhook secret is not configured for this graph.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided_secret = _as_str(request.headers.get("X-Forgegraph-Webhook-Secret"))
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return error_response(
                code="FORBIDDEN",
                message="Webhook secret verification failed.",
                status=status.HTTP_403_FORBIDDEN,
            )

        owner = cast(User, graph_version.graph.owner)
        tenant_id = run_views.get_tenant_id_for_user(owner)
        rate_limit_response = run_views._apply_rate_limit(
            scope="run_start",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return rate_limit_response

        entitlement_response = run_views.check_entitlements(owner)
        if entitlement_response is not None:
            return entitlement_response

        quota_response = run_views.check_llm_quota(owner)
        if quota_response is not None:
            return quota_response

        budget_response = run_views.check_llm_budget(owner)
        if budget_response is not None:
            return budget_response

        input_json = _normalize_webhook_input(request)

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

        try:
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                owner,
                traceparent=request.headers.get("traceparent"),
                tracestate=request.headers.get("tracestate"),
            )
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return run_views._run_preparation_error_response(exc)
        trace_metadata = ensure_trace_context(
            traceparent=str(
                prepared_graph.get("metadata", {}).get("trace", {}).get("traceparent", "")
            ).strip()
            or None,
            tracestate=str(
                prepared_graph.get("metadata", {}).get("trace", {}).get("tracestate", "")
            ).strip()
            or None,
        )

        credential_errors = validate_prompt_credentials(prepared_graph, owner)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )

        thread_hint = _as_str(
            request.headers.get("X-Thread-Id")
            or _as_dict(input_json.get("payload")).get("thread_id")
            or _as_dict(input_json.get("payload")).get("session_id")
        )
        thread_id = _thread_id_for_webhook_source(
            graph_version_id=graph_version.id,
            raw_value=thread_hint,
        )
        session_id = str(thread_id) if thread_id else None

        run = Run.objects.create(
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
            trace_id=trace_metadata["trace_id"],
        )
        try:
            prepared_graph = prepare_tool_executions_for_dispatch(
                run=run,
                graph_json=prepared_graph,
            )
            prepared_graph = run_views._attach_operation_context_pack(run, prepared_graph)
        except ToolExecutionDispatchBlocked as exc:
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = str(exc)
            run.save(update_fields=["status", "ended_at", "error_message"])
            return error_response(
                code="TOOL_EXECUTION_DISPATCH_BLOCKED",
                message=str(exc),
                status=status.HTTP_409_CONFLICT,
            )
        broadcast_run_updated(run)
        record_audit_log(
            actor=owner,
            tenant_id=tenant_id,
            action="run.started.generic_webhook",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "graph_id": str(graph_version.graph_id),
                "channel": "webhook",
                "path": request.path,
            },
        )

        upsert_memory_session(owner, session_id)

        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            queue_entry = enqueue_run(run, tenant_id=tenant_id)
            serialized_data = RunDetailWithNodeRunsSerializer(
                {
                    **_run_payload(run, graph_version),
                    "queue_status": queue_entry.status,
                    "queue_attempts": queue_entry.attempts,
                    "queue_available_at": queue_entry.available_at,
                }
            ).data
            return success_response(
                serialized_data,
                status=status.HTTP_202_ACCEPTED,
                meta={"queued": True, "channel": "webhook"},
            )

        callback_url = run_views.resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph,
            owner,
            session_id=session_id,
        )
        try:
            with start_backend_span(
                "integrations.webhook.start",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.channel": "webhook",
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
                        input_json=run.input_json
                        if isinstance(run.input_json, dict)
                        else input_json,
                        memory_config_json=memory_config_json,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        traceparent=trace_metadata["traceparent"],
                        tracestate=trace_metadata["tracestate"],
                    )
                    run.status = "running"
                    update_fields = ["status"]
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
            logger.error("Engine connection failed for webhook run %s: %s", run.id, exc)
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine connection failed: {exc}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except EngineExecutionError as exc:
            logger.error("Engine rejected webhook run %s: %s", run.id, exc)
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine rejected run: {exc}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serialized_data = RunDetailWithNodeRunsSerializer(_run_payload(run, graph_version)).data
        return success_response(
            serialized_data,
            status=status.HTTP_202_ACCEPTED,
            meta={"channel": "webhook"},
        )
