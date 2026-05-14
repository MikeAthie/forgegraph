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


__all__ = [name for name in globals() if not name.startswith("__")]
