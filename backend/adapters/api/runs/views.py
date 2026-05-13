"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

import asyncio
import hashlib
import json as pyjson
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, OperationalError, models, transaction
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Sum, When
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.problem_details import problem_response
from adapters.api.responses import error_response, success_response
from adapters.api.runs.memory_activity import (
    derive_node_memory_activity,
    summarize_run_memory_activity,
)
from adapters.api.runs.serializers import (
    EngineExecutionEventSerializer,
    RunDetailWithNodeRunsSerializer,
    RunEventSerializer,
    RunInvokeSerializer,
    RunListSerializer,
    RunReplaySerializer,
    RunResumeSerializer,
    RunStartSerializer,
)
from adapters.gateways.grpc_engine_client import (
    EngineConnectionError,
    EngineExecutionError,
    GrpcEngineClient,
)
from adapters.ws.runs.broadcast import (
    broadcast_cost_update,
    broadcast_decision_required,
    broadcast_decision_resolved,
    broadcast_node_run_updated,
    broadcast_node_stream_chunk,
    broadcast_node_stream_summary,
    broadcast_run_schema_validation,
    broadcast_run_updated,
)
from application.services.audit_log import record_audit_log
from application.services.auth_state import (
    consume_ws_ticket,
    is_access_jti_revoked,
    validate_access_token,
)
from application.services.canonical_events import (
    CanonicalEventValidationError,
    parse_engine_event_payload,
)
from application.services.company_archive import ArchiveService, ContextPackService
from application.services.company_learning import PreferenceEventService
from application.services.engine_selection import (
    EngineAssignmentError,
    get_engine_target_by_id,
    reconcile_run_engine_instance,
    select_engine_target,
)
from application.services.engine_selection import (
    resolve_engine_callback_url as resolve_engine_callback_url,
)
from application.services.event_categories import (
    EventSafetyViolation,
    assert_runtime_state_mutation_allowed,
    normalize_event_category,
)
from application.services.event_dead_letters import record_event_dead_letter
from application.services.idempotency import (
    IdempotencyStatus,
    annotate_response,
    annotated_response_from_body,
    hash_request_payload,
    normalize_idempotency_key,
    record_idempotency_observation,
    response_body,
)
from application.services.llm_access import (
    LLM_MODE_MANAGED,
    LLMAccessConfig,
    LLMAccessValidationError,
    attach_llm_access_to_graph,
    engine_input_with_llm_access,
    engine_llm_access_from_graph,
    public_llm_access_from_graph,
    resolve_llm_access_for_dispatch,
)
from application.services.llm_pricing import calculate_cost
from application.services.managed_llm_limits import check_managed_llm_limits
from application.services.memory_intents import BackendMemoryIntentService
from application.services.metrics import (
    record_callback_auth_failure,
    record_run_completed,
    record_run_started,
    record_stale_attempt_ignored,
)
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    record_processed_command,
    replay_processed_command,
)
from application.services.rate_limit import check_rate_limit, rate_limit_response_payload
from application.services.rbac import has_min_role
from application.services.redaction import redact_payload
from application.services.run_event_streaming import (
    add_event_level,
    event_levels_for_subscription,
    flush_all_stream_summaries,
    flush_stream_summary,
    message_allowed_for_level,
    normalize_requested_event_level,
    run_event_group_name,
    update_stream_summary,
)
from application.services.run_liveness import engine_instance_label
from application.services.run_liveness import (
    recovery_state_for_status as recovery_state_for_status,
)
from application.services.run_liveness import touch_run_liveness as touch_run_liveness
from application.services.run_locking import acquire_run_transaction_lock
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    SubgraphResolutionError,
    build_memory_config_json,
    prepare_graph_for_engine,
    upsert_memory_session,
    validate_prompt_credentials,
)
from application.services.run_queue import enqueue_run, log_run_queue_worker_unavailable
from application.services.run_snapshots import (
    RunSnapshot,
    get_snapshot,
    safe_delete_snapshot,
    safe_set_snapshot,
    set_snapshot,
)
from application.services.run_state_machine import (
    RunTransitionConflict,
    apply_run_status_transition,
    assert_run_transition_allowed,
)
from application.services.schema_validation import (
    SchemaError,
    extract_schema_metadata,
    validate_json_schema,
)
from application.services.structured_logging import log_event
from application.services.task_lifecycle import (
    initialize_lifecycle_tasks_for_run,
    mark_run_tasks_terminal,
    record_retry_operation,
    transition_from_node_run,
    transition_task_lifecycle,
)
from application.services.telemetry import start_backend_span
from application.services.tenancy import get_tenant_id_for_user as resolve_tenant_id_for_user
from application.services.tool_executions import (
    ToolExecutionDispatchBlocked,
    prepare_tool_executions_for_dispatch,
)
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import (
    ApprovalTask,
    DecisionRecord,
    GraphVersion,
    LLMBudget,
    LLMQuota,
    LLMUsage,
    NodeRun,
    NodeRunEventProjection,
    Organization,
    ProcessedAccountingEvent,
    ProcessedCallbackEvent,
    ProcessedDecisionSubmission,
    Run,
    RunCheckpoint,
    RunEvent,
    RunEventProjection,
    TenantSubscription,
    User,
)
from infrastructure.security import s2s

logger = logging.getLogger(__name__)
_UNSET = object()
_DEADLOCK_RETRY_ATTEMPTS = 3


@dataclass
class EngineCallbackContext:
    run: Run
    event: dict[str, Any]
    event_type: str
    event_id: Any
    event_time: datetime | None
    trace_context: dict[str, str]
    normalized_category: str
    state_mutation_enabled: bool
    callback_engine_instance_id: str
    callback_organization_id: UUID | None
    callback_idempotency_key: str
    callback_request_hash: str


@dataclass
class RunLifecycleMutation:
    run_payload: dict[str, Any]
    update_fields: list[str]
    pause_payload: dict[str, Any]
    node_id: str
    projection_kwargs: dict[str, Any]
    error_response: Response | None = None


@dataclass
class RunEngineDispatch:
    run: Run
    graph_version: GraphVersion
    outbound_graph: dict[str, Any]
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    session_id: str | None
    tenant_id: str
    trace_metadata: dict[str, str]
    span_name: str
    trigger: str
    engine_rejected_event: str = "engine_rejected_run"
    failure_task_source: str | None = None


@dataclass
class RunStartRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    graph_version_id: UUID
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    thread_id: Any
    session_id: str | None


@dataclass
class RunInvokeRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    thread_id: Any
    session_id: str
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    latest_run: Run
    checkpoint: RunCheckpoint


@dataclass
class RunReplayRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    run: Run
    node_id: str
    llm_access: LLMAccessConfig
    checkpoint: RunCheckpoint
    input_json: dict[str, Any]
    session_id: str | None


@dataclass
class ReplayCheckpointSeed:
    state_json: dict[str, Any]
    completed_nodes: list[Any]
    skipped_nodes: list[Any]


@dataclass
class RunResumeRequestContext:
    user: User
    run: Run
    organization: Organization | None
    command_context: Any
    node_id: str
    input_json: dict[str, Any]
    submit_id: str
    decision_request_hash: str
    decision_submission: ProcessedDecisionSubmission | None
    resume_attempt_id: UUID


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()


def _lock_run_for_update(run_id: UUID) -> Run:
    acquire_run_transaction_lock(run_id)
    return Run.objects.select_for_update().select_related("owner").get(id=run_id)


def _engine_event_attempt_id(event_type: str, event: dict[str, Any]) -> str:
    attempt_id = str(event.get("attempt_id") or "").strip()
    if attempt_id:
        return attempt_id
    if event_type == "run_resumed":
        output = event.get("output")
        if isinstance(output, dict):
            return str(output.get("resume_attempt_id") or "").strip()
    return ""


def _engine_callback_payload(
    *,
    decision: str,
    reason: str,
    backend_event_id: str = "",
    safe_to_discard: bool = False,
    retry_after_ms: int | None = None,
    conflict_code: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "backend_event_id": backend_event_id,
        "safe_to_discard": safe_to_discard,
    }
    if retry_after_ms is not None:
        payload["retry_after_ms"] = retry_after_ms
    if conflict_code:
        payload["conflict_code"] = conflict_code
    payload.update(extra)
    return payload


def _engine_callback_success(
    data: dict[str, Any] | None = None,
    *,
    decision: str = "accepted",
    reason: str = "accepted",
    backend_event_id: str = "",
    safe_to_discard: bool = True,
    conflict_code: str = "",
) -> Response:
    payload = _engine_callback_payload(
        decision=decision,
        reason=reason,
        backend_event_id=backend_event_id,
        safe_to_discard=safe_to_discard,
        conflict_code=conflict_code,
    )
    if data:
        payload.update(data)
    return success_response(payload)


def _engine_callback_problem(
    *,
    type_uri: str,
    title: str,
    status_code: int,
    detail: str,
    decision: str,
    reason: str,
    backend_event_id: str = "",
    safe_to_discard: bool = False,
    conflict_code: str = "",
    extensions: dict[str, Any] | None = None,
) -> Response:
    payload = _engine_callback_payload(
        decision=decision,
        reason=reason,
        backend_event_id=backend_event_id,
        safe_to_discard=safe_to_discard,
        conflict_code=conflict_code,
        type=type_uri,
        title=title,
        status=status_code,
        detail=detail,
    )
    if extensions:
        payload.update(extensions)
    return Response(payload, status=status_code)


def _record_engine_callback_dead_letter(
    *,
    event: dict[str, Any] | None,
    run: Run | None = None,
    reason: str,
    error_class: str = "",
    event_type: str = "",
    event_id: str = "",
    idempotency_key: str = "",
) -> None:
    payload = event if isinstance(event, dict) else {}
    try:
        organization = run.organization if run is not None and run.organization_id else None
        if organization is None:
            organization = _organization_from_event_payload(payload)
        record_event_dead_letter(
            source="engine_callback",
            reason=reason,
            payload=payload,
            organization=organization,
            run=run,
            event_id=event_id or str(payload.get("event_id") or ""),
            idempotency_key=idempotency_key or str(payload.get("idempotency_key") or ""),
            event_type=event_type or str(payload.get("type") or payload.get("event_type") or ""),
            error_class=error_class,
        )
    except Exception:
        logger.exception(
            "engine_callback_dead_letter_record_failed",
            extra={
                "run_id": str(run.id) if run is not None else "",
                "event_id": event_id or str(payload.get("event_id") or ""),
                "event_type": event_type or str(payload.get("type") or ""),
                "reason": reason,
            },
        )


def _organization_from_event_payload(event: dict[str, Any]) -> Organization | None:
    raw_org_id = str(event.get("tenant_id") or event.get("organization_id") or "").strip()
    if not raw_org_id:
        return None
    try:
        org_id = UUID(raw_org_id)
    except ValueError:
        return None
    return Organization.objects.filter(id=org_id).first()


def _ignore_stale_engine_attempt(
    *,
    run: Run,
    event_type: str,
    event: dict[str, Any],
    event_id: str,
    trace_id: str,
    normalized_category: str,
) -> Response | None:
    if normalized_category != "state":
        return None

    current_attempt_id = run.authoritative_attempt_id
    event_attempt_id = _engine_event_attempt_id(event_type, event)
    if not current_attempt_id or not event_attempt_id or event_attempt_id == current_attempt_id:
        return None

    record_stale_attempt_ignored("engine_callback")
    log_event(
        logger,
        logging.WARNING,
        "stale_attempt_ignored",
        run_id=str(run.id),
        trace_id=trace_id,
        event_id=event_id,
        attempt_id=event_attempt_id,
        active_attempt_id=current_attempt_id,
        current_attempt_id=current_attempt_id,
        message="Ignored stale engine callback for superseded attempt",
        category=normalized_category,
    )
    if event_type == "run_resumed":
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/stale-resume-acknowledgement",
            title="Stale resume acknowledgement",
            status_code=status.HTTP_409_CONFLICT,
            detail="run_resumed acknowledgement does not match the active resume_attempt_id.",
            decision="stale_superseded",
            reason="resume_attempt_id does not match the active backend resume attempt",
            backend_event_id=event_id,
            safe_to_discard=True,
            conflict_code="409_STALE_SUPERSEDED",
        )
    return _engine_callback_success(
        {
            "received": True,
            "stale": True,
            "authoritative_state_updated": False,
        },
        decision="stale_superseded",
        reason="event attempt does not match the active backend attempt",
        backend_event_id=event_id,
        safe_to_discard=True,
        conflict_code="409_STALE_SUPERSEDED",
    )


def get_engine_client(
    callback_url: str = "",
    *,
    host: str | None = None,
    port: int | None = None,
) -> GrpcEngineClient:
    """Get an engine client instance. Can be mocked in tests."""
    return GrpcEngineClient(
        host=host or settings.ENGINE_HOST,
        port=port or settings.ENGINE_PORT,
        callback_url=callback_url,
        tls_enabled=settings.ENGINE_GRPC_TLS_ENABLED,
        tls_ca_file=settings.ENGINE_GRPC_TLS_CA_FILE,
        tls_server_name=settings.ENGINE_GRPC_TLS_SERVER_NAME,
    )


def get_engine_assignment(*, run_id: str, callback_url: str = "") -> tuple[str, GrpcEngineClient]:
    target = select_engine_target(run_id=run_id)
    return (
        target.engine_id,
        get_engine_client(callback_url, host=target.host, port=target.port),
    )


def get_engine_client_for_run(*, run: Run, callback_url: str = "") -> tuple[str, GrpcEngineClient]:
    target = (
        get_engine_target_by_id(run.engine_instance_id)
        if str(run.engine_instance_id or "").strip()
        else None
    )
    if target is None:
        target = select_engine_target(run_id=str(run.id))
    return (
        target.engine_id,
        get_engine_client(callback_url, host=target.host, port=target.port),
    )


def get_tenant_id(request: Request) -> str:
    """Get tenant ID from the authenticated user."""
    user = cast(User, request.user)
    return get_tenant_id_for_user(user)


def get_tenant_id_for_user(user: User) -> str:
    return resolve_tenant_id_for_user(user)


def get_tenant_id_for_run(run: Run) -> str:
    if run.organization_id:
        return str(run.organization_id)
    return get_tenant_id_for_user(run.owner)


def _request_trace_headers(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("traceparent"), request.headers.get("tracestate")


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        code="IDEMPOTENCY_CONFLICT",
        message=str(exc),
        status=status.HTTP_409_CONFLICT,
        details=[
            {
                "action": exc.action,
                "idempotency_key": exc.idempotency_key,
            }
        ],
    )


def _replayed_command_response(command_context: Any) -> Response | None:
    try:
        return replay_processed_command(command_context)
    except IdempotencyConflict as exc:
        return _idempotency_conflict_response(exc)


def _deterministic_submit_id(*, run_id: UUID, node_id: str, input_json: Any) -> str:
    digest = hash_request_payload(
        {
            "run_id": str(run_id),
            "node_id": node_id,
            "input_json": input_json if isinstance(input_json, dict) else {},
        }
    )
    return f"decision:{run_id}:{node_id}:{digest}"


def _resume_submit_id(*, request: Request, run_id: UUID, node_id: str, input_json: Any) -> str:
    explicit = normalize_idempotency_key(
        request.data.get("submit_id") if isinstance(request.data, dict) else "",
    )
    if explicit:
        return explicit
    header = normalize_idempotency_key(request.headers.get("Idempotency-Key"))
    if header:
        return header
    return _deterministic_submit_id(run_id=run_id, node_id=node_id, input_json=input_json)


def _processed_decision_replay_response(
    submission: ProcessedDecisionSubmission,
    *,
    submit_id: str,
) -> Response | None:
    if not submission.response_body:
        return None
    record_idempotency_observation(
        boundary="human_decision",
        status="already_applied",
        idempotency_key=submit_id,
        resource_type="run",
        organization_id=submission.organization_id,
        run_id=submission.run_id,
    )
    return annotated_response_from_body(
        submission.response_body,
        response_status=submission.response_status,
        status="already_applied",
        idempotency_key=submit_id,
        resource_type="run",
        resource_id=str(submission.run_id),
    )


def _memory_intent_payload_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("output")
    if not isinstance(payload, dict):
        payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {
            key: event[key]
            for key in (
                "fact",
                "facts",
                "content",
                "value",
                "key",
                "title",
                "source_span",
                "confidence",
                "summary_id",
                "ttl_seconds",
                "cost_usd",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
                "model",
                "provider",
            )
            if key in event
        }
    payload = dict(payload)
    for key in ("tenant_id", "organization_id", "org_id", "run_id", "agent_id", "idempotency_key"):
        if key in event and key not in payload:
            payload[key] = str(event[key]) if event[key] is not None else None
    return payload


def _log_payload_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = [str(key) for key in value.keys()]
        return {
            "type": "object",
            "key_count": len(keys),
            "keys": keys[:12],
            "truncated": len(keys) > 12,
        }
    if isinstance(value, list):
        return {"type": "array", "length": len(value)}
    if isinstance(value, str):
        return {"type": "string", "length": len(value)}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def _trace_metadata_from_graph(graph_json: dict[str, Any]) -> dict[str, str]:
    metadata = graph_json.get("metadata")
    if not isinstance(metadata, dict):
        return ensure_trace_context()
    trace = metadata.get("trace")
    if not isinstance(trace, dict):
        return ensure_trace_context()
    return ensure_trace_context(
        traceparent=str(trace.get("traceparent") or "").strip() or None,
        tracestate=str(trace.get("tracestate") or "").strip() or None,
        trace_id=str(trace.get("trace_id") or "").strip() or None,
    )


def run_queryset_for_user(user: User) -> models.QuerySet[Run]:
    tenant_id = get_tenant_id_for_user(user)
    if not has_min_role(user, "viewer", tenant_id):
        return Run.objects.none()
    tenant_uuid = UUID(tenant_id)
    return Run.objects.filter(
        Q(organization_id=tenant_uuid)
        | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid)
    )


def _queue_payload(run: Run) -> dict[str, Any]:
    entry = getattr(run, "queue_entry", None)
    if not entry:
        return {
            "queue_status": None,
            "queue_attempts": None,
            "queue_available_at": None,
        }
    return {
        "queue_status": entry.status,
        "queue_attempts": entry.attempts,
        "queue_available_at": entry.available_at,
    }


def _queue_response_meta(*, run: Run, tenant_id: str) -> dict[str, Any]:
    health = log_run_queue_worker_unavailable(run_id=run.id, tenant_id=tenant_id)
    return {
        "queued": True,
        "queue_worker_active": health.active,
        "queue_worker_id": health.worker_id or None,
        "queue_worker_last_seen_at": (
            health.last_seen_at.isoformat() if health.last_seen_at else None
        ),
        "queue_worker_age_seconds": health.age_seconds,
        "queue_warning": None if health.active else "run_queue_worker_unavailable",
    }


def _run_start_slow_log_threshold_ms() -> float:
    return float(getattr(settings, "RUN_START_SLOW_LOG_MS", 250))


def _log_run_start_timing(
    *,
    run: Run,
    tenant_id: str,
    queued: bool,
    started_at: float,
    marks: list[tuple[str, float]],
) -> None:
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if elapsed_ms < _run_start_slow_log_threshold_ms():
        return
    previous = started_at
    phases: list[dict[str, Any]] = []
    for stage, mark in marks:
        phases.append(
            {
                "stage": stage,
                "elapsed_ms": round((mark - started_at) * 1000, 2),
                "delta_ms": round((mark - previous) * 1000, 2),
            }
        )
        previous = mark
    log_event(
        logger,
        logging.INFO,
        "run_start_timing",
        run_id=str(run.id),
        tenant_id=tenant_id,
        duration_ms=round(elapsed_ms, 2),
        status=run.status,
        payload={
            "queued": queued,
            "phase_count": len(phases),
            "phases": phases,
        },
        message="Slow run start timing",
    )


def _public_llm_access_payload(run: Run) -> dict[str, Any]:
    return public_llm_access_from_graph(
        run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {}
    )


def _engine_input_for_llm_access(
    input_json: dict[str, Any],
    llm_access: LLMAccessConfig,
) -> dict[str, Any]:
    return engine_input_with_llm_access(input_json, llm_access)


def _attach_operation_context_pack(
    run: Run,
    outbound_graph: dict[str, Any],
    *,
    context_pack_mode: str = "fresh_at_dispatch",
) -> dict[str, Any]:
    _, outbound_with_context = ContextPackService().attach_context_pack_to_run(
        run=run,
        outbound_graph=outbound_graph,
        context_pack_mode=context_pack_mode,
    )
    run.save(update_fields=["dispatch_graph_json"])
    return outbound_with_context or outbound_graph


def _schedule_deliverable_archive(run_id: UUID, node_run_id: UUID | None = None) -> None:
    def archive_deliverables() -> None:
        try:
            run = Run.objects.select_related(
                "organization",
                "graph_version__graph__organization",
            ).get(id=run_id)
            node_run = None
            if node_run_id is not None:
                node_run = NodeRun.objects.filter(id=node_run_id, run=run).first()
            ArchiveService().archive_deliverable_as_asset(run=run, node_run=node_run)
        except Exception:
            logger.exception(
                "deliverable_archive_failed",
                extra={"run_id": str(run_id), "node_run_id": str(node_run_id or "")},
            )

    transaction.on_commit(archive_deliverables)


def _llm_access_error_response(exc: LLMAccessValidationError) -> Response:
    return error_response(
        code="INVALID_LLM_ACCESS",
        message="LLM access configuration is invalid.",
        status=status.HTTP_400_BAD_REQUEST,
        details=exc.details,
    )


def _managed_llm_limit_response(
    *,
    user: User,
    graph_json: dict[str, Any],
    llm_access: LLMAccessConfig,
) -> Response | None:
    if llm_access.llm_mode != LLM_MODE_MANAGED:
        return None
    result = check_managed_llm_limits(graph_json=graph_json, user=user)
    if result.allowed:
        return None
    response = error_response(
        code="MANAGED_LIMIT_EXCEEDED",
        message="Managed LLM limit exceeded.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=result.details,
    )
    if result.rate_limit is not None:
        response["Retry-After"] = str(result.rate_limit.retry_after_seconds)
        response["X-RateLimit-Limit"] = str(result.rate_limit.limit)
        response["X-RateLimit-Remaining"] = str(result.rate_limit.remaining)
        response["X-RateLimit-Reset"] = result.rate_limit.reset_at.isoformat()
    return response


