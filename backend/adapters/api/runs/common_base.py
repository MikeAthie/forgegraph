"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

# ruff: noqa: F401,F811

import asyncio
import hashlib
import json as pyjson
import logging
import time
from collections import defaultdict
from collections.abc import Callable
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
from application.use_cases.runs.dtos import (
    EngineCallbackContext,
    ReplayCheckpointSeed,
    RunEngineDispatch,
    RunInvokeRequestContext,
    RunLifecycleMutation,
    RunReplayRequestContext,
    RunResumeRequestContext,
    RunStartRequestContext,
)
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


class EngineCallbackComposableMixin:
    """Typing contract for engine callback mixins composed on EngineRunEventsView."""

    def _save_engine_callback_event(
        self,
        context: EngineCallbackContext,
        event_type_name: str,
        payload: dict[str, Any],
        *,
        derived: bool = False,
    ) -> bool:
        raise NotImplementedError

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
        raise NotImplementedError

    def _runtime_safety_response(
        self,
        context: EngineCallbackContext,
        *,
        reason: str = "event safety violation",
    ) -> Response | None:
        raise NotImplementedError

    def _handle_engine_schema_validation_event(self, context: EngineCallbackContext) -> Response:
        raise NotImplementedError

    def _handle_engine_stream_chunk_event(self, context: EngineCallbackContext) -> Response:
        raise NotImplementedError

    def _handle_engine_memory_intent_event(self, context: EngineCallbackContext) -> Response:
        raise NotImplementedError

    def _handle_engine_run_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        raise NotImplementedError

    def _handle_engine_node_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        raise NotImplementedError


__all__ = [
    "Any",
    "APIView",
    "AllowAny",
    "ApprovalTask",
    "ArchiveService",
    "BackendMemoryIntentService",
    "Callable",
    "CanonicalEventValidationError",
    "Case",
    "ContextPackService",
    "Count",
    "DecisionRecord",
    "Decimal",
    "EngineAssignmentError",
    "EngineCallbackContext",
    "EngineCallbackComposableMixin",
    "EngineConnectionError",
    "EngineExecutionError",
    "EngineExecutionEventSerializer",
    "EventSafetyViolation",
    "GraphVersion",
    "GrpcEngineClient",
    "IdempotencyConflict",
    "IdempotencyStatus",
    "IntegerField",
    "IntegrityError",
    "IsAuthenticated",
    "LLMAccessConfig",
    "LLMAccessValidationError",
    "LLMBudget",
    "LLMQuota",
    "LLMUsage",
    "LLM_MODE_MANAGED",
    "NodeRun",
    "NodeRunEventProjection",
    "OperationalError",
    "Organization",
    "Prefetch",
    "PreferenceEventService",
    "ProcessedAccountingEvent",
    "ProcessedCallbackEvent",
    "ProcessedDecisionSubmission",
    "PromptTemplateResolutionError",
    "Q",
    "ReplayCheckpointSeed",
    "Request",
    "Response",
    "Run",
    "RunCheckpoint",
    "RunDetailWithNodeRunsSerializer",
    "RunEngineDispatch",
    "RunEvent",
    "RunEventProjection",
    "RunEventSerializer",
    "RunInvokeRequestContext",
    "RunInvokeSerializer",
    "RunLifecycleMutation",
    "RunListSerializer",
    "RunReplayRequestContext",
    "RunReplaySerializer",
    "RunResumeRequestContext",
    "RunResumeSerializer",
    "RunSnapshot",
    "RunStartRequestContext",
    "RunStartSerializer",
    "RunTransitionConflict",
    "SchemaError",
    "StreamingHttpResponse",
    "SubgraphResolutionError",
    "Sum",
    "TenantSubscription",
    "ToolExecutionDispatchBlocked",
    "UTC",
    "UUID",
    "User",
    "When",
    "_DEADLOCK_RETRY_ATTEMPTS",
    "_UNSET",
    "acquire_run_transaction_lock",
    "add_event_level",
    "annotate_response",
    "annotated_response_from_body",
    "apply_run_status_transition",
    "assert_run_transition_allowed",
    "assert_runtime_state_mutation_allowed",
    "async_to_sync",
    "asyncio",
    "attach_llm_access_to_graph",
    "broadcast_cost_update",
    "broadcast_decision_required",
    "broadcast_decision_resolved",
    "broadcast_node_run_updated",
    "broadcast_node_stream_chunk",
    "broadcast_node_stream_summary",
    "broadcast_run_schema_validation",
    "broadcast_run_updated",
    "build_idempotency_context",
    "build_memory_config_json",
    "calculate_cost",
    "cast",
    "check_managed_llm_limits",
    "check_rate_limit",
    "consume_ws_ticket",
    "datetime",
    "defaultdict",
    "derive_node_memory_activity",
    "engine_input_with_llm_access",
    "engine_instance_label",
    "engine_llm_access_from_graph",
    "enqueue_run",
    "ensure_trace_context",
    "error_response",
    "event_levels_for_subscription",
    "extract_schema_metadata",
    "flush_all_stream_summaries",
    "flush_stream_summary",
    "get_channel_layer",
    "get_engine_target_by_id",
    "get_snapshot",
    "hash_request_payload",
    "hashlib",
    "has_min_role",
    "initialize_lifecycle_tasks_for_run",
    "is_access_jti_revoked",
    "log_event",
    "log_run_queue_worker_unavailable",
    "logger",
    "logging",
    "mark_run_tasks_terminal",
    "message_allowed_for_level",
    "models",
    "normalize_event_category",
    "normalize_idempotency_key",
    "normalize_requested_event_level",
    "parse_datetime",
    "parse_engine_event_payload",
    "prepare_graph_for_engine",
    "prepare_tool_executions_for_dispatch",
    "problem_response",
    "public_llm_access_from_graph",
    "pyjson",
    "rate_limit_response_payload",
    "reconcile_run_engine_instance",
    "record_audit_log",
    "record_callback_auth_failure",
    "record_event_dead_letter",
    "record_idempotency_observation",
    "record_processed_command",
    "record_retry_operation",
    "record_run_completed",
    "record_run_started",
    "record_stale_attempt_ignored",
    "recovery_state_for_status",
    "redact_payload",
    "replay_processed_command",
    "resolve_engine_callback_url",
    "resolve_llm_access_for_dispatch",
    "resolve_tenant_id_for_user",
    "response_body",
    "run_event_group_name",
    "s2s",
    "safe_delete_snapshot",
    "safe_set_snapshot",
    "select_engine_target",
    "set_snapshot",
    "settings",
    "start_backend_span",
    "status",
    "success_response",
    "summarize_run_memory_activity",
    "time",
    "timezone",
    "touch_run_liveness",
    "transaction",
    "transition_from_node_run",
    "transition_task_lifecycle",
    "update_stream_summary",
    "upsert_memory_session",
    "uuid4",
    "validate_access_token",
    "validate_json_schema",
    "validate_prompt_credentials",
]