def _run_preparation_error_response(exc: Exception) -> Response:
    if isinstance(exc, PromptTemplateResolutionError):
        return error_response(
            code="INVALID_PROMPT_CONFIG",
            message=str(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, SubgraphResolutionError):
        return error_response(
            code="INVALID_SUBGRAPH",
            message=str(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return error_response(
        code="INVALID_SUBGRAPH",
        message=str(exc),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _tool_execution_dispatch_error_response(exc: Exception) -> Response:
    return error_response(
        code="TOOL_EXECUTION_DISPATCH_BLOCKED",
        message=str(exc),
        status=status.HTTP_409_CONFLICT,
    )


def check_llm_budget(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    budget = LLMBudget.objects.filter(tenant_id=tenant_id).first()
    if not budget:
        return None

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_cost = LLMUsage.objects.filter(
        tenant_id=tenant_id, created_at__gte=month_start
    ).aggregate(total=Sum("cost_usd")).get("total") or Decimal("0")

    if total_cost >= budget.monthly_limit_usd:
        return error_response(
            code="BUDGET_EXCEEDED",
            message="Monthly LLM budget exceeded. Increase your limit or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "budget",
                    "scope": "tenant_monthly_spend",
                    "current_cost_usd": float(total_cost),
                    "limit_cost_usd": float(budget.monthly_limit_usd),
                }
            ],
        )

    return None


def check_llm_quota(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    quota = LLMQuota.objects.filter(tenant_id=tenant_id).first()
    if not quota:
        return None

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = LLMUsage.objects.filter(tenant_id=tenant_id, created_at__gte=month_start).aggregate(
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("cost_usd"),
    )
    total_tokens = int(totals.get("total_tokens") or 0)
    total_cost = totals.get("total_cost") or Decimal("0")

    if quota.monthly_token_limit and total_tokens >= quota.monthly_token_limit:
        return error_response(
            code="QUOTA_EXCEEDED",
            message="Monthly LLM token quota exceeded. Increase your quota or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "quota",
                    "scope": "tenant_monthly_tokens",
                    "current_total_tokens": total_tokens,
                    "limit_total_tokens": quota.monthly_token_limit,
                }
            ],
        )

    if quota.monthly_cost_limit_usd and total_cost >= quota.monthly_cost_limit_usd:
        return error_response(
            code="QUOTA_EXCEEDED",
            message="Monthly LLM cost quota exceeded. Increase your quota or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "quota",
                    "scope": "tenant_monthly_cost",
                    "current_cost_usd": float(total_cost),
                    "limit_cost_usd": float(quota.monthly_cost_limit_usd),
                }
            ],
        )

    return None


def check_entitlements(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    tenant_uuid = UUID(tenant_id)
    subscription = (
        TenantSubscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()
    )

    if not subscription or not subscription.plan:
        return None

    if subscription.status not in {"active", "trialing"}:
        return error_response(
            code="SUBSCRIPTION_INACTIVE",
            message="Your subscription is not active. Update billing to continue.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "plan_entitlement",
                    "scope": "subscription_status",
                    "subscription_status": subscription.status,
                    "plan_name": subscription.plan.name if subscription.plan else None,
                }
            ],
        )

    entitlements = subscription.plan.entitlements or {}
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    max_tokens = entitlements.get("max_monthly_tokens")
    if max_tokens is not None:
        total_tokens = (
            LLMUsage.objects.filter(tenant_id=tenant_id, created_at__gte=month_start)
            .aggregate(total=Sum("total_tokens"))
            .get("total")
            or 0
        )
        if int(total_tokens) >= int(max_tokens):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly token entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_tokens",
                        "current_total_tokens": int(total_tokens),
                        "limit_total_tokens": int(max_tokens),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    max_cost = entitlements.get("max_monthly_cost_usd")
    if max_cost is not None:
        total_cost = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=month_start
        ).aggregate(total=Sum("cost_usd")).get("total") or Decimal("0")
        if total_cost >= Decimal(str(max_cost)):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly cost entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_cost",
                        "current_cost_usd": float(total_cost),
                        "limit_cost_usd": float(Decimal(str(max_cost))),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    max_runs = entitlements.get("max_runs_per_month")
    if max_runs is not None:
        run_count = Run.objects.filter(
            Q(organization_id=tenant_uuid)
            | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid),
            started_at__gte=month_start,
        ).count()
        if run_count >= int(max_runs):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly run entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_runs",
                        "current_run_count": run_count,
                        "limit_run_count": int(max_runs),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    return None


def _apply_rate_limit(
    *, scope: str, tenant_id: str, limit: int, window_seconds: int
) -> Response | None:
    if limit <= 0:
        return None
    result = check_rate_limit(
        scope=scope,
        tenant_id=tenant_id,
        limit=limit,
        window_seconds=window_seconds,
    )
    if result.allowed:
        return None
    response = error_response(
        code="RATE_LIMITED",
        message="Rate limit exceeded. Try again shortly.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=[rate_limit_response_payload(result)],
    )
    response["Retry-After"] = str(result.retry_after_seconds)
    response["X-RateLimit-Limit"] = str(result.limit)
    response["X-RateLimit-Remaining"] = str(result.remaining)
    response["X-RateLimit-Reset"] = result.reset_at.isoformat()
    return response


def _parse_agent_stream_chunk(chunk: Any) -> dict[str, Any] | None:
    if not isinstance(chunk, str):
        return None
    stripped = chunk.strip()
    if not stripped:
        return None

    try:
        parsed = pyjson.loads(stripped)
    except (TypeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    event_name = parsed.get("event")
    if not isinstance(event_name, str) or not event_name.startswith("agent."):
        return None

    return parsed


def _normalize_agent_stream_event(
    *,
    node_id: str,
    node_type: str,
    attempt: int,
    chunk_index: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "event": str(payload.get("event") or ""),
        "node_id": node_id,
        "node_type": node_type,
        "attempt": attempt,
        "chunk_index": chunk_index,
    }
    for key in ("step_index", "action", "tool", "stop_reason", "status"):
        value = payload.get(key)
        if value is not None:
            normalized[key] = value
    return cast(dict[str, Any], redact_payload(normalized))


def _derive_agent_trace(
    *,
    node_run: NodeRun,
    agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if node_run.node_type != "agent":
        return None

    output_json = redact_payload(node_run.output_json) if node_run.output_json else None
    agent_output = None
    if isinstance(output_json, dict):
        candidate = output_json.get("output")
        if isinstance(candidate, dict):
            agent_output = candidate
        elif isinstance(output_json.get("pause_payload"), dict):
            pause_payload = cast(dict[str, Any], output_json["pause_payload"])
            pause_trace = pause_payload.get("agent_trace")
            if isinstance(pause_trace, dict):
                agent_output = pause_trace

    stream_events = agent_events_by_node.get((str(node_run.node_id), int(node_run.attempt)), [])
    if not agent_output and not stream_events:
        return None

    trace: dict[str, Any] = {
        "events": stream_events,
    }
    if isinstance(agent_output, dict):
        for key in (
            "final_output",
            "stop_reason",
            "step_count",
            "tool_call_count",
            "steps",
            "usage",
            "approval_pending",
            "allowed_tools",
        ):
            value = agent_output.get(key)
            if value is not None:
                trace[key] = value
    return trace


def _merge_nested_payload(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_nested_payload(existing, value)
        else:
            merged[key] = value
    return merged


def _insert_dotted_payload_value(root: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = [part for part in dotted_key.split(".") if part]
    if not parts:
        return

    current = root
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing

    leaf_key = parts[-1]
    existing_leaf = current.get(leaf_key)
    if isinstance(existing_leaf, dict) and isinstance(value, dict):
        current[leaf_key] = _merge_nested_payload(existing_leaf, value)
    else:
        current[leaf_key] = value


def _expand_dotted_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [_expand_dotted_payload(item) for item in value]
    if not isinstance(value, dict):
        return value

    expanded: dict[str, Any] = {}
    for key, item in value.items():
        nested_item = _expand_dotted_payload(item)
        if not isinstance(key, str) or "." not in key:
            existing = expanded.get(key)
            if isinstance(existing, dict) and isinstance(nested_item, dict):
                expanded[key] = _merge_nested_payload(existing, nested_item)
            else:
                expanded[key] = nested_item
            continue
        _insert_dotted_payload_value(expanded, key, nested_item)
    return expanded


def _serialize_node_run_for_detail(
    *,
    node_run: NodeRun,
    agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": node_run.id,
        "node_id": node_run.node_id,
        "node_type": node_run.node_type,
        "status": node_run.status,
        "attempt": node_run.attempt,
        "started_at": node_run.started_at,
        "ended_at": node_run.ended_at,
        "duration_ms": node_run.duration_ms,
        "input_json": _expand_dotted_payload(redact_payload(node_run.input_json)),
        "output_json": redact_payload(node_run.output_json),
        "error_json": redact_payload(node_run.error_json),
        "trace_id": node_run.trace_id,
        "span_id": node_run.span_id,
        "memory_activity": derive_node_memory_activity(
            node_type=str(node_run.node_type),
            output_json=node_run.output_json,
        ),
    }
    if agent_events_by_node is not None:
        payload["agent_trace"] = _derive_agent_trace(
            node_run=node_run,
            agent_events_by_node=agent_events_by_node,
        )
    return payload


def _timeline_status_from_payload(event_type: str, payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("status"), str):
        return str(payload["status"])
    nested_status = _nested_timeline_status(payload)
    if nested_status is not None:
        return nested_status
    suffix_statuses = {
        "_failed": "failed",
        "_completed": "succeeded",
        "_started": "running",
    }
    for suffix, status_value in suffix_statuses.items():
        if event_type.endswith(suffix):
            return status_value
    return {
        "run_paused": "paused",
        "run.resume_requested": "resume_requested",
        "run_resumed": "running",
        "node_retrying": "retrying",
    }.get(event_type)


def _nested_timeline_status(payload: dict[str, Any]) -> str | None:
    for key in ("run", "node_run"):
        nested = payload.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("status"), str):
            return str(nested["status"])
    return None


def _timeline_node_id_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("node_id",):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for key in ("node_run", "payload", "output"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            value = nested.get("node_id")
            if isinstance(value, str) and value:
                return value
    return None


def _timeline_message_for_event(event_type: str, payload: dict[str, Any]) -> str:
    node_id = _timeline_node_id_from_payload(payload)
    if event_type == "run_failed":
        return str(payload.get("error") or payload.get("error_message") or "Run failed.")
    run_messages = {
        "run_started": "Run started.",
        "run_completed": "Run completed successfully.",
        "run_paused": "Run paused for a decision boundary.",
        "run.resume_requested": "Resume requested and waiting for engine acknowledgment.",
        "run_resumed": "Run resumed after a decision.",
        "run_canceled": "Run canceled.",
        "run.schema_validation": "Run output schema validation reported issues.",
    }
    if event_type in run_messages:
        return run_messages[event_type]
    if node_id:
        node_messages = {
            "node_started": f"{node_id} started.",
            "node_completed": f"{node_id} completed.",
            "node_failed": f"{node_id} failed.",
            "node_retrying": f"{node_id} is retrying.",
            "node_skipped": f"{node_id} was skipped.",
        }
        if event_type in node_messages:
            return node_messages[event_type]
    return event_type.replace(".", " ").replace("_", " ")


def _run_status_from_event(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type == "run.updated":
        status_value = payload.get("status")
        if isinstance(status_value, str):
            return status_value
        run_payload = payload.get("run")
        if isinstance(run_payload, dict):
            status_value = run_payload.get("status")
            if isinstance(status_value, str):
                return status_value

    if event_type.startswith("run_") or event_type == "run.resume_requested":
        status_value = _timeline_status_from_payload(event_type, payload)
        if isinstance(status_value, str) and status_value in {
            "pending",
            "running",
            "paused",
            "resume_requested",
            "succeeded",
            "failed",
            "canceled",
        }:
            return status_value

    return None


_STATUS_HISTORY_EVENT_ORDER = {
    "run_started": 10,
    "run_paused": 20,
    "run.resume_requested": 30,
    "run_resumed": 40,
    "run_completed": 90,
    "run_failed": 90,
    "run_canceled": 90,
}
_STATUS_HISTORY_STATUS_ORDER = {
    "pending": 0,
    "running": 10,
    "paused": 20,
    "resume_requested": 30,
    "succeeded": 90,
    "failed": 90,
    "canceled": 90,
}


def _build_run_status_history(*, run: Run) -> list[str]:
    history: list[str] = []

    def append_status(status_value: str | None) -> None:
        if not status_value:
            return
        if history and history[-1] == status_value:
            return
        history.append(status_value)

    append_status("pending")

    event_rows = list(
        RunEvent.objects.filter(run=run).order_by("created_at", "id").only("event_type", "payload")
    )
    events: list[tuple[RunEvent, dict[str, Any], str | None]] = []
    for event_row in event_rows:
        payload = redact_payload(event_row.payload or {})
        payload_dict = payload if isinstance(payload, dict) else {}
        events.append(
            (event_row, payload_dict, _run_status_from_event(event_row.event_type, payload_dict))
        )

    for _, _, status_value in sorted(
        events,
        key=lambda item: (
            item[0].created_at,
            _STATUS_HISTORY_EVENT_ORDER.get(
                item[0].event_type,
                _STATUS_HISTORY_STATUS_ORDER.get(item[2] or "", 50),
            ),
            str(item[0].id),
        ),
    ):
        append_status(status_value)

    append_status(str(run.status or "").strip() or None)
    return history


def _validate_run_event_transition(*, current_status: str, event_type: str) -> None:
    normalized = str(current_status or "").strip().lower()
    requested_status = _run_status_from_event(event_type, {})
    if requested_status is None:
        return
    try:
        assert_run_transition_allowed(normalized, requested_status)
    except RunTransitionConflict as exc:
        raise ValueError(f"invalid run event transition: {exc}") from exc


def _build_run_timeline(*, run: Run) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    ignored_event_types = {"run.updated", "node_run.updated", "node_stream.chunk"}

    event_rows = (
        RunEvent.objects.filter(run=run)
        .order_by("created_at", "id")
        .only("id", "event_type", "payload", "created_at", "trace_id")
    )
    for event_row in event_rows:
        if event_row.event_type in ignored_event_types or event_row.event_type.startswith("agent."):
            continue

        payload = redact_payload(event_row.payload or {})
        status_value = _timeline_status_from_payload(event_row.event_type, payload)
        node_id = _timeline_node_id_from_payload(payload)
        error_message = (
            payload.get("error") or payload.get("error_message") or payload.get("message")
            if event_row.event_type in {"run_failed", "node_failed", "run.schema_validation"}
            else None
        )
        duration_ms = payload.get("duration_ms")
        timeline.append(
            {
                "id": f"event:{event_row.id}",
                "timestamp": event_row.created_at.isoformat(),
                "kind": "error"
                if event_row.event_type in {"run_failed", "node_failed", "run.schema_validation"}
                else "event",
                "event_type": event_row.event_type,
                "trace_id": event_row.trace_id or run.trace_id,
                "run_id": str(run.id),
                "node_id": node_id,
                "status": status_value,
                "duration_ms": duration_ms if isinstance(duration_ms, int) else None,
                "cost_usd": None,
                "decision_id": None,
                "message": _timeline_message_for_event(event_row.event_type, payload),
                "error_message": str(error_message) if error_message else None,
                "details": payload,
            }
        )

    approval_rows = ApprovalTask.objects.filter(run=run).order_by("created_at", "id")
    for approval in approval_rows:
        payload = redact_payload(approval.payload if isinstance(approval.payload, dict) else {})
        timeline.append(
            {
                "id": f"decision:{approval.id}:required",
                "timestamp": approval.created_at.isoformat(),
                "kind": "decision",
                "event_type": "decision_required",
                "trace_id": run.trace_id,
                "run_id": str(run.id),
                "node_id": approval.node_id,
                "status": "waiting",
                "duration_ms": None,
                "cost_usd": None,
                "decision_id": str(approval.id),
                "message": str(payload.get("prompt_message") or "Human decision required."),
                "error_message": None,
                "details": payload,
            }
        )
        if approval.status != "pending" and approval.resolved_at:
            resolution = redact_payload(
                approval.result if isinstance(approval.result, dict) else {}
            )
            timeline.append(
                {
                    "id": f"decision:{approval.id}:resolved",
                    "timestamp": approval.resolved_at.isoformat(),
                    "kind": "decision",
                    "event_type": "decision_resolved",
                    "trace_id": run.trace_id,
                    "run_id": str(run.id),
                    "node_id": approval.node_id,
                    "status": approval.status,
                    "duration_ms": None,
                    "cost_usd": None,
                    "decision_id": str(approval.id),
                    "message": f"Decision {approval.status}.",
                    "error_message": None,
                    "details": resolution,
                }
            )

    usage_rows = (
        LLMUsage.objects.filter(run=run)
        .order_by("created_at", "id")
        .only(
            "id",
            "node_id",
            "provider",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
            "created_at",
        )
    )
    for usage in usage_rows:
        timeline.append(
            {
                "id": f"cost:{usage.id}",
                "timestamp": usage.created_at.isoformat(),
                "kind": "cost",
                "event_type": "cost_updated",
                "trace_id": run.trace_id,
                "run_id": str(run.id),
                "node_id": usage.node_id,
                "status": None,
                "duration_ms": None,
                "cost_usd": float(usage.cost_usd),
                "decision_id": None,
                "message": f"{usage.provider} {usage.model} usage recorded.",
                "error_message": None,
                "details": {
                    "provider": usage.provider,
                    "model": usage.model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            }
        )

    timeline.sort(key=lambda entry: (entry.get("timestamp") or "", str(entry.get("id") or "")))
    return timeline


def _extract_llm_usage_payload(*, node_type: str, output_json: Any) -> dict[str, Any] | None:
    if not isinstance(output_json, dict):
        return None

    candidate = output_json
    nested_output = output_json.get("output")
    if node_type == "agent" and isinstance(nested_output, dict):
        candidate = nested_output

    usage = candidate.get("usage")
    if not isinstance(usage, dict):
        return None

    return {
        "provider": str(candidate.get("provider") or "openai"),
        "model": str(candidate.get("model") or ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _payload_contains_policy_denied(value: Any) -> bool:
    if isinstance(value, str):
        return "policy denied:" in value.lower()
    if isinstance(value, dict):
        return any(_payload_contains_policy_denied(item) for item in value.values())
    if isinstance(value, list):
        return any(_payload_contains_policy_denied(item) for item in value)
    return False


def _get_downstream_nodes(graph_json: dict[str, Any], start_node_id: str) -> set[str]:
    nodes_raw = graph_json.get("nodes")
    if not isinstance(nodes_raw, list):
        return set()

    node_ids: set[str] = {
        str(node.get("id"))
        for node in nodes_raw
        if isinstance(node, dict) and node.get("id") is not None
    }
    if start_node_id not in node_ids:
        return set()

    adjacency = _adjacency_for_nodes(node_ids, graph_json.get("edges"))
    visited: set[str] = set()
    stack = [start_node_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, []):
            if neighbor not in visited:
                stack.append(neighbor)

    return visited


def _adjacency_for_nodes(node_ids: set[str], edges_raw: Any) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    if not isinstance(edges_raw, list):
        return adjacency
    for edge in edges_raw:
        if not isinstance(edge, dict):
            continue
        from_id = str(edge.get("from") or "")
        to_id = str(edge.get("to") or "")
        if from_id in adjacency and to_id:
            adjacency[from_id].append(to_id)
    return adjacency


def _prune_state_for_nodes(state_json: dict[str, Any], node_ids: set[str]) -> dict[str, Any]:
    if not node_ids:
        return state_json

    prefixes = tuple(f"node.{node_id}" for node_id in node_ids)
    pruned: dict[str, Any] = {}
    for key, value in state_json.items():
        if isinstance(key, str) and key.startswith(prefixes):
            continue
        pruned[key] = value
    return pruned


def _set_if_changed(instance: Any, field_name: str, value: Any, update_fields: list[str]) -> None:
    if value is _UNSET or getattr(instance, field_name) == value:
        return
    setattr(instance, field_name, value)
    update_fields.append(field_name)


def _run_audit_metadata(
    *,
    graph_version: GraphVersion,
    thread_id: UUID | None,
    trigger: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "graph_id": str(graph_version.graph_id),
        "graph_name": graph_version.graph.name,
        "graph_version_id": str(graph_version.id),
        "graph_version": graph_version.version,
        "trigger": trigger,
    }
    if thread_id is not None:
        metadata["thread_id"] = str(thread_id)
    if extra:
        metadata.update(extra)
    return metadata


def _tenant_active_run_count(tenant_uuid: UUID) -> int:
    return Run.objects.filter(
        Q(organization_id=tenant_uuid)
        | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid),
        status__in=["pending", "running", "paused", "resume_requested"],
    ).count()


def _active_run_guardrail_response(*, tenant_uuid: UUID) -> Response | None:
    max_active = int(getattr(settings, "RUN_MAX_ACTIVE_PER_TENANT", 0))
    if max_active <= 0:
        return None
    active_runs = _tenant_active_run_count(tenant_uuid)
    if active_runs < max_active:
        return None
    return error_response(
        code="RATE_LIMITED",
        message="Too many active runs for this tenant. Wait for current runs to finish.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=[
            {
                "field": "active_runs",
                "issue": f"limit={max_active}, current={active_runs}",
            }
        ],
    )


def _input_size_guardrail_response(input_json: dict[str, Any]) -> Response | None:
    max_bytes = int(getattr(settings, "RUN_INPUT_MAX_BYTES", 0))
    if max_bytes <= 0:
        return None
    serialized = pyjson.dumps(input_json, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = len(serialized.encode("utf-8"))
    if payload_bytes <= max_bytes:
        return None
    return error_response(
        code="VALIDATION_ERROR",
        message="input_json is too large for a single run.",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {
                "field": "input_json",
                "issue": f"max_bytes={max_bytes}, actual_bytes={payload_bytes}",
            }
        ],
    )


def _input_schema_validation_response(
    graph_json: dict[str, Any],
    input_json: dict[str, Any],
) -> Response | None:
    input_schema, _, _, _ = extract_schema_metadata(graph_json)
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
    if not schema_errors:
        return None
    return error_response(
        code="INVALID_INPUT_SCHEMA",
        message="Input does not match the required schema.",
        status=status.HTTP_400_BAD_REQUEST,
        details=schema_errors,
    )


def _project_pause_state(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    pause_payload: dict[str, Any],
    trace_id: str,
    span_id: str,
    event_time: datetime | None,
) -> None:
    if not node_id:
        return

    normalized_node_type = node_type or "human_gate"
    node_defaults: dict[str, Any] = {
        "node_type": normalized_node_type,
        "status": "waiting",
    }
    if event_time:
        node_defaults["started_at"] = event_time
    if pause_payload:
        node_defaults["output_json"] = {"pause_payload": pause_payload}

    with transaction.atomic():
        node_run, created = NodeRun.objects.get_or_create(
            run=run,
            node_id=node_id,
            attempt=attempt,
            defaults=node_defaults,
        )
        node_update_fields: list[str] = []
        if not created:
            _set_if_changed(node_run, "node_type", normalized_node_type, node_update_fields)
        _set_if_changed(node_run, "status", "waiting", node_update_fields)
        if event_time:
            _set_if_changed(node_run, "started_at", event_time, node_update_fields)
        if pause_payload:
            output_json = (
                dict(node_run.output_json) if isinstance(node_run.output_json, dict) else {}
            )
            output_json["pause_payload"] = pause_payload
            _set_if_changed(node_run, "output_json", output_json, node_update_fields)
        _set_if_changed(node_run, "trace_id", trace_id, node_update_fields)
        _set_if_changed(node_run, "span_id", span_id, node_update_fields)
        if node_update_fields:
            node_run.save(update_fields=sorted(set(node_update_fields)))
        lifecycle_result = transition_from_node_run(
            run=run,
            node_run=node_run,
            source="engine_callback",
            idempotency_key=f"task:{run.id}:{node_id}:pause:{attempt}:{event_time.isoformat() if event_time else 'unknown'}",
            reason="human decision gate paused execution",
            occurred_at=event_time,
        )

        approval_payload = {
            "prompt_message": str(pause_payload.get("prompt_message") or ""),
            "required_fields": list(pause_payload.get("required_fields") or []),
        }
        approval_task, created = ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": approval_payload,
                "task_lifecycle": lifecycle_result.lifecycle_task,
            },
        )
        update_fields: list[str] = []
        if not created:
            _set_if_changed(approval_task, "payload", approval_payload, update_fields)
        _set_if_changed(
            approval_task,
            "task_lifecycle",
            lifecycle_result.lifecycle_task,
            update_fields,
        )
        if update_fields:
            approval_task.save(update_fields=sorted(set(update_fields)))


def _project_run_event_state(
    *,
    run: Run,
    projection_status: str,
    trace_id: str,
    event_type: str,
    event_id: str | None,
    event_time: datetime | None,
    started_at: datetime | object = _UNSET,
    ended_at: datetime | object = _UNSET,
    output_json: Any = _UNSET,
    error_message: str | object = _UNSET,
    pause_state_json: Any = _UNSET,
    paused_node_id: str | None | object = _UNSET,
) -> None:
    projection, _ = RunEventProjection.objects.get_or_create(
        run=run,
        defaults={
            "status": projection_status,
            "trace_id": trace_id,
            "last_event_type": event_type,
            "last_event_id": event_id or "",
            "last_event_at": event_time or timezone.now(),
        },
    )

    update_fields: list[str] = []
    _set_if_changed(projection, "status", projection_status, update_fields)
    _set_if_changed(projection, "started_at", started_at, update_fields)
    _set_if_changed(projection, "ended_at", ended_at, update_fields)
    _set_if_changed(projection, "output_json", output_json, update_fields)
    if error_message is not _UNSET:
        _set_if_changed(projection, "error_message", cast(str, error_message), update_fields)
    _set_if_changed(projection, "pause_state_json", pause_state_json, update_fields)
    _set_if_changed(projection, "paused_node_id", paused_node_id, update_fields)
    _set_if_changed(projection, "trace_id", trace_id, update_fields)
    _set_if_changed(projection, "last_event_type", event_type, update_fields)
    next_event_id = event_id or ""
    _set_if_changed(projection, "last_event_id", next_event_id, update_fields)
    effective_event_time = event_time or timezone.now()
    _set_if_changed(projection, "last_event_at", effective_event_time, update_fields)
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


def _project_node_event_state(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    projection_status: str,
    trace_id: str,
    span_id: str,
    event_type: str,
    event_id: str | None,
    event_time: datetime | None,
    started_at: datetime | object = _UNSET,
    ended_at: datetime | object = _UNSET,
    output_json: Any = _UNSET,
    error_json: Any = _UNSET,
) -> None:
    if not node_id:
        return

    projection, _ = NodeRunEventProjection.objects.get_or_create(
        run=run,
        node_id=node_id,
        attempt=attempt,
        defaults={
            "node_type": node_type,
            "status": projection_status,
            "trace_id": trace_id,
            "span_id": span_id,
            "last_event_type": event_type,
            "last_event_id": event_id or "",
            "last_event_at": event_time or timezone.now(),
        },
    )

    update_fields: list[str] = []
    _set_if_changed(projection, "node_type", node_type, update_fields)
    _set_if_changed(projection, "status", projection_status, update_fields)
    _set_if_changed(projection, "started_at", started_at, update_fields)
    _set_if_changed(projection, "ended_at", ended_at, update_fields)
    _set_if_changed(projection, "output_json", output_json, update_fields)
    _set_if_changed(projection, "error_json", error_json, update_fields)
    _set_if_changed(projection, "trace_id", trace_id, update_fields)
    _set_if_changed(projection, "span_id", span_id, update_fields)
    _set_if_changed(projection, "last_event_type", event_type, update_fields)
    next_event_id = event_id or ""
    _set_if_changed(projection, "last_event_id", next_event_id, update_fields)
    effective_event_time = event_time or timezone.now()
    _set_if_changed(projection, "last_event_at", effective_event_time, update_fields)
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Create and start a run using the same contract as /api/runs/start."""
        return RunStartView().post(request)

    def _base_runs_queryset(self, user: User) -> Any:
        return (
            run_queryset_for_user(user)
            .select_related("graph_version__graph", "queue_entry")
            .annotate(
                failed_node_count=Count(
                    "node_runs", filter=Q(node_runs__status="failed"), distinct=True
                )
            )
        )

    def _apply_run_uuid_filter(
        self,
        *,
        runs: Any,
        raw_value: str,
        filter_name: str,
        field_name: str,
    ) -> tuple[Any, Response | None]:
        if not raw_value:
            return runs, None
        try:
            parsed_uuid = UUID(raw_value)
        except ValueError:
            return runs, error_response(
                code="VALIDATION_ERROR",
                message=f"{filter_name} must be a valid UUID",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return runs.filter(**{field_name: parsed_uuid}), None

    def _apply_run_datetime_filter(
        self,
        *,
        runs: Any,
        raw_value: str | None,
        filter_name: str,
        field_name: str,
    ) -> tuple[Any, Response | None]:
        if not raw_value:
            return runs, None
        parsed = parse_datetime(raw_value)
        if parsed is None:
            return runs, error_response(
                code="VALIDATION_ERROR",
                message=f"{filter_name} must be an ISO datetime.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return runs.filter(**{field_name: parsed}), None

    def _apply_run_list_filters(
        self, *, request: Request, runs: Any
    ) -> tuple[Any, Response | None]:
        status_filter = request.query_params.get("status")
        if status_filter:
            runs = runs.filter(status=status_filter)

        runs, error = self._apply_run_uuid_filter(
            runs=runs,
            raw_value=(request.query_params.get("graph_version_id") or "").strip(),
            filter_name="graph_version_id",
            field_name="graph_version_id",
        )
        if error is not None:
            return runs, error
        runs, error = self._apply_run_uuid_filter(
            runs=runs,
            raw_value=(request.query_params.get("graph_id") or "").strip(),
            filter_name="graph_id",
            field_name="graph_version__graph_id",
        )
        if error is not None:
            return runs, error
        runs, error = self._apply_run_datetime_filter(
            runs=runs,
            raw_value=request.query_params.get("started_after"),
            filter_name="started_after",
            field_name="started_at__gte",
        )
        if error is not None:
            return runs, error
        return self._apply_run_datetime_filter(
            runs=runs,
            raw_value=request.query_params.get("started_before"),
            filter_name="started_before",
            field_name="started_at__lte",
        )

    def _apply_failed_nodes_filter(self, *, request: Request, runs: Any) -> Any:
        has_failed_nodes_raw = (request.query_params.get("has_failed_nodes") or "").strip().lower()
        if has_failed_nodes_raw in {"1", "true", "yes"}:
            return runs.filter(failed_node_count__gt=0)
        if has_failed_nodes_raw in {"0", "false", "no"}:
            return runs.filter(failed_node_count=0)
        return runs

    def _apply_run_list_pagination(self, *, request: Request, runs: Any) -> Any:
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
            return runs[offset:end]
        return runs

    def _serialize_run_list(self, runs: Any) -> list[dict[str, Any]]:
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
                    "has_failed_nodes": bool(getattr(run, "failed_node_count", 0)),
                    **_queue_payload(run),
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "duration_ms": run.duration_ms,
                    "trace_id": run.trace_id,
                    "last_progress_at": run.last_progress_at,
                    "last_heartbeat_at": run.last_heartbeat_at,
                    "engine_instance_id": run.engine_instance_id,
                    "recovery_state": run.recovery_state,
                    "recovery_reason": run.recovery_reason,
                    "recovery_policy": run.recovery_policy,
                    "resume_requested_at": run.resume_requested_at,
                    "resume_attempt_id": run.resume_attempt_id,
                    "memory_activity": summarize_run_memory_activity(
                        list(run.node_runs.all()),
                        include_operations=False,
                    ),
                    "llm_access": _public_llm_access_payload(run),
                }
            )
        return result

    def get(self, request: Request) -> Response:
        """List user's runs."""
        user = cast(User, request.user)
        runs, filter_response = self._apply_run_list_filters(
            request=request,
            runs=self._base_runs_queryset(user),
        )
        if filter_response is not None:
            return filter_response
        runs = self._apply_failed_nodes_filter(request=request, runs=runs)

        runs = runs.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "-started_at",
        )

        total_count = runs.count()
        runs = self._apply_run_list_pagination(request=request, runs=runs)

        runs = runs.prefetch_related(
            Prefetch(
                "node_runs",
                queryset=NodeRun.objects.only(
                    "id",
                    "run_id",
                    "node_id",
                    "node_type",
                    "status",
                    "attempt",
                    "started_at",
                    "ended_at",
                    "output_json",
                ).order_by("started_at", "attempt"),
            )
        )

        serialized_data = RunListSerializer(self._serialize_run_list(runs), many=True).data
        return success_response(serialized_data, meta={"total": total_count})


class RunDetailView(APIView):
    """Get run details (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id: UUID) -> Response:
        """Get run details with node runs."""
        user = cast(User, request.user)
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
                run_queryset_for_user(user)
                .select_related("graph_version__graph", "queue_entry")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id)
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
        node_runs = list(run.node_runs.all())
        agent_event_rows = list(
            RunEvent.objects.filter(run=run, event_type__startswith="agent.")
            .order_by("created_at", "id")
            .only("id", "event_type", "payload", "created_at")
        )
        agent_events: list[dict[str, Any]] = []
        agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for event_row in agent_event_rows:
            payload = redact_payload(event_row.payload or {})
            event_payload = {
                "id": str(event_row.id),
                "type": event_row.event_type,
                "created_at": event_row.created_at.isoformat(),
                **payload,
            }
            agent_events.append(event_payload)
            node_id = str(payload.get("node_id") or "")
            attempt = int(payload.get("attempt") or 1)
            if node_id:
                agent_events_by_node[(node_id, attempt)].append(event_payload)
        node_outcomes = {
            "pending": 0,
            "running": 0,
            "waiting": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        }
        for node_run in node_runs:
            status_key = str(node_run.status)
            if status_key in node_outcomes:
                node_outcomes[status_key] += 1

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph.id,
            "graph_name": graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            **_queue_payload(run),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "backend_attempt_id": run.active_attempt_id,
            "status_history": _build_run_status_history(run=run),
            "trace_id": run.trace_id,
            "last_progress_at": run.last_progress_at,
            "last_heartbeat_at": run.last_heartbeat_at,
            "engine_instance_id": run.engine_instance_id,
            "recovery_state": run.recovery_state,
            "recovery_reason": run.recovery_reason,
            "recovery_policy": run.recovery_policy,
            "resume_requested_at": run.resume_requested_at,
            "resume_attempt_id": run.resume_attempt_id,
            "paused_node_id": run.paused_node_id,
            "pause_payload": redact_payload(pause_payload),
            "node_outcomes": node_outcomes,
            "agent_events": agent_events,
            "timeline": _build_run_timeline(run=run),
            "memory_activity": summarize_run_memory_activity(node_runs, include_operations=True),
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [
                _serialize_node_run_for_detail(
                    node_run=node_run,
                    agent_events_by_node=agent_events_by_node,
                )
                for node_run in node_runs
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data)


def _mark_engine_dispatch_failure(
    dispatch: RunEngineDispatch,
    *,
    log_name: str,
    error_prefix: str,
    exc: Exception,
    response_code: str,
    response_message: str,
    response_status: int,
) -> Response:
    run = dispatch.run
    log_event(
        logger,
        logging.ERROR,
        log_name,
        run_id=str(run.id),
        trace_id=run.trace_id or dispatch.trace_metadata["trace_id"],
        error_message=str(exc),
    )
    transition = apply_run_status_transition(run, "failed")
    run.ended_at = timezone.now()
    run.error_message = f"{error_prefix}: {exc}"
    run.save(update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"])))
    if dispatch.failure_task_source:
        mark_run_tasks_terminal(
            run=run,
            status_value="failed",
            source=dispatch.failure_task_source,
            reason=run.error_message,
        )
    record_run_completed("failed", run.duration_ms)
    broadcast_run_updated(run)
    return error_response(
        code=response_code,
        message=response_message,
        status=response_status,
    )


def _dispatch_run_to_engine(dispatch: RunEngineDispatch) -> Response | None:
    callback_url = resolve_engine_callback_url(run_id=str(dispatch.run.id))
    memory_config_json = build_memory_config_json(
        dispatch.graph_version.graph,
        dispatch.run.owner,
        session_id=dispatch.session_id,
    )
    engine_input_json = _engine_input_for_llm_access(
        dispatch.run.input_json
        if isinstance(dispatch.run.input_json, dict)
        else dispatch.input_json,
        dispatch.llm_access,
    )
    try:
        with start_backend_span(
            dispatch.span_name,
            traceparent=dispatch.trace_metadata["traceparent"],
            tracestate=dispatch.trace_metadata["tracestate"],
            attributes={
                "forgegraph.run_id": str(dispatch.run.id),
                "forgegraph.graph_version_id": str(dispatch.graph_version.id),
                "forgegraph.trigger": dispatch.trigger,
            },
        ):
            selected_engine_id, engine_client = get_engine_assignment(
                run_id=str(dispatch.run.id),
                callback_url=callback_url,
            )
            with engine_client as engine:
                engine.start_run(
                    run_id=dispatch.run.id,
                    graph_json=dispatch.outbound_graph,
                    input_json=engine_input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=dispatch.tenant_id,
                    session_id=dispatch.session_id,
                    traceparent=dispatch.trace_metadata["traceparent"],
                    tracestate=dispatch.trace_metadata["tracestate"],
                )
                transition = apply_run_status_transition(dispatch.run, "running")
                update_fields = transition.update_fields
                update_fields.extend(
                    touch_run_liveness(
                        dispatch.run,
                        recovery_state=recovery_state_for_status("running"),
                        engine_instance_id=selected_engine_id,
                    )
                )
                dispatch.run.save(update_fields=sorted(set(update_fields)))
                _persist_run_updated_event(dispatch.run)
                record_run_started()
                broadcast_run_updated(dispatch.run)
    except EngineConnectionError as exc:
        return _mark_engine_dispatch_failure(
            dispatch,
            log_name="engine_connection_failed",
            error_prefix="Engine connection failed",
            exc=exc,
            response_code="ENGINE_UNAVAILABLE",
            response_message="The execution engine is not available. Please try again later.",
            response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except EngineExecutionError as exc:
        return _mark_engine_dispatch_failure(
            dispatch,
            log_name=dispatch.engine_rejected_event,
            error_prefix="Engine rejected run",
            exc=exc,
            response_code="ENGINE_ERROR",
            response_message=str(exc),
            response_status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class RunStartView(APIView):
    """Start a run."""

    permission_classes = [IsAuthenticated]

    def _build_start_request_context(
        self,
        request: Request,
    ) -> tuple[RunStartRequestContext | None, Response | None]:
        serializer = RunStartSerializer(data=request.data)
        if not serializer.is_valid():
            return None, error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to start runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        command_context = build_idempotency_context(
            request=request,
            organization=user.default_organization,
            action="runs.start",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        rate_limit_response = _apply_rate_limit(
            scope="run_start",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return None, rate_limit_response

        input_json = serializer.validated_data.get("input_json") or {}
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return None, input_size_response
        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        thread_id = serializer.validated_data.get("thread_id")
        return RunStartRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            graph_version_id=serializer.validated_data["graph_version_id"],
            input_json=input_json,
            llm_access=serializer.validated_data["llm_access"],
            thread_id=thread_id,
            session_id=str(thread_id) if thread_id else None,
        ), None

    def _start_policy_response(self, user: User) -> Response | None:
        entitlement_response = check_entitlements(user)
        if entitlement_response is not None:
            return entitlement_response
        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(user)

    def _start_input_schema_response(
        self,
        *,
        graph_version: GraphVersion,
        input_json: dict[str, Any],
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
        if not schema_errors:
            return None
        return error_response(
            code="INVALID_INPUT_SCHEMA",
            message="Input does not match the required schema.",
            status=status.HTTP_400_BAD_REQUEST,
            details=schema_errors,
        )

    def _start_credentials_response(
        self,
        *,
        user: User,
        prepared_graph: dict[str, Any],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        managed_limit_response = _managed_llm_limit_response(
            user=user,
            graph_json=prepared_graph,
            llm_access=llm_access,
        )
        if managed_limit_response is not None:
            return managed_limit_response

        credential_errors = validate_prompt_credentials(
            prepared_graph,
            user,
            llm_access=llm_access,
        )
        if not credential_errors:
            return None
        return error_response(
            code="INVALID_CREDENTIALS",
            message="Prompt node credentials are missing or invalid.",
            status=status.HTTP_400_BAD_REQUEST,
            details=credential_errors,
        )

    def _start_graph_version(
        self,
        *,
        tenant_uuid: UUID,
        graph_version_id: UUID,
    ) -> tuple[GraphVersion | None, Response | None]:
        try:
            return (
                GraphVersion.objects.select_related("graph")
                .filter(
                    Q(graph__organization_id=tenant_uuid)
                    | Q(
                        graph__organization__isnull=True,
                        graph__owner__default_organization_id=tenant_uuid,
                    ),
                    id=graph_version_id,
                )
                .get()
            ), None
        except GraphVersion.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=(
                    f"GraphVersion with id '{graph_version_id}' not found "
                    "or you do not have access to it"
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

    def _prepare_start_dispatch_graph(
        self,
        *,
        request: Request,
        context: RunStartRequestContext,
        mark: Callable[[str], None],
    ) -> tuple[
        GraphVersion | None,
        dict[str, Any] | None,
        dict[str, str] | None,
        LLMAccessConfig | None,
        Response | None,
    ]:
        graph_version, graph_response = self._start_graph_version(
            tenant_uuid=context.tenant_uuid,
            graph_version_id=context.graph_version_id,
        )
        if graph_response is not None:
            return None, None, None, None, graph_response
        assert graph_version is not None
        mark("graph_loaded")

        try:
            llm_access = resolve_llm_access_for_dispatch(context.llm_access, context.user)
        except LLMAccessValidationError as exc:
            return None, None, None, None, _llm_access_error_response(exc)

        policy_response = self._start_policy_response(context.user)
        if policy_response is not None:
            return None, None, None, None, policy_response
        mark("policy_checked")

        schema_response = self._start_input_schema_response(
            graph_version=graph_version,
            input_json=context.input_json,
        )
        if schema_response is not None:
            return None, None, None, None, schema_response

        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                context.user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            prepared_graph = attach_llm_access_to_graph(prepared_graph, llm_access)
        except LLMAccessValidationError as exc:
            return None, None, None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, None, None, _run_preparation_error_response(exc)

        trace_metadata = _trace_metadata_from_graph(prepared_graph)
        mark("graph_prepared")
        credentials_response = self._start_credentials_response(
            user=context.user,
            prepared_graph=prepared_graph,
            llm_access=llm_access,
        )
        if credentials_response is not None:
            return None, None, None, None, credentials_response
        mark("credentials_checked")
        return graph_version, prepared_graph, trace_metadata, llm_access, None

    def _create_start_run(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
    ) -> Run:
        return Run.objects.create(
            owner=context.user,
            organization=graph_version.graph.organization or context.user.default_organization,
            graph_version=graph_version,
            thread_id=context.thread_id,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=context.input_json,
            dispatch_graph_json=prepared_graph,
            output_json=None,
            error_message="",
            trace_id=trace_metadata["trace_id"],
        )

    def _initialize_start_run(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        queue_enabled: bool,
        mark: Callable[[str], None],
    ) -> None:
        initialize_lifecycle_tasks_for_run(
            run,
            source="run_start",
            initial_status="queued" if queue_enabled else "created",
            reason=(
                "run queued for backend-owned dispatch"
                if queue_enabled
                else "task initialized from graph"
            ),
        )
        mark("lifecycle_initialized")
        if not queue_enabled:
            broadcast_run_updated(run)
            mark("run_broadcast")
        record_audit_log(
            actor=context.user,
            tenant_id=get_tenant_id_for_user(context.user),
            action="run.started",
            resource_type="run",
            resource_id=str(run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=context.thread_id,
                trigger="start",
            ),
        )
        mark("audit_recorded")
        upsert_memory_session(context.user, context.session_id)
        mark("memory_session")

    def _queued_start_response(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        timing_started_at: float,
        timing_marks: list[tuple[str, float]],
        mark: Callable[[str], None],
    ) -> Response:
        queue_entry = enqueue_run(run, tenant_id=context.tenant_id)
        mark("run_enqueued")
        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "queue_status": queue_entry.status,
            "queue_attempts": queue_entry.attempts,
            "queue_available_at": queue_entry.available_at,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "trace_id": run.trace_id,
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        mark("serialized")
        response = success_response(
            serialized_data,
            status=status.HTTP_201_CREATED,
            meta=_queue_response_meta(run=run, tenant_id=context.tenant_id),
        )
        mark("response_built")
        response = record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )
        mark("processed_command_recorded")
        _log_run_start_timing(
            run=run,
            tenant_id=context.tenant_id,
            queued=True,
            started_at=timing_started_at,
            marks=timing_marks,
        )
        return response

    def _dispatch_start_run(
        self,
        *,
        request: Request,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        try:
            outbound_graph = prepare_tool_executions_for_dispatch(
                run=run,
                graph_json=prepared_graph,
            )
            outbound_graph = _attach_operation_context_pack(run, outbound_graph)
        except ToolExecutionDispatchBlocked as exc:
            transition = apply_run_status_transition(run, "failed")
            run.ended_at = timezone.now()
            run.error_message = str(exc)
            run.save(
                update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"]))
            )
            mark_run_tasks_terminal(
                run=run,
                status_value="failed",
                source="run_start",
                reason=str(exc),
            )
            return _tool_execution_dispatch_error_response(exc)

        return _dispatch_run_to_engine(
            RunEngineDispatch(
                run=run,
                graph_version=graph_version,
                outbound_graph=outbound_graph,
                input_json=context.input_json,
                llm_access=llm_access,
                session_id=context.session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.start",
                trigger="start",
                failure_task_source="run_start",
            )
        )

    def _started_run_response(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
    ) -> Response:
        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            **_queue_payload(run),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data, status=status.HTTP_201_CREATED)
        return record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def post(self, request: Request) -> Response:
        """Start a new run."""
        timing_started_at = time.perf_counter()
        timing_marks: list[tuple[str, float]] = []

        def mark(stage: str) -> None:
            timing_marks.append((stage, time.perf_counter()))

        start_context, context_response = self._build_start_request_context(request)
        if context_response is not None:
            return context_response
        assert start_context is not None
        mark("validated")

        (
            graph_version,
            prepared_graph,
            trace_metadata,
            llm_access,
            prepare_response,
        ) = self._prepare_start_dispatch_graph(
            request=request,
            context=start_context,
            mark=mark,
        )
        if prepare_response is not None:
            return prepare_response
        assert graph_version is not None
        assert prepared_graph is not None
        assert trace_metadata is not None
        assert llm_access is not None

        run = self._create_start_run(
            context=start_context,
            graph_version=graph_version,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
        )
        mark("run_created")
        queue_enabled = bool(getattr(settings, "RUN_QUEUE_ENABLED", False))
        self._initialize_start_run(
            context=start_context,
            graph_version=graph_version,
            run=run,
            queue_enabled=queue_enabled,
            mark=mark,
        )

        if queue_enabled:
            return self._queued_start_response(
                context=start_context,
                graph_version=graph_version,
                run=run,
                timing_started_at=timing_started_at,
                timing_marks=timing_marks,
                mark=mark,
            )

        dispatch_response = self._dispatch_start_run(
            request=request,
            context=start_context,
            graph_version=graph_version,
            run=run,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
            llm_access=llm_access,
        )
        if dispatch_response is not None:
            return dispatch_response

        return self._started_run_response(
            context=start_context,
            graph_version=graph_version,
            run=run,
        )


class RunInvokeView(APIView):
    """Invoke a threaded run using persisted state."""

    permission_classes = [IsAuthenticated]

    def _validated_invoke_serializer(self, request: Request) -> tuple[Any | None, Response | None]:
        serializer = RunInvokeSerializer(data=request.data)
        if serializer.is_valid():
            return serializer, None
        return None, error_response(
            code="VALIDATION_ERROR",
            message="The request contains invalid fields",
            status=status.HTTP_400_BAD_REQUEST,
            details=[
                {"field": field, "issue": ", ".join(errors)}
                for field, errors in serializer.errors.items()
            ],
        )

    def _invoke_policy_response(self, user: User) -> Response | None:
        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(user)

    def _active_thread_response(self, user: User, thread_id: UUID) -> Response | None:
        active_run = (
            run_queryset_for_user(user)
            .filter(
                thread_id=thread_id,
                status__in=["pending", "running", "paused", "resume_requested"],
            )
            .order_by("-started_at")
            .first()
        )
        if not active_run:
            return None
        return error_response(
            code="INVALID_STATE",
            message=f"Thread '{thread_id}' has an active run ({active_run.id}).",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _latest_thread_run(
        self,
        user: User,
        thread_id: UUID,
    ) -> tuple[Run | None, Response | None]:
        latest_run = (
            run_queryset_for_user(user)
            .filter(thread_id=thread_id)
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
        if latest_run is not None:
            return latest_run, None
        return None, error_response(
            code="NOT_FOUND",
            message=f"Thread with id '{thread_id}' not found",
            status=status.HTTP_404_NOT_FOUND,
        )

    def _run_checkpoint(self, run: Run) -> tuple[RunCheckpoint | None, Response | None]:
        try:
            return run.checkpoint, None
        except RunCheckpoint.DoesNotExist:
            return None, error_response(
                code="NO_CHECKPOINT",
                message="No persisted state found for this thread.",
                status=status.HTTP_409_CONFLICT,
            )

    def _prepare_invoke_dispatch_graph(
        self,
        *,
        request: Request,
        graph_version: GraphVersion,
        user: User,
        llm_access: LLMAccessConfig,
        input_json: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None, Response | None]:
        try:
            traceparent, tracestate = _request_trace_headers(request)
            graph_json = prepare_graph_for_engine(
                graph_version.graph_json,
                user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            graph_json = attach_llm_access_to_graph(graph_json, llm_access)
        except LLMAccessValidationError as exc:
            return None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, _run_preparation_error_response(exc)

        response = self._invoke_dispatch_graph_response(
            user=user,
            graph_version=graph_version,
            graph_json=graph_json,
            input_json=input_json,
            llm_access=llm_access,
        )
        if response is not None:
            return None, None, response
        return graph_json, _trace_metadata_from_graph(graph_json), None

    def _invoke_input_json(
        self,
        validated_data: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, Response | None]:
        input_json = validated_data.get("input_json") or {}
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return None, input_size_response
        if isinstance(input_json, dict):
            return input_json, None
        return None, error_response(
            code="VALIDATION_ERROR",
            message="input_json must be a JSON object",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _invoke_llm_access(
        self,
        validated_data: dict[str, Any],
        user: User,
    ) -> tuple[LLMAccessConfig | None, Response | None]:
        try:
            return resolve_llm_access_for_dispatch(validated_data["llm_access"], user), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _invoke_thread_checkpoint(
        self,
        *,
        user: User,
        thread_id: UUID,
    ) -> tuple[Run | None, RunCheckpoint | None, Response | None]:
        active_response = self._active_thread_response(user, thread_id)
        if active_response is not None:
            return None, None, active_response

        latest_run, latest_response = self._latest_thread_run(user, thread_id)
        if latest_response is not None:
            return None, None, latest_response
        assert latest_run is not None

        checkpoint, checkpoint_response = self._run_checkpoint(latest_run)
        if checkpoint_response is not None:
            return None, None, checkpoint_response
        assert checkpoint is not None
        return latest_run, checkpoint, None

    def _invoke_dispatch_graph_response(
        self,
        *,
        user: User,
        graph_version: GraphVersion,
        graph_json: dict[str, Any],
        input_json: dict[str, Any],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        managed_limit_response = _managed_llm_limit_response(
            user=user,
            graph_json=graph_json,
            llm_access=llm_access,
        )
        if managed_limit_response is not None:
            return managed_limit_response

        credential_errors = validate_prompt_credentials(graph_json, user, llm_access=llm_access)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )
        return _input_schema_validation_response(graph_version.graph_json, input_json)

    def _build_invoke_request_context(
        self,
        request: Request,
    ) -> tuple[RunInvokeRequestContext | None, Response | None]:
        serializer, serializer_response = self._validated_invoke_serializer(request)
        if serializer_response is not None:
            return None, serializer_response
        assert serializer is not None

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to invoke runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        command_context = build_idempotency_context(
            request=request,
            organization=user.default_organization,
            action="runs.invoke",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        rate_limit_response = _apply_rate_limit(
            scope="run_invoke",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_INVOKE_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return None, rate_limit_response

        input_json, input_response = self._invoke_input_json(serializer.validated_data)
        if input_response is not None:
            return None, input_response
        assert input_json is not None

        llm_access, llm_response = self._invoke_llm_access(serializer.validated_data, user)
        if llm_response is not None:
            return None, llm_response
        assert llm_access is not None

        policy_response = self._invoke_policy_response(user)
        if policy_response is not None:
            return None, policy_response

        thread_id = serializer.validated_data["thread_id"]
        latest_run, checkpoint, thread_response = self._invoke_thread_checkpoint(
            user=user,
            thread_id=thread_id,
        )
        if thread_response is not None:
            return None, thread_response
        assert checkpoint is not None
        assert latest_run is not None

        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        return RunInvokeRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            thread_id=thread_id,
            session_id=str(thread_id),
            input_json=input_json,
            llm_access=llm_access,
            latest_run=latest_run,
            checkpoint=checkpoint,
        ), None

    def post(self, request: Request) -> Response:
        invoke_context, context_response = self._build_invoke_request_context(request)
        if context_response is not None:
            return context_response
        assert invoke_context is not None
        user = invoke_context.user
        tenant_id = invoke_context.tenant_id
        command_context = invoke_context.command_context
        thread_id = invoke_context.thread_id
        session_id = invoke_context.session_id
        input_json = invoke_context.input_json
        llm_access = invoke_context.llm_access
        latest_run = invoke_context.latest_run
        checkpoint = invoke_context.checkpoint

        graph_version = latest_run.graph_version
        graph_json, trace_metadata, prepare_response = self._prepare_invoke_dispatch_graph(
            request=request,
            graph_version=graph_version,
            user=user,
            llm_access=llm_access,
            input_json=input_json,
        )
        if prepare_response is not None:
            return prepare_response
        assert graph_json is not None and trace_metadata is not None
        checkpoint_graph_json = pyjson.dumps(graph_json)

        seed_state = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        seed_state = dict(seed_state)
        for key, value in input_json.items():
            seed_state[f"input.{key}"] = value

        try:
            with transaction.atomic():
                run = Run.objects.create(
                    owner=user,
                    organization=graph_version.graph.organization or user.default_organization,
                    graph_version=graph_version,
                    thread_id=thread_id,
                    status="pending",
                    started_at=timezone.now(),
                    ended_at=None,
                    input_json=input_json,
                    dispatch_graph_json=graph_json,
                    output_json=None,
                    error_message="",
                    trace_id=trace_metadata["trace_id"],
                )
                outbound_graph = prepare_tool_executions_for_dispatch(
                    run=run,
                    graph_json=graph_json,
                )
                outbound_graph = _attach_operation_context_pack(run, outbound_graph)
                checkpoint_graph_json = pyjson.dumps(outbound_graph)

                RunCheckpoint.objects.create(
                    run=run,
                    node_id="seed",
                    step_index=0,
                    state_json=seed_state,
                    completed_nodes=[],
                    skipped_nodes=[],
                    graph_json=checkpoint_graph_json,
                )
        except ToolExecutionDispatchBlocked as exc:
            return _tool_execution_dispatch_error_response(exc)

        broadcast_run_updated(run)
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="run.started",
            resource_type="run",
            resource_id=str(run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=thread_id,
                trigger="invoke",
                extra={"source_run_id": str(latest_run.id)},
            ),
        )

        upsert_memory_session(user, session_id)

        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            queue_entry = enqueue_run(run, tenant_id=tenant_id)
            run_data = {
                "id": run.id,
                "owner_id": run.owner_id,
                "owner_email": run.owner.email,
                "thread_id": run.thread_id,
                "graph_id": graph_version.graph_id,
                "graph_name": graph_version.graph.name,
                "graph_version_id": graph_version.id,
                "graph_version": graph_version.version,
                "status": run.status,
                "queue_status": queue_entry.status,
                "queue_attempts": queue_entry.attempts,
                "queue_available_at": queue_entry.available_at,
                "started_at": run.started_at,
                "ended_at": run.ended_at,
                "input_json": redact_payload(run.input_json),
                "output_json": redact_payload(run.output_json),
                "error_message": redact_payload(run.error_message),
                "duration_ms": run.duration_ms,
                "trace_id": run.trace_id,
                "llm_access": _public_llm_access_payload(run),
                "node_runs": [],
            }
            serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
            response = success_response(
                serialized_data,
                status=status.HTTP_201_CREATED,
                meta=_queue_response_meta(run=run, tenant_id=tenant_id),
            )
            return record_processed_command(
                context=command_context,
                response=response,
                resource_type="run",
                resource_id=str(run.id),
            )

        dispatch_response = _dispatch_run_to_engine(
            RunEngineDispatch(
                run=run,
                graph_version=graph_version,
                outbound_graph=outbound_graph,
                input_json=input_json,
                llm_access=llm_access,
                session_id=session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.invoke",
                trigger="invoke",
            )
        )
        if dispatch_response is not None:
            return dispatch_response

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            **_queue_payload(run),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data, status=status.HTTP_201_CREATED)
        return record_processed_command(
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )


class RunReplayView(APIView):
    """Replay a completed run from its latest checkpoint."""

    permission_classes = [IsAuthenticated]

    def _event_safety_response(
        self,
        *,
        event_type: str,
        normalized_category: str,
        payload: dict[str, Any],
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=payload,
            )
        except EventSafetyViolation as exc:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        return None

    def _run_output_schema_errors(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]] | None]:
        output_schema = None
        schema_mode = "warn"
        try:
            _, output_schema, _, schema_mode = extract_schema_metadata(run.graph_version.graph_json)
        except Exception:
            output_schema = None

        if not (
            output_schema and payload.get("status") == "succeeded" and "output_json" in payload
        ):
            return schema_mode, None
        try:
            return schema_mode, validate_json_schema(payload.get("output_json"), output_schema)
        except SchemaError as exc:
            log_event(
                logger,
                logging.WARNING,
                "run_output_schema_invalid",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
            return schema_mode, None

    def _apply_authenticated_run_payload(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> None:
        update_fields: list[str] = []
        for field in ["status", "started_at", "ended_at", "output_json", "error_message"]:
            if field not in payload:
                continue
            value = payload[field]
            if field in {"output_json", "error_message"}:
                value = redact_payload(value)
            setattr(run, field, value)
            payload[field] = value
            update_fields.append(field)

        if "paused_node_id" in payload:
            run.paused_node_id = payload["paused_node_id"]
            update_fields.append("paused_node_id")
        if "pause_state_json" in payload:
            run.pause_state_json = redact_payload(payload["pause_state_json"])
            payload["pause_state_json"] = run.pause_state_json
            update_fields.append("pause_state_json")

        if update_fields:
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status(run.status),
                    engine_instance_id=run.engine_instance_id or engine_instance_label(),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _ensure_pause_approval_task(self, *, run: Run, payload: dict[str, Any]) -> None:
        if payload.get("status") != "paused":
            return
        pause_output = payload.get("pause_payload", {})
        node_id = run.paused_node_id or pause_output.get("node_id", "")
        if not node_id:
            return
        ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": {
                    "prompt_message": pause_output.get("prompt_message", ""),
                    "required_fields": pause_output.get("required_fields", []),
                },
            },
        )

    def _persist_authenticated_schema_errors(
        self,
        *,
        run: Run,
        schema_mode: str,
        schema_errors: list[dict[str, Any]] | None,
    ) -> None:
        if not schema_errors:
            return
        try:
            RunEvent.objects.create(
                run=run,
                event_type="run.schema_validation",
                payload=redact_payload(
                    {
                        "errors": schema_errors,
                        "mode": schema_mode,
                        "category": normalize_event_category("run.schema_validation"),
                    }
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _persist_authenticated_run_event(
        self,
        *,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        normalized_category: str,
    ) -> None:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "run_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _handle_authenticated_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        schema_mode, schema_errors = self._run_output_schema_errors(run=run, payload=payload)
        if schema_errors and schema_mode == "strict":
            payload["status"] = "failed"
            payload["error_message"] = (
                f"Output schema validation failed: {schema_errors[0]['message']}"
            )
        self._apply_authenticated_run_payload(run=run, payload=payload)
        self._ensure_pause_approval_task(run=run, payload=payload)
        self._persist_authenticated_schema_errors(
            run=run,
            schema_mode=schema_mode,
            schema_errors=schema_errors,
        )
        self._persist_authenticated_run_event(
            run=run,
            event_type=event_type,
            payload=payload,
            normalized_category=normalized_category,
        )
        return success_response(broadcast_run_updated(run))

    def _apply_authenticated_node_payload(
        self,
        *,
        node_run: NodeRun,
        created: bool,
        node_type: Any,
        payload: dict[str, Any],
    ) -> list[str]:
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")
        node_run.status = payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field not in payload:
                continue
            value = redact_payload(payload[field]) if field.endswith("_json") else payload[field]
            setattr(node_run, field, value)
            payload[field] = value
            node_update_fields.append(field)
        return node_update_fields

    def _handle_authenticated_node_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
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
            node_update_fields = self._apply_authenticated_node_payload(
                node_run=node_run,
                created=created,
                node_type=node_type,
                payload=payload,
            )
            node_run.save(update_fields=sorted(set(node_update_fields)))
            run_update_fields = touch_run_liveness(
                run,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=run.engine_instance_id or engine_instance_label(),
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )

        return success_response(broadcast_node_run_updated(run=run, node_run=node_run))

    def _handle_authenticated_schema_validation(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload={
                    **payload,
                    "category": normalized_category,
                },
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
        return success_response(broadcast_run_schema_validation(run=run, payload=payload))

    def _validated_replay_serializer(self, request: Request) -> tuple[Any | None, Response | None]:
        serializer = RunReplaySerializer(data=request.data)
        if serializer.is_valid():
            return serializer, None
        return None, error_response(
            code="VALIDATION_ERROR",
            message="The request contains invalid fields",
            status=status.HTTP_400_BAD_REQUEST,
            details=[
                {"field": field, "issue": ", ".join(errors)}
                for field, errors in serializer.errors.items()
            ],
        )

    def _replay_source_run(
        self,
        *,
        user: User,
        run_id: UUID,
    ) -> tuple[Run | None, Response | None]:
        try:
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
        except Run.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        if run.status not in {"pending", "running", "paused", "resume_requested"}:
            return run, None
        return None, error_response(
            code="INVALID_STATE",
            message=f"Cannot replay a run in status '{run.status}'. Run must be completed.",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _replay_llm_access(
        self,
        *,
        request: Request,
        serializer: Any,
        run: Run,
        user: User,
    ) -> tuple[LLMAccessConfig | None, Response | None]:
        request_overrides_llm_access = any(
            key in request.data for key in ("llm_mode", "provider", "credential_id", "api_key")
        )
        try:
            if request_overrides_llm_access:
                return resolve_llm_access_for_dispatch(
                    serializer.validated_data["llm_access"],
                    user,
                ), None
            return engine_llm_access_from_graph(
                run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {},
                user,
            ), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _replay_checkpoint(self, run: Run) -> tuple[RunCheckpoint | None, Response | None]:
        try:
            return run.checkpoint, None
        except RunCheckpoint.DoesNotExist:
            return None, error_response(
                code="NO_CHECKPOINT",
                message="No checkpoint available for this run.",
                status=status.HTTP_409_CONFLICT,
            )

    def _active_replay_thread_response(self, *, user: User, run: Run) -> Response | None:
        if not run.thread_id:
            return None
        active_run = (
            run_queryset_for_user(user)
            .filter(
                thread_id=run.thread_id,
                status__in=["pending", "running", "paused", "resume_requested"],
            )
            .order_by("-started_at")
            .first()
        )
        if not active_run:
            return None
        return error_response(
            code="INVALID_STATE",
            message=f"Thread '{run.thread_id}' has an active run ({active_run.id}).",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _build_replay_request_context(
        self,
        request: Request,
        run_id: UUID,
    ) -> tuple[RunReplayRequestContext | None, Response | None]:
        serializer, serializer_response = self._validated_replay_serializer(request)
        if serializer_response is not None:
            return None, serializer_response
        assert serializer is not None

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to replay runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        node_id = str(serializer.validated_data.get("node_id") or "").strip()

        run, run_response = self._replay_source_run(user=user, run_id=run_id)
        if run_response is not None:
            return None, run_response
        assert run is not None

        command_context = build_idempotency_context(
            request=request,
            organization=run.organization or user.default_organization,
            action=f"runs.replay:{run.id}",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        llm_access, llm_response = self._replay_llm_access(
            request=request,
            serializer=serializer,
            run=run,
            user=user,
        )
        if llm_response is not None:
            return None, llm_response
        assert llm_access is not None

        checkpoint, checkpoint_response = self._replay_checkpoint(run)
        if checkpoint_response is not None:
            return None, checkpoint_response
        assert checkpoint is not None

        thread_response = self._active_replay_thread_response(user=user, run=run)
        if thread_response is not None:
            return None, thread_response

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return None, budget_response
        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        return RunReplayRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            run=run,
            node_id=node_id,
            llm_access=llm_access,
            checkpoint=checkpoint,
            input_json=run.input_json if isinstance(run.input_json, dict) else {},
            session_id=str(run.thread_id) if run.thread_id else None,
        ), None

    def _prepare_replay_dispatch_graph(
        self,
        *,
        request: Request,
        replay_context: RunReplayRequestContext,
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None, Response | None]:
        run = replay_context.run
        graph_version = run.graph_version
        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                replay_context.user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            prepared_graph = attach_llm_access_to_graph(
                prepared_graph,
                replay_context.llm_access,
            )
        except LLMAccessValidationError as exc:
            return None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, _run_preparation_error_response(exc)

        managed_limit_response = _managed_llm_limit_response(
            user=replay_context.user,
            graph_json=prepared_graph,
            llm_access=replay_context.llm_access,
        )
        if managed_limit_response is not None:
            return None, None, managed_limit_response

        credential_errors = validate_prompt_credentials(
            prepared_graph,
            replay_context.user,
            llm_access=replay_context.llm_access,
        )
        if credential_errors:
            return (
                None,
                None,
                error_response(
                    code="INVALID_CREDENTIALS",
                    message="Prompt node credentials are missing or invalid.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=credential_errors,
                ),
            )

        return prepared_graph, _trace_metadata_from_graph(prepared_graph), None

    def _replay_checkpoint_seed(
        self,
        *,
        checkpoint: RunCheckpoint,
        prepared_graph: dict[str, Any],
        node_id: str,
    ) -> tuple[ReplayCheckpointSeed | None, Response | None]:
        replay_nodes: set[str] = set()
        if node_id:
            replay_nodes = _get_downstream_nodes(prepared_graph, node_id)
            if not replay_nodes:
                return None, error_response(
                    code="INVALID_NODE",
                    message=f"Node '{node_id}' was not found in the graph.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

        state_json = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        state_json = dict(state_json)
        completed_nodes = list(checkpoint.completed_nodes or [])
        skipped_nodes = list(checkpoint.skipped_nodes or [])
        if replay_nodes:
            state_json = _prune_state_for_nodes(state_json, replay_nodes)
            completed_nodes = [node for node in completed_nodes if node not in replay_nodes]
            skipped_nodes = [node for node in skipped_nodes if node not in replay_nodes]

        return ReplayCheckpointSeed(
            state_json=state_json,
            completed_nodes=completed_nodes,
            skipped_nodes=skipped_nodes,
        ), None

    def _create_replay_run(
        self,
        *,
        replay_context: RunReplayRequestContext,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
        seed: ReplayCheckpointSeed,
    ) -> tuple[Run | None, dict[str, Any] | None, Response | None]:
        source_run = replay_context.run
        graph_version = source_run.graph_version
        replay_context_pack_id = ""
        try:
            with transaction.atomic():
                replay_run = Run.objects.create(
                    owner=replay_context.user,
                    organization=graph_version.graph.organization
                    or replay_context.user.default_organization,
                    graph_version=graph_version,
                    thread_id=source_run.thread_id,
                    status="pending",
                    started_at=timezone.now(),
                    ended_at=None,
                    input_json=replay_context.input_json,
                    dispatch_graph_json=prepared_graph,
                    output_json=None,
                    error_message="",
                    trace_id=trace_metadata["trace_id"],
                )
                outbound_graph = prepare_tool_executions_for_dispatch(
                    run=replay_run,
                    graph_json=prepared_graph,
                )
                outbound_graph = _attach_operation_context_pack(
                    replay_run,
                    outbound_graph,
                    context_pack_mode="fresh_at_replay",
                )
                outbound_metadata = (
                    outbound_graph.get("metadata") if isinstance(outbound_graph, dict) else {}
                )
                replay_context_pack_id = (
                    str(outbound_metadata.get("context_pack_id") or "")
                    if isinstance(outbound_metadata, dict)
                    else ""
                )

                RunCheckpoint.objects.create(
                    run=replay_run,
                    node_id=replay_context.checkpoint.node_id,
                    step_index=replay_context.checkpoint.step_index,
                    state_json=seed.state_json,
                    completed_nodes=seed.completed_nodes,
                    skipped_nodes=seed.skipped_nodes,
                    graph_json=pyjson.dumps(outbound_graph),
                )
                RunEvent.objects.create(
                    run=replay_run,
                    event_type="run.replay",
                    payload={
                        "source_run_id": str(source_run.id),
                        "from_node_id": replay_context.node_id or None,
                        "checkpoint_step": replay_context.checkpoint.step_index,
                        "context_pack_id": replay_context_pack_id or None,
                        "context_pack_mode": "fresh_at_replay",
                    },
                    trace_id=trace_metadata["trace_id"],
                    span_id=trace_metadata["span_id"],
                )
        except ToolExecutionDispatchBlocked as exc:
            return None, None, _tool_execution_dispatch_error_response(exc)
        return replay_run, outbound_graph, None

    def _record_replay_created(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> None:
        source_run = replay_context.run
        graph_version = source_run.graph_version
        broadcast_run_updated(replay_run)
        record_audit_log(
            actor=replay_context.user,
            tenant_id=get_tenant_id_for_user(replay_context.user),
            action="run.replayed",
            resource_type="run",
            resource_id=str(replay_run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=replay_run.thread_id,
                trigger="replay",
                extra={
                    "source_run_id": str(source_run.id),
                    "from_node_id": replay_context.node_id or None,
                },
            ),
        )
        upsert_memory_session(replay_context.user, replay_context.session_id)

    def _queued_replay_response(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> Response:
        graph_version = replay_context.run.graph_version
        queue_entry = enqueue_run(replay_run, tenant_id=replay_context.tenant_id)
        run_data = {
            "id": replay_run.id,
            "owner_id": replay_run.owner_id,
            "owner_email": replay_run.owner.email,
            "thread_id": replay_run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": replay_run.status,
            "queue_status": queue_entry.status,
            "queue_attempts": queue_entry.attempts,
            "queue_available_at": queue_entry.available_at,
            "started_at": replay_run.started_at,
            "ended_at": replay_run.ended_at,
            "input_json": redact_payload(replay_run.input_json),
            "output_json": redact_payload(replay_run.output_json),
            "error_message": redact_payload(replay_run.error_message),
            "duration_ms": replay_run.duration_ms,
            "trace_id": replay_run.trace_id,
            "llm_access": _public_llm_access_payload(replay_run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(
            serialized_data,
            status=status.HTTP_201_CREATED,
            meta=_queue_response_meta(
                run=replay_run,
                tenant_id=replay_context.tenant_id,
            ),
        )
        return record_processed_command(
            context=replay_context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(replay_run.id),
        )

    def _dispatch_replay_run(
        self,
        *,
        request: Request,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
        outbound_graph: dict[str, Any],
        trace_metadata: dict[str, str],
    ) -> Response | None:
        return _dispatch_run_to_engine(
            RunEngineDispatch(
                run=replay_run,
                graph_version=replay_context.run.graph_version,
                outbound_graph=outbound_graph,
                input_json=replay_context.input_json,
                llm_access=replay_context.llm_access,
                session_id=replay_context.session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.replay",
                trigger="replay",
                engine_rejected_event="engine_rejected_replay",
            )
        )

    def _replay_run_response(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> Response:
        graph_version = replay_context.run.graph_version
        run_data = {
            "id": replay_run.id,
            "owner_id": replay_run.owner_id,
            "owner_email": replay_run.owner.email,
            "thread_id": replay_run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": replay_run.status,
            **_queue_payload(replay_run),
            "started_at": replay_run.started_at,
            "ended_at": replay_run.ended_at,
            "input_json": redact_payload(replay_run.input_json),
            "output_json": redact_payload(replay_run.output_json),
            "error_message": redact_payload(replay_run.error_message),
            "duration_ms": replay_run.duration_ms,
            "llm_access": _public_llm_access_payload(replay_run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data, status=status.HTTP_201_CREATED)
        return record_processed_command(
            context=replay_context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(replay_run.id),
        )

    def post(self, request: Request, run_id: UUID) -> Response:
        replay_context, context_response = self._build_replay_request_context(request, run_id)
        if context_response is not None:
            return context_response
        assert replay_context is not None
        checkpoint = replay_context.checkpoint

        prepared_graph, trace_metadata, prepare_response = self._prepare_replay_dispatch_graph(
            request=request,
            replay_context=replay_context,
        )
        if prepare_response is not None:
            return prepare_response
        assert prepared_graph is not None
        assert trace_metadata is not None

        seed, seed_response = self._replay_checkpoint_seed(
            checkpoint=checkpoint,
            prepared_graph=prepared_graph,
            node_id=replay_context.node_id,
        )
        if seed_response is not None:
            return seed_response
        assert seed is not None

        replay_run, outbound_graph, create_response = self._create_replay_run(
            replay_context=replay_context,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
            seed=seed,
        )
        if create_response is not None:
            return create_response
        assert replay_run is not None
        assert outbound_graph is not None

        self._record_replay_created(replay_context=replay_context, replay_run=replay_run)
        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            return self._queued_replay_response(
                replay_context=replay_context,
                replay_run=replay_run,
            )

        dispatch_response = self._dispatch_replay_run(
            request=request,
            replay_context=replay_context,
            replay_run=replay_run,
            outbound_graph=outbound_graph,
            trace_metadata=trace_metadata,
        )
        if dispatch_response is not None:
            return dispatch_response

        return self._replay_run_response(
            replay_context=replay_context,
            replay_run=replay_run,
        )


class RunCancelView(APIView):
    """Cancel a run."""

    permission_classes = [IsAuthenticated]

    def _event_safety_response(
        self,
        *,
        event_type: str,
        normalized_category: str,
        payload: dict[str, Any],
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=payload,
            )
        except EventSafetyViolation as exc:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        return None

    def _run_output_schema_errors(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]] | None]:
        output_schema = None
        schema_mode = "warn"
        try:
            _, output_schema, _, schema_mode = extract_schema_metadata(run.graph_version.graph_json)
        except Exception:
            output_schema = None

        if not (
            isinstance(output_schema, dict)
            and payload.get("status") == "succeeded"
            and "output_json" in payload
        ):
            return schema_mode, None
        try:
            return schema_mode, validate_json_schema(payload.get("output_json"), output_schema)
        except SchemaError as exc:
            log_event(
                logger,
                logging.WARNING,
                "run_output_schema_invalid",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
            return schema_mode, None

    def _apply_authenticated_run_payload(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> None:
        update_fields: list[str] = []
        for field in ["status", "started_at", "ended_at", "output_json", "error_message"]:
            if field not in payload:
                continue
            value = payload[field]
            if field in {"output_json", "error_message"}:
                value = redact_payload(value)
            setattr(run, field, value)
            payload[field] = value
            update_fields.append(field)

        if "paused_node_id" in payload:
            run.paused_node_id = payload["paused_node_id"]
            update_fields.append("paused_node_id")
        if "pause_state_json" in payload:
            run.pause_state_json = redact_payload(payload["pause_state_json"])
            payload["pause_state_json"] = run.pause_state_json
            update_fields.append("pause_state_json")

        if update_fields:
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status(run.status),
                    engine_instance_id=run.engine_instance_id or engine_instance_label(),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _ensure_pause_approval_task(self, *, run: Run, payload: dict[str, Any]) -> None:
        if payload.get("status") != "paused":
            return
        pause_output = payload.get("pause_payload", {})
        node_id = run.paused_node_id or pause_output.get("node_id", "")
        if not node_id:
            return
        ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": {
                    "prompt_message": pause_output.get("prompt_message", ""),
                    "required_fields": pause_output.get("required_fields", []),
                },
            },
        )

    def _persist_authenticated_schema_errors(
        self,
        *,
        run: Run,
        schema_mode: str,
        schema_errors: list[dict[str, Any]] | None,
    ) -> None:
        if not schema_errors:
            return
        try:
            RunEvent.objects.create(
                run=run,
                event_type="run.schema_validation",
                payload=redact_payload(
                    {
                        "errors": schema_errors,
                        "mode": schema_mode,
                        "category": normalize_event_category("run.schema_validation"),
                    }
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _persist_authenticated_run_event(
        self,
        *,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        normalized_category: str,
    ) -> None:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "run_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _handle_authenticated_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        schema_mode, schema_errors = self._run_output_schema_errors(run=run, payload=payload)
        if schema_errors and schema_mode == "strict":
            payload["status"] = "failed"
            payload["error_message"] = (
                f"Output schema validation failed: {schema_errors[0]['message']}"
            )
        self._apply_authenticated_run_payload(run=run, payload=payload)
        self._ensure_pause_approval_task(run=run, payload=payload)
        self._persist_authenticated_schema_errors(
            run=run,
            schema_mode=schema_mode,
            schema_errors=schema_errors,
        )
        self._persist_authenticated_run_event(
            run=run,
            event_type=event_type,
            payload=payload,
            normalized_category=normalized_category,
        )
        return success_response(broadcast_run_updated(run))

    def _apply_authenticated_node_payload(
        self,
        *,
        node_run: NodeRun,
        created: bool,
        node_type: Any,
        payload: dict[str, Any],
    ) -> list[str]:
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")
        node_run.status = payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field not in payload:
                continue
            value = redact_payload(payload[field]) if field.endswith("_json") else payload[field]
            setattr(node_run, field, value)
            payload[field] = value
            node_update_fields.append(field)
        return node_update_fields

    def _handle_authenticated_node_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
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
            node_update_fields = self._apply_authenticated_node_payload(
                node_run=node_run,
                created=created,
                node_type=node_type,
                payload=payload,
            )
            node_run.save(update_fields=sorted(set(node_update_fields)))
            run_update_fields = touch_run_liveness(
                run,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=run.engine_instance_id or engine_instance_label(),
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )

        return success_response(broadcast_node_run_updated(run=run, node_run=node_run))

    def _handle_authenticated_schema_validation(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload={
                    **payload,
                    "category": normalized_category,
                },
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
        return success_response(broadcast_run_schema_validation(run=run, payload=payload))

    def post(self, request: Request, run_id: UUID) -> Response:
        """Cancel a running run."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to cancel runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
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
                run_queryset_for_user(user)
                .select_related("graph_version__graph")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id)
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        command_context = build_idempotency_context(
            request=request,
            organization=run.organization or user.default_organization,
            action=f"runs.cancel:{run.id}",
            request_payload=request.data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return replayed_response

        if run.status in {"succeeded", "failed", "canceled"}:
            return error_response(
                code="INVALID_STATE",
                message=f"Cannot cancel a run in status '{run.status}'.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tell the engine to cancel the run
        try:
            _, engine_client = get_engine_client_for_run(run=run)
            with engine_client as engine:
                engine.cancel_run(run_id=run.id)

        except EngineConnectionError as e:
            log_event(
                logger,
                logging.WARNING,
                "engine_cancel_connection_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(e),
            )
            # Still proceed to mark as canceled in the control plane

        except EngineExecutionError as e:
            log_event(
                logger,
                logging.WARNING,
                "engine_cancel_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(e),
            )
            # Still proceed to mark as canceled in the control plane

        if not run.started_at:
            run.started_at = timezone.now()

        transition = apply_run_status_transition(run, "canceled")
        run.ended_at = timezone.now()
        if not run.error_message:
            run.error_message = "Canceled by user."

        run.save(
            update_fields=sorted(
                set(transition.update_fields + ["started_at", "ended_at", "error_message"])
            )
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_run(run),
            action="run.canceled",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "status": run.status,
                "reason": run.error_message,
            },
        )
        mark_run_tasks_terminal(
            run=run,
            status_value="cancelled",
            source="run_cancel",
            reason=run.error_message or "Canceled by user.",
        )
        record_run_completed("canceled", run.duration_ms)
        broadcast_run_updated(run)

        graph_version = run.graph_version
        graph = graph_version.graph
        node_runs = list(run.node_runs.all())

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph.id,
            "graph_name": graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "memory_activity": summarize_run_memory_activity(node_runs, include_operations=True),
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [
                _serialize_node_run_for_detail(node_run=node_run) for node_run in node_runs
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data)
        return record_processed_command(
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )


class RunResumeView(APIView):
    """Resume a paused run (human gate approval/rejection)."""

    permission_classes = [IsAuthenticated]

    def _load_resume_request_context(
        self,
        *,
        request: Request,
        run_id: UUID,
    ) -> tuple[RunResumeRequestContext | None, Response | None]:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to resume runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = RunResumeSerializer(data=request.data)
        if not serializer.is_valid():
            return None, error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        try:
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
        except Run.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        organization = run.organization or user.default_organization
        command_context = build_idempotency_context(
            request=request,
            organization=organization,
            action=f"runs.resume:{run.id}",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        node_id = serializer.validated_data["node_id"]
        input_json = serializer.validated_data.get("input_json", {})
        submit_id = _resume_submit_id(
            request=request,
            run_id=run.id,
            node_id=node_id,
            input_json=input_json,
        )
        decision_request_hash = hash_request_payload(
            {
                "run_id": str(run.id),
                "node_id": node_id,
                "input_json": input_json,
            }
        )
        decision_submission, decision_response = self._load_resume_decision_submission(
            run=run,
            organization=organization,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
        )
        if decision_response is not None:
            return None, decision_response
        if run.status not in {"paused", "resume_requested"}:
            return None, error_response(
                code="INVALID_STATE",
                message=(
                    f"Cannot resume a run in status '{run.status}'. "
                    "Run must be paused or already resuming."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        resume_attempt_id = uuid4()
        if decision_submission is not None and decision_submission.resume_attempt_id:
            resume_attempt_id = decision_submission.resume_attempt_id
        return RunResumeRequestContext(
            user=user,
            run=run,
            organization=organization,
            command_context=command_context,
            node_id=node_id,
            input_json=input_json,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
            decision_submission=decision_submission,
            resume_attempt_id=resume_attempt_id,
        ), None

    def _resume_preflight_response(
        self,
        *,
        context: RunResumeRequestContext,
        pending_approval_task: ApprovalTask | None,
    ) -> Response | None:
        run = context.run
        if pending_approval_task is None:
            resolved_response = self._resolved_approval_response(
                run=run,
                node_id=context.node_id,
                input_json=context.input_json,
                submit_id=context.submit_id,
                decision_submission=context.decision_submission,
                command_context=context.command_context,
            )
            if resolved_response is not None:
                return resolved_response
        if run.status == "resume_requested":
            return error_response(
                code="INVALID_STATE",
                message="Resume already requested for this run.",
                status=status.HTTP_409_CONFLICT,
            )
        if run.paused_node_id and run.paused_node_id != context.node_id:
            return error_response(
                code="INVALID_NODE",
                message=f"Node '{context.node_id}' does not match paused node '{run.paused_node_id}'",
                status=status.HTTP_400_BAD_REQUEST,
            )

        entitlement_response = check_entitlements(context.user)
        if entitlement_response is not None:
            return entitlement_response
        quota_response = check_llm_quota(context.user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(context.user)

    def _resume_trace_context(self, *, request: Request, run: Run) -> dict[str, str]:
        traceparent, tracestate = _request_trace_headers(request)
        trace_context = ensure_trace_context(
            traceparent=traceparent,
            tracestate=tracestate,
            trace_id=run.trace_id or None,
        )
        if not run.trace_id:
            run.trace_id = trace_context["trace_id"]
            run.save(update_fields=["trace_id"])
        return trace_context

    def _resume_engine_input(
        self,
        *,
        run: Run,
        user: User,
        input_json: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, Response | None]:
        try:
            resume_llm_access = engine_llm_access_from_graph(
                run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {},
                user,
            )
            return _engine_input_for_llm_access(input_json, resume_llm_access), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _updated_resume_snapshot(
        self,
        *,
        existing_snapshot: RunSnapshot | None,
        resume_attempt_id: UUID,
        resume_requested_at: datetime,
    ) -> RunSnapshot | None:
        if existing_snapshot is None:
            return None
        return RunSnapshot(
            run_id=existing_snapshot.run_id,
            last_completed_node=existing_snapshot.last_completed_node,
            next_node=existing_snapshot.next_node,
            attempt_id=str(resume_attempt_id),
            updated_at=resume_requested_at,
        )

    def _activate_resume_attempt(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> Response | None:
        existing_snapshot = get_snapshot(run.id)
        updated_snapshot = self._updated_resume_snapshot(
            existing_snapshot=existing_snapshot,
            resume_attempt_id=resume_attempt_id,
            resume_requested_at=resume_requested_at,
        )
        self._mark_resume_requested(
            run=run,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
        )
        if updated_snapshot is None:
            return None
        try:
            set_snapshot(updated_snapshot)
        except Exception as exc:
            self._revert_resume_request(
                run=run,
                resume_attempt_id=resume_attempt_id,
                existing_snapshot=existing_snapshot,
                updated_snapshot=updated_snapshot,
            )
            log_event(
                logger,
                logging.ERROR,
                "resume_snapshot_update_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return error_response(
                code="SNAPSHOT_UNAVAILABLE",
                message="Unable to activate the resume attempt. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return None

    def _touch_resume_liveness(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        selected_engine_id: str,
    ) -> Run:
        with transaction.atomic():
            run = Run.objects.select_for_update().get(id=run.id)
            update_fields = touch_run_liveness(
                run,
                event_time=resume_requested_at,
                recovery_state=recovery_state_for_status("resume_requested"),
                engine_instance_id=selected_engine_id,
            )
            if update_fields:
                run.save(update_fields=sorted(set(update_fields)))
            return run

    def _resume_completed_response(
        self,
        *,
        context: RunResumeRequestContext,
        run: Run,
        decision_status: str,
    ) -> Response:
        response = success_response(
            {
                "resumed": True,
                "run_id": str(run.id),
                "resume_attempt_id": str(context.resume_attempt_id),
                "decision_status": decision_status,
            }
        )
        annotate_response(
            response,
            status="applied",
            idempotency_key=context.submit_id,
            resource_type="run",
            resource_id=str(run.id),
        )
        if context.organization is not None:
            ProcessedDecisionSubmission.objects.filter(
                organization=context.organization,
                submit_id=context.submit_id,
            ).update(
                dispatched_at=timezone.now(),
                response_status=response.status_code,
                response_body=response_body(response),
                status="applied",
            )
        return record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def post(self, request: Request, run_id: UUID) -> Response:
        """Resume a paused run with human decision."""
        resume_context, context_response = self._load_resume_request_context(
            request=request,
            run_id=run_id,
        )
        if context_response is not None:
            return context_response
        assert resume_context is not None
        user = resume_context.user
        run = resume_context.run
        organization = resume_context.organization
        node_id = resume_context.node_id
        input_json = resume_context.input_json
        submit_id = resume_context.submit_id
        decision_request_hash = resume_context.decision_request_hash
        resume_attempt_id = resume_context.resume_attempt_id
        log_event(
            logger,
            logging.INFO,
            "runs_resume_requested",
            run_id=str(run.id),
            trace_id=run.trace_id or None,
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            message="Received run resume request",
        )

        pending_approval_task = run.approval_tasks.filter(node_id=node_id, status="pending").first()
        preflight_response = self._resume_preflight_response(
            context=resume_context,
            pending_approval_task=pending_approval_task,
        )
        if preflight_response is not None:
            return preflight_response

        resume_requested_at = timezone.now()
        trace_context = self._resume_trace_context(request=request, run=run)
        engine_input_json, engine_input_response = self._resume_engine_input(
            run=run,
            user=user,
            input_json=input_json,
        )
        if engine_input_response is not None:
            return engine_input_response
        assert engine_input_json is not None

        activation_response = self._activate_resume_attempt(
            run=run,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
            trace_context=trace_context,
        )
        if activation_response is not None:
            return activation_response

        decision_status = "accepted" if bool(input_json.get("approved", True)) else "rejected"
        run, decision_resolved_payload = self._record_resume_decision(
            run=run,
            user=user,
            organization=organization,
            pending_approval_task=pending_approval_task,
            node_id=node_id,
            input_json=input_json,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
            decision_status=decision_status,
            trace_id=trace_context["trace_id"],
        )

        broadcast_run_updated(run)
        if decision_resolved_payload is not None:
            broadcast_decision_resolved(run=run, payload=decision_resolved_payload)

        run, selected_engine_id, dispatch_error = self._dispatch_resume_to_engine(
            run=run,
            node_id=node_id,
            engine_input_json=engine_input_json,
            resume_attempt_id=resume_attempt_id,
            trace_context=trace_context,
        )
        if dispatch_error is not None:
            return dispatch_error

        run = self._touch_resume_liveness(
            run=run,
            resume_requested_at=resume_requested_at,
            selected_engine_id=selected_engine_id,
        )
        broadcast_run_updated(run)

        log_event(
            logger,
            logging.INFO,
            "runs_resume_completed",
            run_id=str(run.id),
            trace_id=run.trace_id or trace_context["trace_id"],
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            message="Run resume request completed",
        )
        return self._resume_completed_response(
            context=resume_context,
            run=run,
            decision_status=decision_status,
        )

    def _load_resume_decision_submission(
        self,
        *,
        run: Run,
        organization: Organization | None,
        submit_id: str,
        decision_request_hash: str,
    ) -> tuple[ProcessedDecisionSubmission | None, Response | None]:
        if organization is None:
            return None, None

        decision_submission = ProcessedDecisionSubmission.objects.filter(
            organization=organization,
            submit_id=submit_id,
        ).first()
        if decision_submission is None:
            return None, None
        if decision_submission.request_hash != decision_request_hash:
            record_idempotency_observation(
                boundary="human_decision",
                status="rejected",
                idempotency_key=submit_id,
                resource_type="run",
                organization_id=organization.id,
                run_id=run.id,
            )
            return decision_submission, error_response(
                code="IDEMPOTENCY_CONFLICT",
                message="Decision submit id was already used with a different payload.",
                status=status.HTTP_409_CONFLICT,
                details=[{"submit_id": submit_id}],
            )
        replayed_decision = _processed_decision_replay_response(
            decision_submission,
            submit_id=submit_id,
        )
        return decision_submission, replayed_decision

    def _resolved_approval_response(
        self,
        *,
        run: Run,
        node_id: str,
        input_json: dict[str, Any],
        submit_id: str,
        decision_submission: ProcessedDecisionSubmission | None,
        command_context: Any,
    ) -> Response | None:
        resolved_task = (
            run.approval_tasks.filter(node_id=node_id)
            .exclude(status="pending")
            .order_by("-resolved_at", "-created_at")
            .first()
        )
        if resolved_task is None:
            return None
        if resolved_task.result != input_json:
            return error_response(
                code="DECISION_CONFLICT",
                message="Approval task for this node has already been resolved differently.",
                status=status.HTTP_409_CONFLICT,
                details=[
                    {
                        "field": "input_json",
                        "issue": "Conflicting decision does not match the recorded result.",
                    }
                ],
            )

        response = success_response(
            {
                "resumed": True,
                "run_id": str(run.id),
                "duplicate": True,
                "decision_status": resolved_task.status,
            }
        )
        annotate_response(
            response,
            status="already_applied",
            idempotency_key=submit_id,
            resource_type="run",
            resource_id=str(run.id),
        )
        if decision_submission is not None and not decision_submission.response_body:
            decision_submission.response_status = response.status_code
            decision_submission.response_body = response_body(response)
            decision_submission.status = "applied"
            decision_submission.save(
                update_fields=["response_status", "response_body", "status", "updated_at"]
            )
        return record_processed_command(
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def _mark_resume_requested(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> None:
        with transaction.atomic():
            transition = apply_run_status_transition(run, "resume_requested")
            run.resume_requested_at = resume_requested_at
            run.resume_attempt_id = resume_attempt_id
            update_fields = transition.update_fields + [
                "resume_requested_at",
                "resume_attempt_id",
            ]
            update_fields.extend(
                touch_run_liveness(
                    run,
                    event_time=resume_requested_at,
                    recovery_state=recovery_state_for_status("resume_requested"),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _revert_resume_request(
        self,
        *,
        run: Run,
        resume_attempt_id: UUID,
        existing_snapshot: RunSnapshot | None,
        updated_snapshot: RunSnapshot | None,
    ) -> None:
        with transaction.atomic():
            refreshed_run = Run.objects.select_for_update().get(id=run.id)
            if (
                refreshed_run.status == "resume_requested"
                and refreshed_run.resume_attempt_id == resume_attempt_id
            ):
                transition = apply_run_status_transition(refreshed_run, "paused")
                refreshed_run.resume_requested_at = None
                refreshed_run.resume_attempt_id = None
                revert_fields = transition.update_fields + [
                    "resume_requested_at",
                    "resume_attempt_id",
                ]
                revert_fields.extend(
                    touch_run_liveness(
                        refreshed_run,
                        event_time=timezone.now(),
                        recovery_state=recovery_state_for_status("paused"),
                    )
                )
                refreshed_run.save(update_fields=sorted(set(revert_fields)))
        if existing_snapshot is not None:
            safe_set_snapshot(existing_snapshot)
        elif updated_snapshot is not None:
            safe_delete_snapshot(run.id)

    def _record_resume_decision(
        self,
        *,
        run: Run,
        user: User,
        organization: Organization | None,
        pending_approval_task: ApprovalTask | None,
        node_id: str,
        input_json: dict[str, Any],
        submit_id: str,
        decision_request_hash: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        decision_status: str,
        trace_id: str,
    ) -> tuple[Run, dict[str, Any] | None]:
        with transaction.atomic():
            run = Run.objects.select_for_update().get(id=run.id)
            update_fields = touch_run_liveness(
                run,
                event_time=resume_requested_at,
                recovery_state=recovery_state_for_status("resume_requested"),
            )
            if update_fields:
                run.save(update_fields=sorted(set(update_fields)))
            self._record_resume_requested_event(
                run=run,
                user=user,
                node_id=node_id,
                resume_requested_at=resume_requested_at,
                resume_attempt_id=resume_attempt_id,
                decision_status=decision_status,
                trace_id=trace_id,
            )
            decision_resolved_payload = self._resolve_pending_approval(
                run=run,
                user=user,
                approval_task=pending_approval_task,
                node_id=node_id,
                input_json=input_json,
                resume_requested_at=resume_requested_at,
                resume_attempt_id=resume_attempt_id,
            )
            self._record_processed_resume_decision(
                run=run,
                organization=organization,
                approval_task=pending_approval_task,
                submit_id=submit_id,
                decision_request_hash=decision_request_hash,
                resume_attempt_id=resume_attempt_id,
            )
            return run, decision_resolved_payload

    def _record_resume_requested_event(
        self,
        *,
        run: Run,
        user: User,
        node_id: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        decision_status: str,
        trace_id: str,
    ) -> None:
        RunEvent.objects.create(
            run=run,
            event_type="run.resume_requested",
            payload={
                "status": "resume_requested",
                "node_id": node_id,
                "resume_requested_at": resume_requested_at.isoformat(),
                "resume_attempt_id": str(resume_attempt_id),
                "decision_status": decision_status,
                "category": "state",
            },
            trace_id=run.trace_id or trace_id,
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_run(run),
            action="run.resume_requested",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "node_id": node_id,
                "resume_attempt_id": str(resume_attempt_id),
                "decision_status": decision_status,
            },
        )
        _project_run_event_state(
            run=run,
            projection_status="resume_requested",
            trace_id=run.trace_id or trace_id,
            event_type="run.resume_requested",
            event_id=None,
            event_time=resume_requested_at,
            pause_state_json=run.pause_state_json,
            paused_node_id=run.paused_node_id,
        )

    def _resolve_pending_approval(
        self,
        *,
        run: Run,
        user: User,
        approval_task: ApprovalTask | None,
        node_id: str,
        input_json: dict[str, Any],
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> dict[str, Any] | None:
        if approval_task is None:
            return None
        approved = bool(input_json.get("approved", True))
        lifecycle_task = approval_task.task_lifecycle
        if lifecycle_task is None:
            lifecycle_task = transition_task_lifecycle(
                run=run,
                node_id=node_id,
                node_type="human_gate",
                to_status="waiting_for_decision",
                attempt_number=1,
                source="hitl_resume",
                idempotency_key=f"task:{run.id}:{node_id}:decision_link:{approval_task.id}",
                reason="approval task linked to lifecycle task",
            ).lifecycle_task
        approval_task.status = "approved" if approved else "rejected"
        approval_task.result = input_json
        approval_task.resolved_at = resume_requested_at
        approval_task.task_lifecycle = lifecycle_task
        approval_task.save(update_fields=["status", "result", "resolved_at", "task_lifecycle"])
        self._record_approval_decision(
            run=run,
            user=user,
            approval_task=approval_task,
            lifecycle_task=lifecycle_task,
            input_json=input_json,
            node_id=node_id,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
        )
        return {
            "node_id": node_id,
            "status": approval_task.status,
            "resolution": redact_payload(input_json),
            "resume_attempt_id": str(resume_attempt_id),
        }

    def _record_approval_decision(
        self,
        *,
        run: Run,
        user: User,
        approval_task: ApprovalTask,
        lifecycle_task: Any,
        input_json: dict[str, Any],
        node_id: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> None:
        organization = run.organization if run.organization_id else user.default_organization
        if organization is not None:
            decision_record, _ = DecisionRecord.objects.update_or_create(
                organization=organization,
                external_key=f"approval:{approval_task.id}",
                defaults={
                    "execution": run,
                    "task": None,
                    "task_lifecycle": lifecycle_task,
                    "agent": None,
                    "decision_type": "human_approval",
                    "status": approval_task.status,
                    "source_approval_task": approval_task,
                    "context_json": approval_task.payload
                    if isinstance(approval_task.payload, dict)
                    else {},
                    "resolution_json": input_json,
                    "requested_at": approval_task.created_at,
                    "resolved_at": resume_requested_at,
                },
            )
            lifecycle_task.current_decision = decision_record
            lifecycle_task.save(update_fields=["current_decision", "updated_at"])
        PreferenceEventService().record_hitl_feedback(
            approval_task=approval_task,
            actor=user,
            final_value=input_json,
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="approval.resolved",
            resource_type="approval",
            resource_id=str(approval_task.id),
            metadata={
                "run_id": str(run.id),
                "node_id": node_id,
                "status": approval_task.status,
                "resume_attempt_id": str(resume_attempt_id),
            },
        )

    def _record_processed_resume_decision(
        self,
        *,
        run: Run,
        organization: Organization | None,
        approval_task: ApprovalTask | None,
        submit_id: str,
        decision_request_hash: str,
        resume_attempt_id: UUID,
    ) -> None:
        if organization is None:
            return
        ProcessedDecisionSubmission.objects.update_or_create(
            organization=organization,
            submit_id=submit_id,
            defaults={
                "run": run,
                "approval_task": approval_task,
                "request_hash": decision_request_hash,
                "resume_attempt_id": resume_attempt_id,
                "status": "applied",
            },
        )
        record_idempotency_observation(
            boundary="human_decision",
            status="applied",
            idempotency_key=submit_id,
            resource_type="run",
            organization_id=organization.id,
            run_id=run.id,
        )

    def _mark_resume_dispatch_failed(
        self,
        *,
        run: Run,
        node_id: str,
        resume_attempt_id: UUID,
        trace_id: str,
        reason: str,
        error_message: str,
    ) -> Run:
        failure_time = timezone.now()
        with transaction.atomic():
            failed_run = Run.objects.select_for_update().get(id=run.id)
            if (
                failed_run.status == "resume_requested"
                and failed_run.resume_attempt_id == resume_attempt_id
            ):
                failed_run.recovery_state = "resume_dispatch_failed"
                failed_run.recovery_reason = reason[:64]
                update_fields = ["recovery_state", "recovery_reason"]
                update_fields.extend(
                    touch_run_liveness(
                        failed_run,
                        event_time=failure_time,
                        recovery_state="resume_dispatch_failed",
                    )
                )
                failed_run.save(update_fields=sorted(set(update_fields)))
                RunEvent.objects.create(
                    run=failed_run,
                    event_type="run.resume_dispatch_failed",
                    payload={
                        "status": "resume_requested",
                        "recovery_state": "resume_dispatch_failed",
                        "recovery_reason": reason,
                        "error_message": redact_payload(error_message),
                        "resume_attempt_id": str(resume_attempt_id),
                        "node_id": node_id,
                        "category": "state",
                    },
                    trace_id=failed_run.trace_id or trace_id,
                )
                _project_run_event_state(
                    run=failed_run,
                    projection_status="resume_requested",
                    trace_id=failed_run.trace_id or trace_id,
                    event_type="run.resume_dispatch_failed",
                    event_id=None,
                    event_time=failure_time,
                    pause_state_json=failed_run.pause_state_json,
                    paused_node_id=failed_run.paused_node_id,
                )
            return failed_run

    def _dispatch_resume_to_engine(
        self,
        *,
        run: Run,
        node_id: str,
        engine_input_json: dict[str, Any],
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> tuple[Run, str, Response | None]:
        try:
            selected_engine_id = self._send_resume_to_engine(
                run=run,
                node_id=node_id,
                engine_input_json=engine_input_json,
                resume_attempt_id=resume_attempt_id,
                trace_context=trace_context,
            )
        except EngineConnectionError as exc:
            failed_run = self._mark_resume_dispatch_failed(
                run=run,
                node_id=node_id,
                resume_attempt_id=resume_attempt_id,
                trace_id=trace_context["trace_id"],
                reason="engine_unavailable",
                error_message=str(exc),
            )
            broadcast_run_updated(failed_run)
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_connection_failed",
                run_id=str(failed_run.id),
                trace_id=failed_run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return (
                failed_run,
                "",
                error_response(
                    code="ENGINE_UNAVAILABLE",
                    message="The execution engine is not available. Please try again later.",
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                ),
            )
        except EngineExecutionError as exc:
            failed_run = self._mark_resume_dispatch_failed(
                run=run,
                node_id=node_id,
                resume_attempt_id=resume_attempt_id,
                trace_id=trace_context["trace_id"],
                reason="engine_rejected_resume",
                error_message=str(exc),
            )
            broadcast_run_updated(failed_run)
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_failed",
                run_id=str(failed_run.id),
                trace_id=failed_run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return (
                failed_run,
                "",
                error_response(
                    code="ENGINE_ERROR",
                    message=str(exc),
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        return run, selected_engine_id, None

    def _send_resume_to_engine(
        self,
        *,
        run: Run,
        node_id: str,
        engine_input_json: dict[str, Any],
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> str:
        with start_backend_span(
            "runs.resume",
            traceparent=trace_context["traceparent"],
            tracestate=trace_context["tracestate"],
            attributes={
                "forgegraph.run_id": str(run.id),
                "forgegraph.node_id": node_id,
                "forgegraph.trigger": "resume",
            },
        ):
            selected_engine_id, engine_client = get_engine_client_for_run(run=run)
            with engine_client as engine:
                engine.resume_run(
                    run_id=run.id,
                    node_id=node_id,
                    input_json=engine_input_json,
                    resume_attempt_id=str(resume_attempt_id),
                    traceparent=trace_context["traceparent"],
                    tracestate=trace_context["tracestate"],
                )
        log_event(
            logger,
            logging.INFO,
            "runs_resume_dispatched",
            run_id=str(run.id),
            trace_id=run.trace_id or trace_context["trace_id"],
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            engine_instance_id=selected_engine_id,
            message="Dispatched run resume to engine",
        )
        return selected_engine_id


class EngineRunEventsView(APIView):
    """Persist + broadcast engine execution events (S2S).

    Events never mutate durable state directly. The backend validates, deduplicates,
    enforces monotonicity/ownership rules, and then performs durable writes.
    """

    permission_classes = [AllowAny]
    throttle_classes: list[type] = []

    def post(self, request: Request) -> Response:
        for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
            try:
                return self._post_once(
                    request,
                    verify_signature=not bool(getattr(request, "_forgegraph_s2s_verified", False)),
                )
            except OperationalError as exc:
                if (
                    not _is_deadlock(exc)
                    or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1
                    or not bool(getattr(request, "_forgegraph_s2s_verified", False))
                ):
                    raise
                time.sleep(0.02 * (attempt + 1))
        raise RuntimeError("unreachable engine callback retry state")

    def _save_engine_callback_event(
        self,
        context: EngineCallbackContext,
        event_type_name: str,
        payload: dict[str, Any],
        *,
        derived: bool = False,
    ) -> bool:
        normalized_payload = dict(payload)
        normalized_payload["category"] = normalize_event_category(
            event_type_name,
            category=str(normalized_payload.get("category") or ""),
            payload=normalized_payload,
        )
        try:
            RunEvent.objects.create(
                run=context.run,
                event_type=event_type_name,
                payload=normalized_payload,
                external_id=None if derived else context.event_id,
                trace_id=context.trace_context["trace_id"],
                span_id=context.trace_context["span_id"],
            )
            if not derived and context.event_id and context.callback_organization_id:
                ProcessedCallbackEvent.objects.update_or_create(
                    run=context.run,
                    event_id=str(context.event_id),
                    defaults={
                        "organization_id": context.callback_organization_id,
                        "idempotency_key": context.callback_idempotency_key,
                        "event_type": event_type_name,
                        "request_hash": context.callback_request_hash,
                        "resource_type": "run",
                        "resource_id": str(context.run.id),
                        "status": "applied",
                    },
                )
                record_idempotency_observation(
                    boundary="engine_callback",
                    status="applied",
                    idempotency_key=str(context.event_id),
                    resource_type="run",
                    organization_id=context.callback_organization_id,
                    run_id=context.run.id,
                )
            return True
        except IntegrityError:
            log_event(
                logger,
                logging.INFO,
                "duplicate_run_event_ignored",
                run_id=str(context.run.id),
                trace_id=context.trace_context["trace_id"],
                event_id=context.event_id,
                message="Duplicate run event ignored",
            )
            return False

    def _engine_callback_context_success(
        self,
        context: EngineCallbackContext,
        data: dict[str, Any] | None = None,
        *,
        decision: str = "accepted",
        reason: str = "accepted",
        backend_event_id: str = "",
        safe_to_discard: bool = True,
        conflict_code: str = "",
        idempotency_status: IdempotencyStatus = "applied",
    ) -> Response:
        response = _engine_callback_success(
            data,
            decision=decision,
            reason=reason,
            backend_event_id=backend_event_id,
            safe_to_discard=safe_to_discard,
            conflict_code=conflict_code,
        )
        if not context.event_id:
            return response

        annotate_response(
            response,
            status=idempotency_status,
            idempotency_key=str(context.event_id),
            resource_type="run",
            resource_id=str(context.run.id),
        )
        if context.callback_organization_id:
            ProcessedCallbackEvent.objects.update_or_create(
                run=context.run,
                event_id=str(context.event_id),
                defaults={
                    "organization_id": context.callback_organization_id,
                    "idempotency_key": context.callback_idempotency_key,
                    "event_type": str(context.event_type or ""),
                    "request_hash": context.callback_request_hash,
                    "response_status": response.status_code,
                    "response_body": response_body(response),
                    "resource_type": "run",
                    "resource_id": str(context.run.id),
                    "status": "applied",
                },
            )
        return response

    def _verify_engine_callback_signature(
        self,
        request: Request,
        *,
        verify_signature: bool,
    ) -> Response | None:
        if not verify_signature:
            return None
        ok, reason = s2s.verify_request_once(
            timestamp_ms=request.headers.get("X-Forgegraph-Timestamp", ""),
            signature=request.headers.get("X-Forgegraph-Signature", ""),
            body=request.body or b"",
            method=request.method or "",
            path=request.path,
        )
        if ok:
            cast(Any, request)._forgegraph_s2s_verified = True
            return None
        record_callback_auth_failure(reason)
        _record_engine_callback_dead_letter(
            event={"path": request.path, "body_size": len(request.body or b"")},
            reason="engine callback authentication failed",
            error_class="engine_callback_auth_failed",
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-unauthorized",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Engine callback verification failed: {reason}",
            decision="reject_invalid",
            reason="engine callback authentication failed",
            safe_to_discard=False,
        )

    def _parse_engine_callback_event(
        self,
        request: Request,
    ) -> tuple[dict[str, Any] | None, Response | None]:
        try:
            parsed_event = parse_engine_event_payload(
                request.data,
                allow_legacy=bool(
                    getattr(settings, "ENGINE_LEGACY_EVENT_CALLBACKS_ENABLED", False)
                ),
            )
        except CanonicalEventValidationError as exc:
            payload = request.data if isinstance(request.data, dict) else {}
            _record_engine_callback_dead_letter(
                event=payload,
                reason="invalid canonical engine event envelope",
                error_class="canonical_event_validation",
                event_id=str(payload.get("event_id") or ""),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                event_type=str(payload.get("type") or ""),
            )
            return None, _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/canonical-engine-event-validation",
                title="Invalid canonical engine event envelope",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
                decision="reject_invalid",
                reason="invalid canonical engine event envelope",
                backend_event_id=str(payload.get("event_id") or ""),
                safe_to_discard=True,
            )

        incoming_payload = parsed_event.event
        serializer = EngineExecutionEventSerializer(data=incoming_payload)
        if serializer.is_valid():
            return serializer.validated_data, None
        _record_engine_callback_dead_letter(
            event=incoming_payload if isinstance(incoming_payload, dict) else {},
            reason="invalid engine callback schema",
            error_class="engine_callback_validation",
        )
        return None, _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-validation",
            title="Invalid engine callback payload",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The request contains invalid fields.",
            decision="reject_invalid",
            reason="invalid engine callback schema",
            safe_to_discard=True,
            extensions={
                "errors": [
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ]
            },
        )

    def _load_engine_callback_run(
        self,
        event: dict[str, Any],
    ) -> tuple[Run | None, Response | None]:
        run_id = event.get("run_id")
        try:
            return Run.objects.get(id=cast(UUID | str, run_id)), None
        except Run.DoesNotExist:
            _record_engine_callback_dead_letter(
                event=event,
                reason="backend cannot prove the run is tombstoned",
                error_class="run_not_found",
            )
            return None, _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/run-not-found",
                title="Run not found",
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run with id '{run_id}' not found.",
                decision="retry_required",
                reason="backend cannot prove the run is tombstoned",
                safe_to_discard=False,
                conflict_code="404_UNKNOWN_ENTITY",
            )

    def _engine_callback_trace_context(
        self,
        *,
        request: Request,
        event: dict[str, Any],
        run: Run,
    ) -> dict[str, str]:
        traceparent = str(
            event.get("traceparent")
            or request.headers.get("traceparent")
            or request.headers.get("Traceparent")
            or ""
        ).strip()
        tracestate = str(
            event.get("tracestate")
            or request.headers.get("tracestate")
            or request.headers.get("Tracestate")
            or ""
        ).strip()
        return ensure_trace_context(
            traceparent=traceparent or None,
            tracestate=tracestate or None,
            trace_id=run.trace_id or None,
        )

    def _engine_callback_tenant_response(
        self,
        *,
        event: dict[str, Any],
        run: Run,
    ) -> Response | None:
        tenant_id = str(event.get("tenant_id"))
        if tenant_id == get_tenant_id_for_run(run):
            return None
        _record_engine_callback_dead_letter(
            event=event,
            run=run,
            reason="tenant mismatch for run event",
            error_class="tenant_mismatch",
            event_id=str(event.get("event_id") or ""),
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/tenant-mismatch",
            title="Tenant mismatch",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch for run event.",
            decision="reject_invalid",
            reason="tenant mismatch for run event",
            backend_event_id=str(event.get("event_id") or ""),
            safe_to_discard=False,
        )

    def _engine_callback_duplicate_response(
        self,
        *,
        run: Run,
        event_id: Any,
        callback_request_hash: str,
    ) -> Response | None:
        if not event_id or not RunEvent.objects.filter(run=run, external_id=event_id).exists():
            return None
        processed_callback = ProcessedCallbackEvent.objects.filter(
            run=run,
            event_id=str(event_id),
        ).first()
        if (
            processed_callback is not None
            and processed_callback.request_hash == callback_request_hash
            and processed_callback.response_body
        ):
            record_idempotency_observation(
                boundary="engine_callback",
                status="already_applied",
                idempotency_key=str(event_id),
                resource_type=processed_callback.resource_type or "run",
                organization_id=processed_callback.organization_id,
                run_id=run.id,
            )
            duplicate_response = annotated_response_from_body(
                processed_callback.response_body,
                response_status=processed_callback.response_status,
                status="already_applied",
                idempotency_key=str(event_id),
                resource_type=processed_callback.resource_type or "run",
                resource_id=processed_callback.resource_id or str(run.id),
            )
            body = duplicate_response.data
            if isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, dict):
                    data["duplicate"] = True
                    data["decision"] = "duplicate"
                    data["reason"] = "event already applied"
                    data["safe_to_discard"] = True
            return duplicate_response

        response = _engine_callback_success(
            {"received": True, "duplicate": True},
            decision="duplicate",
            reason="event already applied",
            backend_event_id=str(event_id),
            safe_to_discard=True,
        )
        annotate_response(
            response,
            status="already_applied",
            idempotency_key=str(event_id),
            resource_type="run",
            resource_id=str(run.id),
        )
        return response

    def _engine_callback_idempotency_conflict_response(
        self,
        *,
        run: Run,
        event_id: Any,
        callback_request_hash: str,
        callback_organization_id: UUID | None,
    ) -> Response | None:
        if not event_id:
            return None
        processed_callback = ProcessedCallbackEvent.objects.filter(
            run=run,
            event_id=str(event_id),
        ).first()
        if processed_callback is None or processed_callback.request_hash == callback_request_hash:
            return None
        record_idempotency_observation(
            boundary="engine_callback",
            status="rejected",
            idempotency_key=str(event_id),
            resource_type="run",
            organization_id=callback_organization_id,
            run_id=run.id,
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-idempotency-conflict",
            title="Engine callback idempotency conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail="Engine callback event_id was already used with a different payload.",
            decision="reject_invalid",
            reason="event idempotency key conflict",
            backend_event_id=str(event_id),
            safe_to_discard=False,
            conflict_code="409_IDEMPOTENCY_CONFLICT",
        )

    def _reconcile_engine_callback_assignment(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: Any,
        event_id: Any,
        trace_context: dict[str, str],
        normalized_category: str,
    ) -> tuple[str, bool, Response | None]:
        try:
            callback_engine_instance_id, assigned_engine = reconcile_run_engine_instance(
                assigned_engine_id=run.engine_instance_id,
                callback_engine_id=str(event.get("engine_instance_id") or ""),
            )
        except EngineAssignmentError as exc:
            log_event(
                logger,
                logging.WARNING,
                "engine_callback_assignment_conflict",
                run_id=str(run.id),
                trace_id=trace_context["trace_id"],
                event_id=event_id,
                message="Rejected engine callback due to engine ownership mismatch",
                assigned_engine_instance_id=run.engine_instance_id or None,
                callback_engine_instance_id=str(event.get("engine_instance_id") or "").strip()
                or None,
                error_detail=str(exc),
                category=normalized_category,
            )
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="engine callback ownership conflict",
                error_class="engine_instance_mismatch",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return (
                "",
                False,
                _engine_callback_problem(
                    type_uri="https://forgegraph.dev/problems/engine-instance-mismatch",
                    title="Engine instance mismatch",
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                    decision="retry_required",
                    reason="engine callback ownership conflict",
                    backend_event_id=str(event_id or ""),
                    safe_to_discard=False,
                    conflict_code="409_ORDERING_CONFLICT",
                ),
            )
        return callback_engine_instance_id, assigned_engine, None

    def _adopt_engine_callback_assignment(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: Any,
        event_id: Any,
        callback_engine_instance_id: str,
        assigned_engine: bool,
        normalized_category: str,
    ) -> Response | None:
        raw_callback_engine_instance_id = str(event.get("engine_instance_id") or "").strip()
        if not (assigned_engine and callback_engine_instance_id != run.engine_instance_id):
            return None
        if not raw_callback_engine_instance_id:
            return None
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=event,
            )
        except EventSafetyViolation as exc:
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="event safety violation",
                error_class="event_safety_violation",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="reject_invalid",
                reason="event safety violation",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
                conflict_code="409_EVENT_SAFETY_VIOLATION",
            )
        run.engine_instance_id = callback_engine_instance_id
        run.save(update_fields=["engine_instance_id"])
        return None

    def _dispatch_engine_callback_event(self, context: EngineCallbackContext) -> Response:
        event_type = context.event_type
        if event_type == "run.schema_validation":
            return self._handle_engine_schema_validation_event(context)
        if event_type == "node_stream_chunk":
            return self._handle_engine_stream_chunk_event(context)
        if event_type in {
            "memory_write_requested",
            "memory_fact_extracted",
            "summary_created",
            "memory.write_requested",
            "memory.fact_extracted",
            "summary.created",
        }:
            return self._handle_engine_memory_intent_event(context)
        if event_type in {
            "run_started",
            "run_completed",
            "run_failed",
            "run_paused",
            "run_resumed",
            "run_canceled",
        }:
            return self._handle_engine_run_lifecycle_event(context)
        if event_type in {
            "node_started",
            "node_completed",
            "node_failed",
            "node_skipped",
            "node_retrying",
        }:
            return self._handle_engine_node_lifecycle_event(context)

        _record_engine_callback_dead_letter(
            event=context.event,
            run=context.run,
            reason="unknown engine event type",
            error_class="unknown_engine_event",
            event_id=str(context.event_id or ""),
            event_type=str(event_type or ""),
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/unknown-engine-event",
            title="Unknown engine event",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown event type.",
            decision="reject_invalid",
            reason="unknown engine event type",
            backend_event_id=str(context.event_id or ""),
            safe_to_discard=True,
        )

    def _post_once(self, request: Request, *, verify_signature: bool) -> Response:
        signature_response = self._verify_engine_callback_signature(
            request,
            verify_signature=verify_signature,
        )
        if signature_response is not None:
            return signature_response

        event, parse_response = self._parse_engine_callback_event(request)
        if parse_response is not None:
            return parse_response
        assert event is not None

        run, load_response = self._load_engine_callback_run(event)
        if load_response is not None:
            return load_response
        assert run is not None

        trace_context = self._engine_callback_trace_context(
            request=request,
            event=event,
            run=run,
        )
        tenant_response = self._engine_callback_tenant_response(event=event, run=run)
        if tenant_response is not None:
            return tenant_response

        event_id = event.get("event_id")
        callback_organization_id = run.organization_id or run.owner.default_organization_id
        callback_idempotency_key = normalize_idempotency_key(
            event.get("idempotency_key") or event_id,
        )
        callback_request_hash = hash_request_payload(event)
        duplicate_response = self._engine_callback_duplicate_response(
            run=run,
            event_id=event_id,
            callback_request_hash=callback_request_hash,
        )
        if duplicate_response is not None:
            return duplicate_response
        conflict_response = self._engine_callback_idempotency_conflict_response(
            run=run,
            event_id=event_id,
            callback_request_hash=callback_request_hash,
            callback_organization_id=callback_organization_id,
        )
        if conflict_response is not None:
            return conflict_response
        event_type = event.get("type", "")
        timestamp_ms = event.get("timestamp")
        event_time = _datetime_from_timestamp_ms(timestamp_ms)
        normalized_category = normalize_event_category(
            str(event_type),
            category=str(event.get("category") or ""),
        )
        state_mutation_enabled = bool(
            getattr(settings, "ENGINE_EVENT_STATE_MUTATION_ENABLED", False)
        )
        stale_attempt_response = _ignore_stale_engine_attempt(
            run=run,
            event_type=event_type,
            event=event,
            event_id=str(event_id or ""),
            trace_id=trace_context["trace_id"],
            normalized_category=normalized_category,
        )
        if stale_attempt_response is not None:
            return stale_attempt_response

        callback_engine_instance_id, assigned_engine, assignment_response = (
            self._reconcile_engine_callback_assignment(
                run=run,
                event=event,
                event_type=event_type,
                event_id=event_id,
                trace_context=trace_context,
                normalized_category=normalized_category,
            )
        )
        if assignment_response is not None:
            return assignment_response
        adoption_response = self._adopt_engine_callback_assignment(
            run=run,
            event=event,
            event_type=event_type,
            event_id=event_id,
            callback_engine_instance_id=callback_engine_instance_id,
            assigned_engine=assigned_engine,
            normalized_category=normalized_category,
        )
        if adoption_response is not None:
            return adoption_response

        context = EngineCallbackContext(
            run=run,
            event=event,
            event_type=str(event_type),
            event_id=event_id,
            event_time=event_time,
            trace_context=trace_context,
            normalized_category=normalized_category,
            state_mutation_enabled=state_mutation_enabled,
            callback_engine_instance_id=callback_engine_instance_id,
            callback_organization_id=callback_organization_id,
            callback_idempotency_key=callback_idempotency_key,
            callback_request_hash=callback_request_hash,
        )

        return self._dispatch_engine_callback_event(context)

    def _handle_engine_schema_validation_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_id = context.event_id
        payload = redact_payload(event.get("output") or {})
        self._save_engine_callback_event(context, "run.schema_validation", payload)
        message = broadcast_run_schema_validation(run=run, payload=payload)
        return self._engine_callback_context_success(
            context,
            message,
            reason="schema validation event accepted",
            backend_event_id=str(event_id or ""),
        )

    def _handle_engine_stream_chunk_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_id = context.event_id
        event_time = context.event_time
        output = event.get("output")
        payload = output if isinstance(output, dict) else {}
        chunk = str(redact_payload(payload.get("chunk") or ""))
        chunk_index = int(payload.get("chunk_index") or 0)
        stream_node_id = str(event.get("node_id") or "")
        stream_node_type = str(event.get("node_type") or "")
        stream_attempt = int(cast(int | str, event.get("attempt") or 1))
        stream_payload = {
            "node_id": stream_node_id,
            "node_type": stream_node_type,
            "attempt": stream_attempt,
            "chunk": chunk,
            "chunk_index": chunk_index,
        }
        agent_chunk = _parse_agent_stream_chunk(chunk)
        if agent_chunk:
            normalized_agent_event = _normalize_agent_stream_event(
                node_id=stream_node_id,
                node_type=stream_node_type,
                attempt=stream_attempt,
                chunk_index=chunk_index,
                payload=agent_chunk,
            )
            stream_payload["agent_event"] = normalized_agent_event
        self._save_engine_callback_event(context, "node_stream.chunk", stream_payload)
        if agent_chunk:
            self._save_engine_callback_event(
                context,
                str(agent_chunk.get("event") or "agent.unknown"),
                cast(dict[str, Any], stream_payload["agent_event"]),
                derived=True,
            )
        summary_payload = update_stream_summary(
            run_id=str(run.id),
            payload=stream_payload,
            event_time=event_time,
        )
        if summary_payload:
            broadcast_node_stream_summary(run=run, payload=summary_payload)
        message = broadcast_node_stream_chunk(run=run, payload=stream_payload)
        return self._engine_callback_context_success(
            context,
            message,
            reason="stream chunk event accepted",
            backend_event_id=str(event_id or ""),
        )

    def _handle_engine_memory_intent_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_type = context.event_type
        event_id = context.event_id
        memory_payload = _memory_intent_payload_from_event(event)
        try:
            memory_result = BackendMemoryIntentService().apply_engine_memory_intent(
                run=run,
                event_type=str(event_type),
                payload=memory_payload,
                event_id=str(event_id or ""),
            )
        except ValueError as exc:
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="invalid backend memory intent",
                error_class="memory_intent_validation",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/memory-intent-validation",
                title="Invalid memory intent",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
                decision="reject_invalid",
                reason="invalid backend memory intent",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
            )
        if not self._save_engine_callback_event(
            context, event_type, _serialize_event_payload(redact_payload(memory_payload))
        ):
            return self._engine_callback_context_success(
                context,
                {"received": True, "duplicate": True},
                decision="duplicate",
                reason="event already applied",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
                idempotency_status="already_applied",
            )
        record_audit_log(
            actor=None,
            tenant_id=get_tenant_id_for_run(run),
            action=f"memory.{event_type}",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "event_id": event_id,
                "event_type": event_type,
                "source": "engine_callback",
                "backend_owner": "memory_service",
                "observation_count": memory_result.observation_count,
            },
        )
        return self._engine_callback_context_success(
            context,
            {
                "received": True,
                "event_type": event_type,
                "authoritative_state_updated": True,
                "memory_owner": "backend",
                "memory_observation_count": memory_result.observation_count,
            },
            reason="backend memory intent event accepted",
            backend_event_id=str(event_id or ""),
        )

    def _run_started_duplicate_response(
        self, context: EngineCallbackContext, current_status: str
    ) -> Response | None:
        if context.event_type != "run_started" or current_status == "pending":
            return None
        return self._engine_callback_context_success(
            context,
            {
                "received": True,
                "duplicate": True,
                "current_status": current_status,
            },
            decision="duplicate",
            reason="run_started was already superseded by backend state",
            backend_event_id=str(context.event_id or ""),
            safe_to_discard=True,
            idempotency_status="already_applied",
        )

    def _runtime_safety_response(
        self, context: EngineCallbackContext, *, reason: str = "event safety violation"
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                context.event_type,
                category=context.normalized_category,
                payload=context.event,
            )
        except EventSafetyViolation as exc:
            _record_engine_callback_dead_letter(
                event=context.event,
                run=context.run,
                reason=reason,
                error_class="event_safety_violation",
                event_id=str(context.event_id or ""),
                event_type=str(context.event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="reject_invalid",
                reason=reason,
                backend_event_id=str(context.event_id or ""),
                safe_to_discard=True,
                conflict_code="409_EVENT_SAFETY_VIOLATION",
            )
        return None

    def _run_transition_conflict_response(
        self,
        context: EngineCallbackContext,
        *,
        current_status: str,
    ) -> Response | None:
        try:
            _validate_run_event_transition(
                current_status=current_status,
                event_type=context.event_type,
            )
        except ValueError as exc:
            _record_engine_callback_dead_letter(
                event=context.event,
                run=context.run,
                reason="run state ordering conflict",
                error_class="run_state_ordering_conflict",
                event_id=str(context.event_id or ""),
                event_type=str(context.event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/invalid-run-transition",
                title="Invalid run transition",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="retry_required",
                reason="run state ordering conflict",
                backend_event_id=str(context.event_id or ""),
                safe_to_discard=False,
                conflict_code="409_ORDERING_CONFLICT",
            )
        return None

    def _run_lifecycle_preflight_response(
        self,
        context: EngineCallbackContext,
        *,
        current_status: str,
        check_safety: bool,
    ) -> Response | None:
        duplicate_response = self._run_started_duplicate_response(context, current_status)
        if duplicate_response is not None:
            return duplicate_response
        if check_safety:
            safety_response = self._runtime_safety_response(context)
            if safety_response is not None:
                return safety_response
        return self._run_transition_conflict_response(context, current_status=current_status)

    def _record_run_lifecycle_metrics(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
        previous_status: str,
    ) -> None:
        if context.event_type == "run_started" and previous_status != "running":
            record_run_started()
        if context.event_type in {
            "run_completed",
            "run_failed",
            "run_canceled",
        } and previous_status not in {
            "succeeded",
            "failed",
            "canceled",
        }:
            record_run_completed(run.status, run.duration_ms)
        if context.state_mutation_enabled and context.event_type == "run_completed":
            _schedule_deliverable_archive(run.id)

    def _empty_run_lifecycle_mutation(self) -> RunLifecycleMutation:
        return RunLifecycleMutation(
            run_payload={},
            update_fields=[],
            pause_payload={},
            node_id="",
            projection_kwargs={},
        )

    def _run_started_lifecycle_mutation(
        self,
        *,
        run: Run,
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "running"}
        update_fields = apply_run_status_transition(run, "running").update_fields
        if event_time:
            run_payload["started_at"] = event_time
            run.started_at = event_time
            update_fields.append("started_at")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"started_at": event_time},
        )

    def _run_completed_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "succeeded"}
        update_fields = apply_run_status_transition(run, "succeeded").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        if "output" in event:
            redacted_output = redact_payload(event.get("output"))
            run_payload["output_json"] = redacted_output
            run.output_json = redacted_output
            update_fields.append("output_json")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={
                "ended_at": event_time,
                "output_json": run_payload.get("output_json", _UNSET),
            },
        )

    def _run_failed_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        error_message = redact_payload(event.get("error") or "")
        run_payload: dict[str, Any] = {
            "status": "failed",
            "error_message": error_message,
        }
        update_fields = apply_run_status_transition(run, "failed").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        run.error_message = error_message
        update_fields.append("error_message")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"ended_at": event_time, "error_message": error_message},
        )

    def _run_canceled_lifecycle_mutation(
        self,
        *,
        run: Run,
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "canceled"}
        update_fields = apply_run_status_transition(run, "canceled").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"ended_at": event_time},
        )

    def _run_paused_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
    ) -> RunLifecycleMutation:
        node_id = str(event.get("node_id") or "")
        run_payload: dict[str, Any] = {"status": "paused"}
        update_fields = apply_run_status_transition(run, "paused").update_fields
        if node_id:
            run_payload["paused_node_id"] = node_id
            run.paused_node_id = node_id
            update_fields.append("paused_node_id")
        raw_pause_payload = redact_payload(event.get("output") or {})
        pause_payload = raw_pause_payload if isinstance(raw_pause_payload, dict) else {}
        run_payload["pause_payload"] = pause_payload
        persisted_pause_state = redact_payload(run.pause_state_json)
        if persisted_pause_state is not None:
            run_payload["pause_state_json"] = persisted_pause_state
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload=pause_payload,
            node_id=node_id,
            projection_kwargs={
                "paused_node_id": node_id or None,
                "pause_state_json": (
                    persisted_pause_state if persisted_pause_state is not None else _UNSET
                ),
            },
        )

    def _run_resumed_lifecycle_mutation(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
    ) -> RunLifecycleMutation:
        event = context.event
        event_output = event.get("output")
        resume_output = event_output if isinstance(event_output, dict) else {}
        resume_attempt_id = str(
            resume_output.get("resume_attempt_id") or event.get("attempt_id") or ""
        ).strip()
        expected_resume_attempt_id = str(
            run.resume_attempt_id or run.authoritative_attempt_id or ""
        ).strip()
        if not resume_attempt_id or (
            expected_resume_attempt_id and resume_attempt_id != expected_resume_attempt_id
        ):
            return RunLifecycleMutation(
                run_payload={},
                update_fields=[],
                pause_payload={},
                node_id="",
                projection_kwargs={},
                error_response=_engine_callback_problem(
                    type_uri="https://forgegraph.dev/problems/stale-resume-acknowledgement",
                    title="Stale resume acknowledgement",
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "run_resumed acknowledgement does not match the active resume_attempt_id."
                    ),
                    decision="stale_superseded",
                    reason="resume_attempt_id does not match the active backend resume attempt",
                    backend_event_id=str(context.event_id or ""),
                    safe_to_discard=True,
                    conflict_code="409_STALE_SUPERSEDED",
                ),
            )
        run_payload: dict[str, Any] = {
            "status": "running",
            "paused_node_id": None,
            "pause_state_json": None,
        }
        update_fields = apply_run_status_transition(run, "running").update_fields
        run.paused_node_id = None
        run.pause_state_json = None
        update_fields.extend(["paused_node_id", "pause_state_json"])
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={
                "paused_node_id": None,
                "pause_state_json": None,
            },
        )

    def _run_lifecycle_mutation(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
    ) -> RunLifecycleMutation:
        if context.event_type == "run_started":
            return self._run_started_lifecycle_mutation(run=run, event_time=context.event_time)
        if context.event_type == "run_completed":
            return self._run_completed_lifecycle_mutation(
                run=run,
                event=context.event,
                event_time=context.event_time,
            )
        if context.event_type == "run_failed":
            return self._run_failed_lifecycle_mutation(
                run=run,
                event=context.event,
                event_time=context.event_time,
            )
        if context.event_type == "run_canceled":
            return self._run_canceled_lifecycle_mutation(run=run, event_time=context.event_time)
        if context.event_type == "run_paused":
            return self._run_paused_lifecycle_mutation(run=run, event=context.event)
        if context.event_type == "run_resumed":
            return self._run_resumed_lifecycle_mutation(context=context, run=run)
        return self._empty_run_lifecycle_mutation()

    def _clear_resume_request_fields(
        self,
        *,
        run: Run,
        run_payload: dict[str, Any],
        update_fields: list[str],
    ) -> None:
        if run.resume_requested_at is not None:
            run_payload["resume_requested_at"] = None
            run.resume_requested_at = None
            update_fields.append("resume_requested_at")
        if run.resume_attempt_id is not None:
            run_payload["resume_attempt_id"] = None
            run.resume_attempt_id = None
            update_fields.append("resume_attempt_id")

    def _handle_engine_run_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event_type = context.event_type
        event_id = context.event_id
        event_time = context.event_time
        trace_context = context.trace_context
        state_mutation_enabled = context.state_mutation_enabled
        callback_engine_instance_id = context.callback_engine_instance_id
        preflight_response = self._run_lifecycle_preflight_response(
            context,
            current_status=run.status,
            check_safety=True,
        )
        if preflight_response is not None:
            return preflight_response
        with transaction.atomic():
            run = _lock_run_for_update(run.id)
            context.run = run
            previous_status = run.status
            locked_response = self._run_lifecycle_preflight_response(
                context,
                current_status=previous_status,
                check_safety=False,
            )
            if locked_response is not None:
                return locked_response
            previous_paused_node_id = run.paused_node_id
            previous_pause_state = (
                dict(run.pause_state_json) if isinstance(run.pause_state_json, dict) else {}
            )
            mutation = self._run_lifecycle_mutation(context=context, run=run)
            if mutation.error_response is not None:
                return mutation.error_response
            run_payload = mutation.run_payload
            update_fields = mutation.update_fields
            pause_payload = mutation.pause_payload
            node_id = mutation.node_id
            projection_kwargs = mutation.projection_kwargs
            self._clear_resume_request_fields(
                run=run,
                run_payload=run_payload,
                update_fields=update_fields,
            )

            if state_mutation_enabled and update_fields:
                update_fields.extend(
                    touch_run_liveness(
                        run,
                        event_time=event_time,
                        recovery_state=recovery_state_for_status(run.status),
                        engine_instance_id=callback_engine_instance_id,
                    )
                )
                run.trace_id = trace_context["trace_id"]
                update_fields.append("trace_id")
                run.save(update_fields=sorted(set(update_fields)))

            final_run_stream_summaries = self._final_run_stream_summaries(run, event_type)

            _project_run_event_state(
                run=run,
                projection_status=run.status,
                trace_id=trace_context["trace_id"],
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                **projection_kwargs,
            )

            self._project_run_pause_event_state(
                context=context,
                node_id=node_id,
                pause_payload=pause_payload,
            )

            self._record_run_lifecycle_metrics(
                context=context,
                run=run,
                previous_status=previous_status,
            )

            lifecycle_event_saved = self._save_engine_callback_event(
                context, "run.updated", _serialize_event_payload(redact_payload(run_payload))
            )
            if lifecycle_event_saved:
                self._save_engine_callback_event(
                    context,
                    event_type,
                    _serialize_event_payload(redact_payload(run_payload)),
                    derived=True,
                )
            for summary_payload in final_run_stream_summaries:
                broadcast_node_stream_summary(run=run, payload=summary_payload)
            self._broadcast_run_lifecycle_decision_event(
                context=context,
                node_id=node_id,
                pause_payload=pause_payload,
                previous_paused_node_id=previous_paused_node_id,
                previous_pause_state=previous_pause_state,
            )

            for summary_payload in final_run_stream_summaries:
                broadcast_node_stream_summary(run=run, payload=summary_payload)

            if not state_mutation_enabled:
                return self._engine_callback_context_success(
                    context,
                    {
                        "received": True,
                        "event_type": event_type,
                        "authoritative_state_updated": False,
                    },
                    reason="event accepted without authoritative state mutation",
                    backend_event_id=str(event_id or ""),
                )

            message = broadcast_run_updated(run)
            return self._engine_callback_context_success(
                context,
                message,
                reason="run state event accepted",
                backend_event_id=str(event_id or ""),
            )

    def _final_run_stream_summaries(
        self,
        run: Run,
        event_type: str,
    ) -> list[dict[str, Any]]:
        if event_type not in {"run_completed", "run_failed", "run_canceled", "run_paused"}:
            return []
        return flush_all_stream_summaries(run_id=str(run.id), final_reason=event_type)

    def _project_run_pause_event_state(
        self,
        *,
        context: EngineCallbackContext,
        node_id: Any,
        pause_payload: Any,
    ) -> None:
        if context.event_type != "run_paused" or not node_id:
            return
        event = context.event
        trace_context = context.trace_context
        pause_payload_dict = pause_payload if isinstance(pause_payload, dict) else {}
        _project_pause_state(
            run=context.run,
            node_id=node_id,
            node_type=str(event.get("node_type") or ""),
            attempt=int(event.get("attempt") or 1),
            pause_payload=pause_payload_dict,
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
            event_time=context.event_time,
        )
        _project_node_event_state(
            run=context.run,
            node_id=node_id,
            node_type=str(event.get("node_type") or "human_gate"),
            attempt=int(event.get("attempt") or 1),
            projection_status="waiting",
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
            event_type=context.event_type,
            event_id=context.event_id,
            event_time=context.event_time,
            started_at=context.event_time,
            output_json={"pause_payload": pause_payload} if pause_payload else _UNSET,
        )

    def _broadcast_run_lifecycle_decision_event(
        self,
        *,
        context: EngineCallbackContext,
        node_id: Any,
        pause_payload: Any,
        previous_paused_node_id: str | None,
        previous_pause_state: dict[str, Any],
    ) -> None:
        if not context.state_mutation_enabled:
            return
        if context.event_type == "run_paused" and node_id:
            pause_payload_dict = pause_payload if isinstance(pause_payload, dict) else {}
            broadcast_decision_required(
                run=context.run,
                payload={
                    "node_id": node_id,
                    "node_type": str(context.event.get("node_type") or "human_gate"),
                    "attempt": int(context.event.get("attempt") or 1),
                    "status": "waiting",
                    "prompt_message": str(pause_payload_dict.get("prompt_message") or ""),
                    "required_fields": list(pause_payload_dict.get("required_fields") or []),
                    "node_name": str(pause_payload_dict.get("node_name") or ""),
                },
            )
            return
        if context.event_type == "run_resumed" and previous_paused_node_id:
            broadcast_decision_resolved(
                run=context.run,
                payload={
                    "node_id": previous_paused_node_id,
                    "status": "resolved",
                    "prompt_message": str(previous_pause_state.get("prompt_message") or ""),
                    "required_fields": list(previous_pause_state.get("required_fields") or []),
                    "resolution": redact_payload(context.event.get("output") or {}),
                },
            )

    def _build_engine_node_payload(
        self, context: EngineCallbackContext
    ) -> tuple[Any, Any, int, dict[str, Any]]:
        run = context.run
        event = context.event
        event_type = context.event_type
        trace_context = context.trace_context
        callback_engine_instance_id = context.callback_engine_instance_id
        node_id = event.get("node_id") or ""
        node_type = event.get("node_type") or ""
        attempt = int(event.get("attempt") or 1)
        attempt_id = str(event.get("attempt_id") or "").strip() or None
        node_payload: dict[str, Any] = {
            "node_id": node_id,
            "node_type": node_type,
            "attempt": attempt,
            "trace_id": trace_context["trace_id"],
            "span_id": trace_context["span_id"],
        }
        if event_type in {"node_started", "node_completed"}:
            log_event(
                logger,
                logging.INFO,
                event_type,
                run_id=str(run.id),
                trace_id=trace_context["trace_id"],
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                attempt_id=attempt_id,
                engine_instance_id=callback_engine_instance_id,
                message="Engine node lifecycle event received",
            )

        self._apply_engine_node_payload_event(
            context=context,
            node_payload=node_payload,
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
        )
        return node_id, node_type, attempt, node_payload

    def _apply_engine_node_payload_event(
        self,
        *,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        event_type = context.event_type
        event_time = context.event_time
        if event_type == "node_started":
            self._apply_engine_node_started_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_completed":
            self._apply_engine_node_completed_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_failed":
            self._apply_engine_node_failed_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_skipped":
            node_payload["status"] = "skipped"
            if event_time:
                node_payload["ended_at"] = event_time
            return
        if event_type == "node_retrying":
            node_payload["status"] = "running"

    def _apply_engine_node_started_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["input_json"] = redact_payload(context.event.get("input") or {})
        self._log_engine_node_payload(
            context=context,
            event_name="node_input",
            node_payload=node_payload["input_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node input received",
        )
        node_payload["status"] = "running"
        if context.event_time:
            node_payload["started_at"] = context.event_time

    def _apply_engine_node_completed_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["status"] = "succeeded"
        if context.event_time:
            node_payload["ended_at"] = context.event_time
        node_payload["output_json"] = redact_payload(context.event.get("output"))
        self._log_engine_node_payload(
            context=context,
            event_name="node_output",
            node_payload=node_payload["output_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node output received",
        )

    def _apply_engine_node_failed_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["status"] = "failed"
        if context.event_time:
            node_payload["ended_at"] = context.event_time
        node_payload["error_json"] = self._engine_node_error_json(context.event)
        self._log_engine_node_payload(
            context=context,
            event_name="node_output",
            node_payload=node_payload["error_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node failure output received",
        )

    def _engine_node_error_json(self, event: dict[str, Any]) -> dict[str, Any]:
        error_message = redact_payload(event.get("error") or "")
        output_payload = redact_payload(event.get("output") or {})
        error_json: dict[str, Any] = {}
        if isinstance(output_payload, dict) and isinstance(output_payload.get("error"), dict):
            error_json = dict(output_payload["error"])
        if not error_json:
            return {"error": error_message}
        if error_message:
            error_json.setdefault("error", error_message)
        return error_json

    def _log_engine_node_payload(
        self,
        *,
        context: EngineCallbackContext,
        event_name: str,
        node_payload: Any,
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
        message: str,
    ) -> None:
        log_event(
            logger,
            logging.INFO,
            event_name,
            run_id=str(context.run.id),
            trace_id=context.trace_context["trace_id"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            engine_instance_id=context.callback_engine_instance_id,
            payload=_log_payload_summary(node_payload),
            message=message,
        )

    def _record_node_lifecycle_accounting(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        usage_payload = _extract_llm_usage_payload(
            node_type=node_type,
            output_json=node_payload.get("output_json"),
        )
        if node_type not in {"prompt", "agent"} or not usage_payload:
            return None
        prompt_tokens = usage_payload["prompt_tokens"]
        completion_tokens = usage_payload["completion_tokens"]
        total_tokens = usage_payload["total_tokens"]
        if not (prompt_tokens or completion_tokens or total_tokens):
            return None

        model = usage_payload["model"]
        provider = usage_payload["provider"]
        tenant_id = get_tenant_id_for_run(run)
        cost = calculate_cost(provider, model, prompt_tokens, completion_tokens)
        usage_key_material = (
            f"{context.event_id or run.id}:{run.id}:{node_id}:{attempt}:{provider}:{model}"
        )
        usage_external_key = f"llm:{hashlib.sha256(usage_key_material.encode('utf-8')).hexdigest()}"
        accounting_request_hash = hash_request_payload(
            {
                "event_id": context.event_id,
                "run_id": str(run.id),
                "node_id": node_id,
                "attempt": attempt,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": str(cost),
            }
        )
        llm_usage, _ = LLMUsage.objects.update_or_create(
            tenant_id=tenant_id,
            external_key=usage_external_key,
            defaults={
                "run": run,
                "node_id": node_id,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost,
            },
        )
        ProcessedAccountingEvent.objects.update_or_create(
            organization_id=tenant_id,
            event_key=usage_external_key,
            defaults={
                "event_type": "llm_usage",
                "request_hash": accounting_request_hash,
                "llm_usage": llm_usage,
                "status": "applied",
            },
        )
        record_idempotency_observation(
            boundary="accounting_write",
            status="applied",
            idempotency_key=usage_external_key,
            resource_type="llm_usage",
            organization_id=tenant_id,
            run_id=run.id,
        )
        return {
            "node_id": node_id,
            "node_type": node_type,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": float(cost),
        }

    def _upsert_node_run_from_payload(
        self,
        *,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
        trace_context: dict[str, str],
    ) -> NodeRun:
        node_run, created = NodeRun.objects.get_or_create(
            run=run,
            node_id=node_id,
            attempt=attempt,
            defaults={
                "node_type": node_type,
                "status": node_payload["status"],
            },
        )
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")

        node_run.status = node_payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field in node_payload:
                setattr(node_run, field, node_payload[field])
                node_update_fields.append(field)
        node_run.trace_id = trace_context["trace_id"]
        node_run.span_id = trace_context["span_id"]
        node_update_fields.extend(["trace_id", "span_id"])
        node_run.save(update_fields=sorted(set(node_update_fields)))
        return node_run

    def _ephemeral_node_run_from_payload(
        self,
        *,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
        trace_context: dict[str, str],
    ) -> NodeRun:
        node_run = NodeRun(
            run=run,
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            status=str(node_payload["status"]),
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
        )
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field in node_payload:
                setattr(node_run, field, node_payload[field])
        return node_run

    def _record_node_retry_lifecycle(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_id: Any,
        event_time: datetime | None,
        node_run: NodeRun,
        node_id: Any,
        node_type: Any,
        attempt: int,
    ) -> None:
        retry_attempt = int(event.get("retry_attempt") or attempt)
        max_attempts = int(event.get("max_attempts") or event.get("max_retries") or retry_attempt)
        retry_delay_ms = int(event.get("retry_delay_ms") or event.get("retry_after_ms") or 0)
        retry_reason = str(event.get("reason") or event.get("error") or "node retry scheduled")
        transition_task_lifecycle(
            run=run,
            node_id=node_id,
            node_type=node_type,
            to_status="retry_scheduled",
            attempt_number=attempt,
            parent_attempt_number=attempt - 1 if attempt > 1 else None,
            source="engine_callback",
            idempotency_key=f"task:{event_id or run.id}:{node_id}:retry",
            reason=retry_reason,
            node_run=node_run,
            owner_component="engine",
            payload={
                "retry_attempt": retry_attempt,
                "max_attempts": max_attempts,
                "retry_delay_ms": retry_delay_ms,
            },
            occurred_at=event_time,
        )
        record_retry_operation(
            run=run,
            operation_type="node_execution",
            idempotency_key=f"retry:{event_id or run.id}:{node_id}:{attempt}",
            attempt_number=retry_attempt,
            max_attempts=max(max_attempts, retry_attempt),
            retry_delay_ms=retry_delay_ms,
            retry_reason=retry_reason,
            last_error=str(event.get("error") or retry_reason),
            owning_component="engine",
            retry_class=str(event.get("retry_class") or "llm_backpressure"),
            terminal_fallback="dead_letter",
            node_id=node_id,
            node_type=node_type,
            parent_attempt_number=attempt - 1 if attempt > 1 else None,
            payload=redact_payload(event),
        )

    def _record_node_lifecycle_transition(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: str,
        event_id: Any,
        event_time: datetime | None,
        node_run: NodeRun,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
    ) -> None:
        try:
            if event_type == "node_retrying":
                self._record_node_retry_lifecycle(
                    run=run,
                    event=event,
                    event_id=event_id,
                    event_time=event_time,
                    node_run=node_run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                )
            else:
                transition_from_node_run(
                    run=run,
                    node_run=node_run,
                    source="engine_callback",
                    idempotency_key=(
                        f"task:{event_id or run.id}:{node_id}:{node_payload['status']}:{attempt}"
                    ),
                    reason=str(node_payload.get("error_json") or ""),
                    occurred_at=event_time,
                )
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "task_lifecycle_projection_failed",
                run_id=str(run.id),
                node_id=node_id,
                attempt=attempt,
                event_type=event_type,
                error_message=str(exc),
            )

    def _touch_run_for_node_lifecycle(
        self,
        *,
        run: Run,
        event_time: datetime | None,
        trace_context: dict[str, str],
        callback_engine_instance_id: str,
    ) -> None:
        run_update_fields = touch_run_liveness(
            run,
            event_time=event_time,
            recovery_state=recovery_state_for_status(run.status),
            engine_instance_id=callback_engine_instance_id,
        )
        if run.trace_id != trace_context["trace_id"]:
            run.trace_id = trace_context["trace_id"]
            run_update_fields.append("trace_id")
        run.save(update_fields=sorted(set(run_update_fields)))

    def _handle_engine_node_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_type = context.event_type
        event_id = context.event_id
        event_time = context.event_time
        trace_context = context.trace_context
        state_mutation_enabled = context.state_mutation_enabled
        callback_engine_instance_id = context.callback_engine_instance_id
        safety_response = self._runtime_safety_response(context)
        if safety_response is not None:
            return safety_response
        node_id, node_type, attempt, node_payload = self._build_engine_node_payload(context)
        cost_update_payload: dict[str, Any] | None = None
        node_run: NodeRun | None = None
        with transaction.atomic():
            run = _lock_run_for_update(run.id)
            context.run = run
            if state_mutation_enabled:
                node_run = self._upsert_node_run_from_payload(
                    run=run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                    trace_context=trace_context,
                )
                self._record_node_lifecycle_transition(
                    run=run,
                    event=event,
                    event_type=event_type,
                    event_id=event_id,
                    event_time=event_time,
                    node_run=node_run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                )
                self._touch_run_for_node_lifecycle(
                    run=run,
                    event_time=event_time,
                    trace_context=trace_context,
                    callback_engine_instance_id=callback_engine_instance_id,
                )
            else:
                node_run = self._ephemeral_node_run_from_payload(
                    run=run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                    trace_context=trace_context,
                )

            if event_type == "node_failed" and _payload_contains_policy_denied(
                node_payload.get("error_json")
            ):
                record_audit_log(
                    actor=None,
                    tenant_id=get_tenant_id_for_run(run),
                    action="run.policy_denied",
                    resource_type="node_run",
                    resource_id=str(node_run.id or f"{run.id}:{node_id}:{attempt}"),
                    metadata={
                        "run_id": str(run.id),
                        "node_id": node_id,
                        "node_type": node_type,
                        "attempt": attempt,
                        "error_json": redact_payload(node_payload.get("error_json") or {}),
                    },
                )
            _project_node_event_state(
                run=run,
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                projection_status=str(node_payload["status"]),
                trace_id=trace_context["trace_id"],
                span_id=trace_context["span_id"],
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                started_at=node_payload.get("started_at", _UNSET),
                ended_at=node_payload.get("ended_at", _UNSET),
                output_json=node_payload.get("output_json", _UNSET),
                error_json=node_payload.get("error_json", _UNSET),
            )
            self._save_engine_callback_event(
                context, "node_run.updated", _serialize_event_payload(redact_payload(node_payload))
            )
            if (
                state_mutation_enabled
                and event_type == "node_completed"
                and getattr(node_run, "id", None)
            ):
                _schedule_deliverable_archive(run.id, node_run.id)

            cost_update_payload = self._record_node_lifecycle_accounting(
                context=context,
                run=run,
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                node_payload=node_payload,
            )

        if event_type in {"node_completed", "node_failed", "node_skipped"}:
            summary_payload = flush_stream_summary(
                run_id=str(run.id),
                node_id=node_id,
                attempt=attempt,
                final_reason=event_type,
            )
            if summary_payload:
                broadcast_node_stream_summary(run=run, payload=summary_payload)

        if cost_update_payload:
            broadcast_cost_update(run=run, payload=cost_update_payload)

        if not state_mutation_enabled:
            return self._engine_callback_context_success(
                context,
                {
                    "received": True,
                    "event_type": event_type,
                    "authoritative_state_updated": False,
                },
                reason="event accepted without authoritative state mutation",
                backend_event_id=str(event_id or ""),
            )

        message = broadcast_node_run_updated(run=run, node_run=node_run)
        return self._engine_callback_context_success(
            context,
            message,
            reason="node state event accepted",
            backend_event_id=str(event_id or ""),
        )


class RunEventsView(APIView):
    """Persist + broadcast Run/NodeRun delta events.

    These authenticated events are write requests, not authoritative state by themselves.
    """

    permission_classes = [IsAuthenticated]

    def _event_safety_response(
        self,
        *,
        event_type: str,
        normalized_category: str,
        payload: dict[str, Any],
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=payload,
            )
        except EventSafetyViolation as exc:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        return None

    def _run_output_schema_errors(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]] | None]:
        output_schema = None
        schema_mode = "warn"
        try:
            _, output_schema, _, schema_mode = extract_schema_metadata(run.graph_version.graph_json)
        except Exception:
            output_schema = None

        if not (
            isinstance(output_schema, dict)
            and payload.get("status") == "succeeded"
            and "output_json" in payload
        ):
            return schema_mode, None
        try:
            return schema_mode, validate_json_schema(payload.get("output_json"), output_schema)
        except SchemaError as exc:
            log_event(
                logger,
                logging.WARNING,
                "run_output_schema_invalid",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
            return schema_mode, None

    def _apply_authenticated_run_payload(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> None:
        update_fields: list[str] = []
        for field in ["status", "started_at", "ended_at", "output_json", "error_message"]:
            if field not in payload:
                continue
            value = payload[field]
            if field in {"output_json", "error_message"}:
                value = redact_payload(value)
            setattr(run, field, value)
            payload[field] = value
            update_fields.append(field)

        if "paused_node_id" in payload:
            run.paused_node_id = payload["paused_node_id"]
            update_fields.append("paused_node_id")
        if "pause_state_json" in payload:
            run.pause_state_json = redact_payload(payload["pause_state_json"])
            payload["pause_state_json"] = run.pause_state_json
            update_fields.append("pause_state_json")

        if update_fields:
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status(run.status),
                    engine_instance_id=run.engine_instance_id or engine_instance_label(),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _ensure_pause_approval_task(self, *, run: Run, payload: dict[str, Any]) -> None:
        if payload.get("status") != "paused":
            return
        pause_output = payload.get("pause_payload", {})
        node_id = run.paused_node_id or pause_output.get("node_id", "")
        if not node_id:
            return
        ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": {
                    "prompt_message": pause_output.get("prompt_message", ""),
                    "required_fields": pause_output.get("required_fields", []),
                },
            },
        )

    def _persist_authenticated_schema_errors(
        self,
        *,
        run: Run,
        schema_mode: str,
        schema_errors: list[dict[str, Any]] | None,
    ) -> None:
        if not schema_errors:
            return
        try:
            RunEvent.objects.create(
                run=run,
                event_type="run.schema_validation",
                payload=redact_payload(
                    {
                        "errors": schema_errors,
                        "mode": schema_mode,
                        "category": normalize_event_category("run.schema_validation"),
                    }
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _persist_authenticated_run_event(
        self,
        *,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        normalized_category: str,
    ) -> None:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "run_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _handle_authenticated_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        schema_mode, schema_errors = self._run_output_schema_errors(run=run, payload=payload)
        if schema_errors and schema_mode == "strict":
            payload["status"] = "failed"
            payload["error_message"] = (
                f"Output schema validation failed: {schema_errors[0]['message']}"
            )
        self._apply_authenticated_run_payload(run=run, payload=payload)
        self._ensure_pause_approval_task(run=run, payload=payload)
        self._persist_authenticated_schema_errors(
            run=run,
            schema_mode=schema_mode,
            schema_errors=schema_errors,
        )
        self._persist_authenticated_run_event(
            run=run,
            event_type=event_type,
            payload=payload,
            normalized_category=normalized_category,
        )
        return success_response(broadcast_run_updated(run))

    def _apply_authenticated_node_payload(
        self,
        *,
        node_run: NodeRun,
        created: bool,
        node_type: Any,
        payload: dict[str, Any],
    ) -> list[str]:
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")
        node_run.status = payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field not in payload:
                continue
            value = redact_payload(payload[field]) if field.endswith("_json") else payload[field]
            setattr(node_run, field, value)
            payload[field] = value
            node_update_fields.append(field)
        return node_update_fields

    def _handle_authenticated_node_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
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
            node_update_fields = self._apply_authenticated_node_payload(
                node_run=node_run,
                created=created,
                node_type=node_type,
                payload=payload,
            )
            node_run.save(update_fields=sorted(set(node_update_fields)))
            run_update_fields = touch_run_liveness(
                run,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=run.engine_instance_id or engine_instance_label(),
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )

        return success_response(broadcast_node_run_updated(run=run, node_run=node_run))

    def _handle_authenticated_schema_validation(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload={
                    **payload,
                    "category": normalized_category,
                },
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
        return success_response(broadcast_run_schema_validation(run=run, payload=payload))

    def post(self, request: Request, run_id: UUID) -> Response:
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

        user = cast(User, request.user)
        try:
            run = run_queryset_for_user(user).get(id=run_id)
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        event_type = serializer.validated_data["event_type"]
        normalized_category = normalize_event_category(
            event_type,
            category=str(serializer.validated_data.get("category") or ""),
        )

        if event_type == "run.updated":
            safety_response = self._event_safety_response(
                event_type=event_type,
                normalized_category=normalized_category,
                payload=serializer.validated_data,
            )
            if safety_response is not None:
                return safety_response
            return self._handle_authenticated_run_updated(
                run=run,
                payload=serializer.validated_data["run"],
                event_type=event_type,
                normalized_category=normalized_category,
            )

        if event_type == "node_run.updated":
            safety_response = self._event_safety_response(
                event_type=event_type,
                normalized_category=normalized_category,
                payload=serializer.validated_data,
            )
            if safety_response is not None:
                return safety_response
            return self._handle_authenticated_node_run_updated(
                run=run,
                payload=serializer.validated_data["node_run"],
                event_type=event_type,
                normalized_category=normalized_category,
            )

        if event_type == "run.schema_validation":
            payload = redact_payload(serializer.validated_data.get("payload") or {})
            return self._handle_authenticated_schema_validation(
                run=run,
                payload=payload,
                event_type=event_type,
                normalized_category=normalized_category,
            )

        return error_response(
            code="VALIDATION_ERROR",
            message="Unknown event_type",
            status=status.HTTP_400_BAD_REQUEST,
        )


def _build_stream_message(*, run: Run, event: RunEvent) -> dict[str, Any]:
    payload: dict[str, Any] = event.payload or {}
    message: dict[str, Any] = {
        "event_id": str(event.id),
        "timestamp": event.created_at.isoformat(),
        "type": event.event_type,
        "run_id": str(run.id),
        "trace_id": event.trace_id or run.trace_id,
        "category": normalize_event_category(
            event.event_type,
            category=str(payload.get("category") or ""),
            payload=payload,
        ),
    }
    if event.event_type == "run.updated":
        message["run"] = payload
    elif event.event_type == "node_run.updated":
        message["node_run"] = payload
    elif event.event_type == "node_stream.chunk":
        message["node_stream"] = payload
    else:
        message["payload"] = payload
    return add_event_level(message, payload=payload)


def _format_sse(message: dict[str, Any], event_name: str | None = None) -> str:
    payload = pyjson.dumps(message, default=str)
    lines = []
    if event_name:
        lines.append(f"event: {event_name}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def _datetime_from_timestamp_ms(timestamp_ms: int | None) -> datetime | None:
    if not timestamp_ms:
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _serialize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _persist_run_updated_event(run: Run) -> None:
    RunEvent.objects.create(
        run=run,
        event_type="run.updated",
        trace_id=run.trace_id,
        payload=_serialize_event_payload(
            redact_payload(
                {
                    "status": run.status,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "output_json": run.output_json,
                    "error_message": run.error_message,
                    "paused_node_id": run.paused_node_id,
                    "pause_state_json": run.pause_state_json,
                    "category": "state",
                }
            )
        ),
    )


def _get_user_from_request(request: Request) -> User | None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return cast(User, user)

    ticket_user = _user_from_stream_ticket(request)
    if ticket_user is not None:
        return ticket_user
    return _user_from_query_access_token(request)


def _user_from_stream_ticket(request: Request) -> User | None:
    ticket = str(request.query_params.get("ticket") or "").strip()
    if not ticket:
        return None
    ticket_payload = consume_ws_ticket(ticket)
    if not isinstance(ticket_payload, dict):
        return None
    permissions = ticket_payload.get("permissions")
    if isinstance(permissions, list) and "runs:view" not in permissions:
        return None
    access_jti = str(ticket_payload.get("access_jti") or "").strip()
    if access_jti and is_access_jti_revoked(access_jti):
        return None
    return _user_by_id(str(ticket_payload.get("user_id") or "").strip())


def _user_from_query_access_token(request: Request) -> User | None:
    if not getattr(settings, "RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN", False):
        return None

    token = request.query_params.get("token")
    if not token:
        return None

    access_token = validate_access_token(cast(Any, token))
    if access_token is None:
        return None

    user_id_claim = getattr(settings, "SIMPLE_JWT", {}).get("USER_ID_CLAIM", "user_id")
    user_id = access_token.get(user_id_claim)
    return _user_by_id(str(user_id or ""))


def _user_by_id(user_id: str) -> User | None:
    if not user_id:
        return None
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return None


async def _receive_with_timeout(channel_layer: Any, channel_name: str, timeout: float) -> Any:
    try:
        return await asyncio.wait_for(channel_layer.receive(channel_name), timeout=timeout)
    except TimeoutError:
        return None


class RunEventsStreamView(APIView):
    """Stream run events over Server-Sent Events (SSE)."""

    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> StreamingHttpResponse | Response:
        user = _get_user_from_request(request)
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            run = run_queryset_for_user(user).get(id=run_id)
        except Run.DoesNotExist:
            return Response({"detail": "Run not found"}, status=status.HTTP_404_NOT_FOUND)

        since_param = request.query_params.get("since")
        since = parse_datetime(since_param) if since_param else None
        requested_level = normalize_requested_event_level(request.query_params.get("event_level"))
        response = StreamingHttpResponse(
            self._event_stream(run=run, since=since, requested_level=requested_level),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response

    def _event_stream(
        self,
        *,
        run: Run,
        since: datetime | None,
        requested_level: str,
    ) -> Any:
        yield _format_sse(
            {
                "type": "connected",
                "run_id": str(run.id),
                "timestamp": timezone.now().isoformat(),
                "level": requested_level,
            },
            event_name="connected",
        )
        yield from _historical_sse_events(run=run, since=since, requested_level=requested_level)
        yield from _live_sse_events(run=run, requested_level=requested_level)


def _historical_sse_events(
    *,
    run: Run,
    since: datetime | None,
    requested_level: str,
) -> Any:
    if since is None:
        return
    for event in RunEvent.objects.filter(run=run, created_at__gt=since).order_by("created_at"):
        message = _build_stream_message(run=run, event=event)
        if message_allowed_for_level(message, requested_level):
            yield _format_sse(message, event_name=event.event_type)


def _live_sse_events(*, run: Run, requested_level: str) -> Any:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    channel_name = async_to_sync(channel_layer.new_channel)()
    group_names = [
        run_event_group_name(run_id=str(run.id), level=level)
        for level in event_levels_for_subscription(requested_level)
    ]
    for group_name in group_names:
        async_to_sync(channel_layer.group_add)(group_name, channel_name)

    try:
        yield from _live_sse_messages(channel_layer, channel_name)
    except GeneratorExit:
        return
    finally:
        for group_name in group_names:
            async_to_sync(channel_layer.group_discard)(group_name, channel_name)


def _live_sse_messages(channel_layer: Any, channel_name: str) -> Any:
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
