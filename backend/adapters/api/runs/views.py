"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

import asyncio
import json as pyjson
import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, models, transaction
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
    broadcast_node_run_updated,
    broadcast_node_stream_chunk,
    broadcast_node_stream_summary,
    broadcast_run_schema_validation,
    broadcast_run_updated,
)
from application.services.audit_log import record_audit_log
from application.services.auth_state import validate_access_token
from application.services.cloudevents import unwrap_engine_event
from application.services.engine_selection import (
    EngineAssignmentError,
    get_engine_target_by_id,
    reconcile_run_engine_instance,
    select_engine_target,
)
from application.services.engine_selection import (
    resolve_engine_callback_url as resolve_engine_callback_url,
)
from application.services.event_categories import normalize_event_category
from application.services.llm_pricing import calculate_cost
from application.services.metrics import record_run_completed, record_run_started
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
from application.services.run_liveness import (
    engine_instance_label,
)
from application.services.run_liveness import (
    recovery_state_for_status as recovery_state_for_status,
)
from application.services.run_liveness import (
    touch_run_liveness as touch_run_liveness,
)
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
from application.services.structured_logging import log_event
from application.services.telemetry import start_backend_span
from application.services.tenancy import get_tenant_id_for_user as resolve_tenant_id_for_user
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import (
    ApprovalTask,
    GraphVersion,
    LLMBudget,
    LLMQuota,
    LLMUsage,
    NodeRun,
    NodeRunEventProjection,
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
    return get_tenant_id_for_user(run.owner)


def _request_trace_headers(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("traceparent"), request.headers.get("tracestate")


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
    tenant_uuid = UUID(tenant_id)
    return Run.objects.filter(owner__default_organization_id=tenant_uuid)


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
            owner__default_organization_id=tenant_uuid, started_at__gte=month_start
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
        "input_json": redact_payload(node_run.input_json),
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
    run_payload = payload.get("run")
    if isinstance(run_payload, dict) and isinstance(run_payload.get("status"), str):
        return str(run_payload["status"])
    node_payload = payload.get("node_run")
    if isinstance(node_payload, dict) and isinstance(node_payload.get("status"), str):
        return str(node_payload["status"])

    if event_type.endswith("_failed"):
        return "failed"
    if event_type.endswith("_completed"):
        return "succeeded"
    if event_type.endswith("_started"):
        return "running"
    if event_type == "run_paused":
        return "paused"
    if event_type == "run_resumed":
        return "running"
    if event_type == "node_retrying":
        return "retrying"
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
    if event_type == "run_started":
        return "Run started."
    if event_type == "run_completed":
        return "Run completed successfully."
    if event_type == "run_failed":
        return str(payload.get("error") or payload.get("error_message") or "Run failed.")
    if event_type == "run_paused":
        return "Run paused for a decision boundary."
    if event_type == "run_resumed":
        return "Run resumed after a decision."
    if event_type == "run_canceled":
        return "Run canceled."
    if event_type == "node_started" and node_id:
        return f"{node_id} started."
    if event_type == "node_completed" and node_id:
        return f"{node_id} completed."
    if event_type == "node_failed" and node_id:
        return f"{node_id} failed."
    if event_type == "node_retrying" and node_id:
        return f"{node_id} is retrying."
    if event_type == "node_skipped" and node_id:
        return f"{node_id} was skipped."
    if event_type == "run.schema_validation":
        return "Run output schema validation reported issues."
    return event_type.replace(".", " ").replace("_", " ")


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

    edges_raw = graph_json.get("edges")
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    if isinstance(edges_raw, list):
        for edge in edges_raw:
            if not isinstance(edge, dict):
                continue
            from_id = edge.get("from")
            to_id = edge.get("to")
            if not from_id or not to_id:
                continue
            if str(from_id) in adjacency:
                adjacency[str(from_id)].append(str(to_id))

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
        owner__default_organization_id=tenant_uuid,
        status__in=["pending", "running", "paused"],
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
        if not created and node_run.node_type != normalized_node_type:
            node_run.node_type = normalized_node_type
            node_update_fields.append("node_type")
        if node_run.status != "waiting":
            node_run.status = "waiting"
            node_update_fields.append("status")
        if event_time and node_run.started_at != event_time:
            node_run.started_at = event_time
            node_update_fields.append("started_at")
        if pause_payload:
            output_json = (
                dict(node_run.output_json) if isinstance(node_run.output_json, dict) else {}
            )
            output_json["pause_payload"] = pause_payload
            if output_json != node_run.output_json:
                node_run.output_json = output_json
                node_update_fields.append("output_json")
        if node_run.trace_id != trace_id:
            node_run.trace_id = trace_id
            node_update_fields.append("trace_id")
        if node_run.span_id != span_id:
            node_run.span_id = span_id
            node_update_fields.append("span_id")
        if node_update_fields:
            node_run.save(update_fields=sorted(set(node_update_fields)))

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
            },
        )
        if not created and approval_task.payload != approval_payload:
            approval_task.payload = approval_payload
            approval_task.save(update_fields=["payload"])


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
    if projection.status != projection_status:
        projection.status = projection_status
        update_fields.append("status")
    if started_at is not _UNSET and projection.started_at != started_at:
        projection.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and projection.ended_at != ended_at:
        projection.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if output_json is not _UNSET and projection.output_json != output_json:
        projection.output_json = output_json
        update_fields.append("output_json")
    if error_message is not _UNSET and projection.error_message != error_message:
        projection.error_message = cast(str, error_message)
        update_fields.append("error_message")
    if pause_state_json is not _UNSET and projection.pause_state_json != pause_state_json:
        projection.pause_state_json = pause_state_json
        update_fields.append("pause_state_json")
    if paused_node_id is not _UNSET and projection.paused_node_id != paused_node_id:
        projection.paused_node_id = cast(str | None, paused_node_id)
        update_fields.append("paused_node_id")
    if projection.trace_id != trace_id:
        projection.trace_id = trace_id
        update_fields.append("trace_id")
    if projection.last_event_type != event_type:
        projection.last_event_type = event_type
        update_fields.append("last_event_type")
    next_event_id = event_id or ""
    if projection.last_event_id != next_event_id:
        projection.last_event_id = next_event_id
        update_fields.append("last_event_id")
    effective_event_time = event_time or timezone.now()
    if projection.last_event_at != effective_event_time:
        projection.last_event_at = effective_event_time
        update_fields.append("last_event_at")
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
    if projection.node_type != node_type:
        projection.node_type = node_type
        update_fields.append("node_type")
    if projection.status != projection_status:
        projection.status = projection_status
        update_fields.append("status")
    if started_at is not _UNSET and projection.started_at != started_at:
        projection.started_at = cast(datetime | None, started_at)
        update_fields.append("started_at")
    if ended_at is not _UNSET and projection.ended_at != ended_at:
        projection.ended_at = cast(datetime | None, ended_at)
        update_fields.append("ended_at")
    if output_json is not _UNSET and projection.output_json != output_json:
        projection.output_json = output_json
        update_fields.append("output_json")
    if error_json is not _UNSET and projection.error_json != error_json:
        projection.error_json = error_json
        update_fields.append("error_json")
    if projection.trace_id != trace_id:
        projection.trace_id = trace_id
        update_fields.append("trace_id")
    if projection.span_id != span_id:
        projection.span_id = span_id
        update_fields.append("span_id")
    if projection.last_event_type != event_type:
        projection.last_event_type = event_type
        update_fields.append("last_event_type")
    next_event_id = event_id or ""
    if projection.last_event_id != next_event_id:
        projection.last_event_id = next_event_id
        update_fields.append("last_event_id")
    effective_event_time = event_time or timezone.now()
    if projection.last_event_at != effective_event_time:
        projection.last_event_at = effective_event_time
        update_fields.append("last_event_at")
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's runs."""
        user = cast(User, request.user)
        runs = run_queryset_for_user(user).select_related("graph_version__graph", "queue_entry")
        runs = runs.annotate(
            failed_node_count=Count(
                "node_runs", filter=Q(node_runs__status="failed"), distinct=True
            )
        )

        status_filter = request.query_params.get("status")
        if status_filter:
            runs = runs.filter(status=status_filter)

        graph_version_filter = (request.query_params.get("graph_version_id") or "").strip()
        if graph_version_filter:
            try:
                graph_version_uuid = UUID(graph_version_filter)
            except ValueError:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="graph_version_id must be a valid UUID",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            runs = runs.filter(graph_version_id=graph_version_uuid)

        graph_id_filter = (request.query_params.get("graph_id") or "").strip()
        if graph_id_filter:
            try:
                graph_uuid = UUID(graph_id_filter)
            except ValueError:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="graph_id must be a valid UUID",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            runs = runs.filter(graph_version__graph_id=graph_uuid)

        started_after = request.query_params.get("started_after")
        if started_after:
            parsed = parse_datetime(started_after)
            if parsed is None:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="started_after must be an ISO datetime.",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            runs = runs.filter(started_at__gte=parsed)

        started_before = request.query_params.get("started_before")
        if started_before:
            parsed = parse_datetime(started_before)
            if parsed is None:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="started_before must be an ISO datetime.",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            runs = runs.filter(started_at__lte=parsed)

        has_failed_nodes_raw = (request.query_params.get("has_failed_nodes") or "").strip().lower()
        if has_failed_nodes_raw in {"1", "true", "yes"}:
            runs = runs.filter(failed_node_count__gt=0)
        elif has_failed_nodes_raw in {"0", "false", "no"}:
            runs = runs.filter(failed_node_count=0)

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
                    "memory_activity": summarize_run_memory_activity(
                        list(run.node_runs.all()),
                        include_operations=False,
                    ),
                }
            )

        serialized_data = RunListSerializer(result, many=True).data
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
            "trace_id": run.trace_id,
            "last_progress_at": run.last_progress_at,
            "last_heartbeat_at": run.last_heartbeat_at,
            "engine_instance_id": run.engine_instance_id,
            "recovery_state": run.recovery_state,
            "paused_node_id": run.paused_node_id,
            "pause_payload": redact_payload(pause_payload),
            "node_outcomes": node_outcomes,
            "agent_events": agent_events,
            "timeline": _build_run_timeline(run=run),
            "memory_activity": summarize_run_memory_activity(node_runs, include_operations=True),
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

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to start runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        rate_limit_response = _apply_rate_limit(
            scope="run_start",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return rate_limit_response
        tenant_uuid = UUID(tenant_id)
        graph_version_id = serializer.validated_data["graph_version_id"]
        input_json = serializer.validated_data.get("input_json") or {}
        thread_id = serializer.validated_data.get("thread_id")
        session_id = str(thread_id) if thread_id else None
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return input_size_response
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return active_guardrail_response

        try:
            graph_version = GraphVersion.objects.select_related("graph").get(
                id=graph_version_id,
                graph__owner__default_organization_id=tenant_uuid,
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"GraphVersion with id '{graph_version_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        entitlement_response = check_entitlements(user)
        if entitlement_response is not None:
            return entitlement_response

        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return budget_response

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

        # Prepare graph for engine (inline subgraphs, enforce memory namespace)
        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                user,
                traceparent=traceparent,
                tracestate=tracestate,
            )
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return _run_preparation_error_response(exc)
        trace_metadata = _trace_metadata_from_graph(prepared_graph)

        credential_errors = validate_prompt_credentials(prepared_graph, user)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )

        run = Run.objects.create(
            owner=user,
            graph_version=graph_version,
            thread_id=thread_id,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=input_json,
            output_json=None,
            error_message="",
            trace_id=trace_metadata["trace_id"],
        )
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
                trigger="start",
            ),
        )

        # Track memory session for cross-run buffers.
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
                "node_runs": [],
            }
            serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
            return success_response(
                serialized_data, status=status.HTTP_201_CREATED, meta={"queued": True}
            )

        # Send run to the engine
        callback_url = resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with start_backend_span(
                "runs.start",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.trigger": "start",
                },
            ):
                selected_engine_id, engine_client = get_engine_assignment(
                    run_id=str(run.id),
                    callback_url=callback_url,
                )
                with engine_client as engine:
                    engine.start_run(
                        run_id=run.id,
                        graph_json=prepared_graph,
                        input_json=input_json,
                        memory_config_json=memory_config_json,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        traceparent=trace_metadata["traceparent"],
                        tracestate=trace_metadata["tracestate"],
                    )
                    # Update status to running once engine accepts
                    run.status = "running"
                    update_fields = ["status"]
                    update_fields.extend(
                        touch_run_liveness(
                            run,
                            recovery_state=recovery_state_for_status("running"),
                            engine_instance_id=selected_engine_id,
                        )
                    )
                    run.save(update_fields=sorted(set(update_fields)))
                    record_run_started()
                    broadcast_run_updated(run)

        except EngineConnectionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_connection_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine connection failed: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except EngineExecutionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_rejected_run",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine rejected run: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to invoke runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        tenant_uuid = UUID(tenant_id)
        rate_limit_response = _apply_rate_limit(
            scope="run_invoke",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_INVOKE_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return rate_limit_response
        thread_id = serializer.validated_data["thread_id"]
        session_id = str(thread_id)
        input_json = serializer.validated_data.get("input_json") or {}
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return input_size_response

        if input_json and not isinstance(input_json, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="input_json must be a JSON object",
                status=status.HTTP_400_BAD_REQUEST,
            )

        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return budget_response

        active_run = (
            run_queryset_for_user(user)
            .filter(
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

        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return active_guardrail_response

        graph_version = latest_run.graph_version
        try:
            traceparent, tracestate = _request_trace_headers(request)
            graph_json = prepare_graph_for_engine(
                graph_version.graph_json,
                user,
                traceparent=traceparent,
                tracestate=tracestate,
            )
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return _run_preparation_error_response(exc)
        trace_metadata = _trace_metadata_from_graph(graph_json)

        credential_errors = validate_prompt_credentials(graph_json, user)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
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
                owner=user,
                graph_version=graph_version,
                thread_id=thread_id,
                status="pending",
                started_at=timezone.now(),
                ended_at=None,
                input_json=input_json,
                output_json=None,
                error_message="",
                trace_id=trace_metadata["trace_id"],
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
                "node_runs": [],
            }
            serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
            return success_response(
                serialized_data, status=status.HTTP_201_CREATED, meta={"queued": True}
            )

        callback_url = resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with start_backend_span(
                "runs.invoke",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.trigger": "invoke",
                },
            ):
                selected_engine_id, engine_client = get_engine_assignment(
                    run_id=str(run.id),
                    callback_url=callback_url,
                )
                with engine_client as engine:
                    engine.start_run(
                        run_id=run.id,
                        graph_json=graph_json,
                        input_json=input_json,
                        memory_config_json=memory_config_json,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        traceparent=trace_metadata["traceparent"],
                        tracestate=trace_metadata["tracestate"],
                    )
                    run.status = "running"
                    update_fields = ["status"]
                    update_fields.extend(
                        touch_run_liveness(
                            run,
                            recovery_state=recovery_state_for_status("running"),
                            engine_instance_id=selected_engine_id,
                        )
                    )
                    run.save(update_fields=sorted(set(update_fields)))
                    record_run_started()
                    broadcast_run_updated(run)

        except EngineConnectionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_connection_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine connection failed: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except EngineExecutionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_rejected_run",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine rejected run: {e}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            "node_runs": [],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data, status=status.HTTP_201_CREATED)


class RunReplayView(APIView):
    """Replay a completed run from its latest checkpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id: UUID) -> Response:
        serializer = RunReplaySerializer(data=request.data)
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
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to replay runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_uuid = UUID(get_tenant_id_for_user(user))
        node_id = str(serializer.validated_data.get("node_id") or "").strip()

        try:
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        if run.status in {"pending", "running", "paused"}:
            return error_response(
                code="INVALID_STATE",
                message=f"Cannot replay a run in status '{run.status}'. Run must be completed.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            checkpoint = run.checkpoint
        except RunCheckpoint.DoesNotExist:
            return error_response(
                code="NO_CHECKPOINT",
                message="No checkpoint available for this run.",
                status=status.HTTP_409_CONFLICT,
            )

        if run.thread_id:
            active_run = (
                run_queryset_for_user(user)
                .filter(
                    thread_id=run.thread_id,
                    status__in=["pending", "running", "paused"],
                )
                .order_by("-started_at")
                .first()
            )
            if active_run:
                return error_response(
                    code="INVALID_STATE",
                    message=f"Thread '{run.thread_id}' has an active run ({active_run.id}).",
                    status=status.HTTP_400_BAD_REQUEST,
                )

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return budget_response
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return active_guardrail_response

        graph_version = run.graph_version
        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                user,
                traceparent=traceparent,
                tracestate=tracestate,
            )
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return _run_preparation_error_response(exc)
        trace_metadata = _trace_metadata_from_graph(prepared_graph)

        credential_errors = validate_prompt_credentials(prepared_graph, user)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )

        replay_nodes: set[str] = set()
        if node_id:
            replay_nodes = _get_downstream_nodes(prepared_graph, node_id)
            if not replay_nodes:
                return error_response(
                    code="INVALID_NODE",
                    message=f"Node '{node_id}' was not found in the graph.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

        state_json = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        state_json = dict(state_json)
        if replay_nodes:
            state_json = _prune_state_for_nodes(state_json, replay_nodes)

        completed_nodes = list(checkpoint.completed_nodes or [])
        skipped_nodes = list(checkpoint.skipped_nodes or [])
        if replay_nodes:
            completed_nodes = [node for node in completed_nodes if node not in replay_nodes]
            skipped_nodes = [node for node in skipped_nodes if node not in replay_nodes]

        input_json = run.input_json if isinstance(run.input_json, dict) else {}
        session_id = str(run.thread_id) if run.thread_id else None
        checkpoint_graph_json = pyjson.dumps(prepared_graph)

        with transaction.atomic():
            replay_run = Run.objects.create(
                owner=user,
                graph_version=graph_version,
                thread_id=run.thread_id,
                status="pending",
                started_at=timezone.now(),
                ended_at=None,
                input_json=input_json,
                output_json=None,
                error_message="",
                trace_id=trace_metadata["trace_id"],
            )

            RunCheckpoint.objects.create(
                run=replay_run,
                node_id=checkpoint.node_id,
                step_index=checkpoint.step_index,
                state_json=state_json,
                completed_nodes=completed_nodes,
                skipped_nodes=skipped_nodes,
                graph_json=checkpoint_graph_json,
            )

            RunEvent.objects.create(
                run=replay_run,
                event_type="run.replay",
                payload={
                    "source_run_id": str(run.id),
                    "from_node_id": node_id or None,
                    "checkpoint_step": checkpoint.step_index,
                },
                trace_id=trace_metadata["trace_id"],
                span_id=trace_metadata["span_id"],
            )

        broadcast_run_updated(replay_run)
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="run.replayed",
            resource_type="run",
            resource_id=str(replay_run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=replay_run.thread_id,
                trigger="replay",
                extra={
                    "source_run_id": str(run.id),
                    "from_node_id": node_id or None,
                },
            ),
        )
        upsert_memory_session(user, session_id)

        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            queue_entry = enqueue_run(replay_run, tenant_id=get_tenant_id_for_user(user))
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
                "node_runs": [],
            }
            serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
            return success_response(
                serialized_data, status=status.HTTP_201_CREATED, meta={"queued": True}
            )

        callback_url = resolve_engine_callback_url(run_id=str(replay_run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with start_backend_span(
                "runs.replay",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(replay_run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.trigger": "replay",
                },
            ):
                selected_engine_id, engine_client = get_engine_assignment(
                    run_id=str(replay_run.id),
                    callback_url=callback_url,
                )
                with engine_client as engine:
                    engine.start_run(
                        run_id=replay_run.id,
                        graph_json=prepared_graph,
                        input_json=input_json,
                        memory_config_json=memory_config_json,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        traceparent=trace_metadata["traceparent"],
                        tracestate=trace_metadata["tracestate"],
                    )
                    replay_run.status = "running"
                    update_fields = ["status"]
                    update_fields.extend(
                        touch_run_liveness(
                            replay_run,
                            recovery_state=recovery_state_for_status("running"),
                            engine_instance_id=selected_engine_id,
                        )
                    )
                    replay_run.save(update_fields=sorted(set(update_fields)))
                    record_run_started()
                    broadcast_run_updated(replay_run)

        except EngineConnectionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_connection_failed",
                run_id=str(replay_run.id),
                trace_id=replay_run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            replay_run.status = "failed"
            replay_run.ended_at = timezone.now()
            replay_run.error_message = f"Engine connection failed: {e}"
            replay_run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", replay_run.duration_ms)
            broadcast_run_updated(replay_run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except EngineExecutionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_rejected_replay",
                run_id=str(replay_run.id),
                trace_id=replay_run.trace_id or trace_metadata["trace_id"],
                error_message=str(e),
            )
            replay_run.status = "failed"
            replay_run.ended_at = timezone.now()
            replay_run.error_message = f"Engine rejected run: {e}"
            replay_run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", replay_run.duration_ms)
            broadcast_run_updated(replay_run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            "node_runs": [],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data, status=status.HTTP_201_CREATED)


class RunCancelView(APIView):
    """Cancel a run."""

    permission_classes = [IsAuthenticated]

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

        run.status = "canceled"
        run.ended_at = timezone.now()
        if not run.error_message:
            run.error_message = "Canceled by user."

        run.save(update_fields=["status", "started_at", "ended_at", "error_message"])
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
            "node_runs": [
                _serialize_node_run_for_detail(node_run=node_run) for node_run in node_runs
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data)


class RunResumeView(APIView):
    """Resume a paused run (human gate approval/rejection)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id: UUID) -> Response:
        """Resume a paused run with human decision."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to resume runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
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
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
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
        log_event(
            logger,
            logging.INFO,
            "runs_resume_requested",
            run_id=str(run.id),
            trace_id=run.trace_id or None,
            node_id=node_id,
            message="Received run resume request",
        )

        pending_approval_task = run.approval_tasks.filter(node_id=node_id, status="pending").first()
        if pending_approval_task is None:
            resolved_task = (
                run.approval_tasks.filter(node_id=node_id)
                .exclude(status="pending")
                .order_by("-resolved_at", "-created_at")
                .first()
            )
            if resolved_task is not None:
                if resolved_task.result == input_json:
                    return success_response(
                        {"resumed": True, "run_id": str(run.id), "duplicate": True}
                    )
                return error_response(
                    code="DECISION_ALREADY_RESOLVED",
                    message="Approval task for this node has already been resolved.",
                    status=status.HTTP_409_CONFLICT,
                )

        # Verify node_id matches paused node
        if run.paused_node_id and run.paused_node_id != node_id:
            return error_response(
                code="INVALID_NODE",
                message=f"Node '{node_id}' does not match paused node '{run.paused_node_id}'",
                status=status.HTTP_400_BAD_REQUEST,
            )

        entitlement_response = check_entitlements(user)
        if entitlement_response is not None:
            return entitlement_response

        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return budget_response

        # Call engine ResumeRun
        try:
            traceparent, tracestate = _request_trace_headers(request)
            trace_context = ensure_trace_context(
                traceparent=traceparent,
                tracestate=tracestate,
                trace_id=run.trace_id or None,
            )
            if not run.trace_id:
                run.trace_id = trace_context["trace_id"]
                run.save(update_fields=["trace_id"])
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
                        input_json=input_json,
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
                engine_instance_id=selected_engine_id,
                message="Dispatched run resume to engine",
            )
        except EngineConnectionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_connection_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_context["trace_id"],
                error_message=str(e),
            )
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except EngineExecutionError as e:
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_context["trace_id"],
                error_message=str(e),
            )
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        liveness_fields = touch_run_liveness(
            run,
            recovery_state=recovery_state_for_status(run.status),
            engine_instance_id=selected_engine_id,
        )
        run.save(update_fields=sorted(set(liveness_fields)))

        # Update ApprovalTask
        approval_task = pending_approval_task
        if approval_task:
            approved = input_json.get("approved", True)
            approval_task.status = "approved" if approved else "rejected"
            approval_task.result = input_json
            approval_task.resolved_at = timezone.now()
            approval_task.save(update_fields=["status", "result", "resolved_at"])
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
                },
            )

        log_event(
            logger,
            logging.INFO,
            "runs_resume_completed",
            run_id=str(run.id),
            trace_id=run.trace_id or trace_context["trace_id"],
            node_id=node_id,
            message="Run resume request completed",
        )
        return success_response({"resumed": True, "run_id": str(run.id)})


class EngineRunEventsView(APIView):
    """Persist + broadcast engine execution events (S2S).

    Events never mutate durable state directly. The backend validates, deduplicates,
    enforces monotonicity/ownership rules, and then performs durable writes.
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        timestamp_header = request.headers.get("X-Forgegraph-Timestamp", "")
        signature_header = request.headers.get("X-Forgegraph-Signature", "")
        ok, reason = s2s.verify_request(
            timestamp_ms=timestamp_header,
            signature=signature_header,
            body=request.body or b"",
        )
        if not ok:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/engine-callback-unauthorized",
                title="Unauthorized",
                status=status.HTTP_401_UNAUTHORIZED,
                detail=f"Engine callback verification failed: {reason}",
            )

        incoming_payload = unwrap_engine_event(request.data)
        serializer = EngineExecutionEventSerializer(data=incoming_payload)
        if not serializer.is_valid():
            return problem_response(
                type_uri="https://forgegraph.dev/problems/engine-callback-validation",
                title="Invalid engine callback payload",
                status=status.HTTP_400_BAD_REQUEST,
                detail="The request contains invalid fields.",
                extensions={
                    "errors": [
                        {"field": field, "issue": ", ".join(errors)}
                        for field, errors in serializer.errors.items()
                    ]
                },
            )

        event = serializer.validated_data
        run_id = event.get("run_id")
        try:
            run = Run.objects.get(id=run_id)
        except Run.DoesNotExist:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/run-not-found",
                title="Run not found",
                status=status.HTTP_404_NOT_FOUND,
                detail=f"Run with id '{run_id}' not found.",
            )
        trace_context = ensure_trace_context(
            traceparent=str(
                event.get("traceparent")
                or request.headers.get("traceparent")
                or request.headers.get("Traceparent")
                or ""
            ).strip()
            or None,
            tracestate=str(
                event.get("tracestate")
                or request.headers.get("tracestate")
                or request.headers.get("Tracestate")
                or ""
            ).strip()
            or None,
            trace_id=run.trace_id or None,
        )
        if not run.trace_id:
            run.trace_id = trace_context["trace_id"]
            run.save(update_fields=["trace_id"])

        tenant_id = str(event.get("tenant_id"))
        expected_tenant_id = get_tenant_id_for_run(run)
        if tenant_id != expected_tenant_id:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/tenant-mismatch",
                title="Tenant mismatch",
                status=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch for run event.",
            )

        event_id = event.get("event_id")
        if event_id and RunEvent.objects.filter(run=run, external_id=event_id).exists():
            return success_response({"received": True, "duplicate": True})

        event_type = event.get("type", "")
        timestamp_ms = event.get("timestamp")
        event_time = _datetime_from_timestamp_ms(timestamp_ms)
        normalized_category = normalize_event_category(
            str(event_type),
            category=str(event.get("category") or ""),
        )

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
            return problem_response(
                type_uri="https://forgegraph.dev/problems/engine-instance-mismatch",
                title="Engine instance mismatch",
                status=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )

        if assigned_engine and callback_engine_instance_id != run.engine_instance_id:
            run.engine_instance_id = callback_engine_instance_id
            run.save(update_fields=["engine_instance_id"])

        def _save_event(
            event_type_name: str,
            payload: dict[str, Any],
            *,
            derived: bool = False,
        ) -> None:
            normalized_payload = dict(payload)
            normalized_payload["category"] = normalize_event_category(
                event_type_name,
                category=str(normalized_payload.get("category") or ""),
                payload=normalized_payload,
            )
            try:
                RunEvent.objects.create(
                    run=run,
                    event_type=event_type_name,
                    payload=normalized_payload,
                    external_id=None if derived else event_id,
                    trace_id=trace_context["trace_id"],
                    span_id=trace_context["span_id"],
                )
            except IntegrityError:
                log_event(
                    logger,
                    logging.INFO,
                    "duplicate_run_event_ignored",
                    run_id=str(run.id),
                    trace_id=trace_context["trace_id"],
                    event_id=event_id,
                    message="Duplicate run event ignored",
                )

        if event_type == "run.schema_validation":
            payload = redact_payload(event.get("output") or {})
            run_update_fields = touch_run_liveness(
                run,
                event_time=event_time,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=callback_engine_instance_id,
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            _save_event("run.schema_validation", payload)
            message = broadcast_run_schema_validation(run=run, payload=payload)
            return success_response(message)

        if event_type == "node_stream_chunk":
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
            _save_event("node_stream.chunk", stream_payload)
            if agent_chunk:
                _save_event(
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
            run_update_fields = touch_run_liveness(
                run,
                event_time=event_time,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=callback_engine_instance_id,
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            message = broadcast_node_stream_chunk(run=run, payload=stream_payload)
            return success_response(message)

        if event_type in {
            "run_started",
            "run_completed",
            "run_failed",
            "run_paused",
            "run_resumed",
            "run_canceled",
        }:
            previous_status = run.status
            run_payload: dict[str, Any] = {}
            update_fields: list[str] = []
            pause_payload: dict[str, Any] = {}
            node_id = ""
            projection_kwargs: dict[str, Any] = {}

            if event_type == "run_started":
                run_payload["status"] = "running"
                run.status = "running"
                update_fields.append("status")
                if event_time:
                    run_payload["started_at"] = event_time
                    run.started_at = event_time
                    update_fields.append("started_at")
                projection_kwargs = {
                    "started_at": event_time,
                }

            if event_type == "run_completed":
                run_payload["status"] = "succeeded"
                run.status = "succeeded"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")
                if "output" in event:
                    redacted_output = redact_payload(event.get("output"))
                    run_payload["output_json"] = redacted_output
                    run.output_json = redacted_output
                    update_fields.append("output_json")
                projection_kwargs = {
                    "ended_at": event_time,
                    "output_json": run_payload.get("output_json", _UNSET),
                }

            if event_type == "run_failed":
                run_payload["status"] = "failed"
                run.status = "failed"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")
                error_message = redact_payload(event.get("error") or "")
                run_payload["error_message"] = error_message
                run.error_message = error_message
                update_fields.append("error_message")
                projection_kwargs = {
                    "ended_at": event_time,
                    "error_message": error_message,
                }

            if event_type == "run_canceled":
                run_payload["status"] = "canceled"
                run.status = "canceled"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")
                projection_kwargs = {
                    "ended_at": event_time,
                }

            if event_type == "run_paused":
                run_payload["status"] = "paused"
                run.status = "paused"
                update_fields.append("status")
                node_id = str(event.get("node_id") or "")
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
                projection_kwargs = {
                    "paused_node_id": node_id or None,
                    "pause_state_json": (
                        persisted_pause_state if persisted_pause_state is not None else _UNSET
                    ),
                }

            if event_type == "run_resumed":
                run_payload["status"] = "running"
                run.status = "running"
                update_fields.append("status")
                run_payload["paused_node_id"] = None
                run.paused_node_id = None
                update_fields.append("paused_node_id")
                run_payload["pause_state_json"] = None
                run.pause_state_json = None
                update_fields.append("pause_state_json")
                projection_kwargs = {
                    "paused_node_id": None,
                    "pause_state_json": None,
                }

            if update_fields:
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

            final_run_stream_summaries: list[dict[str, Any]] = []
            if event_type in {"run_completed", "run_failed", "run_canceled", "run_paused"}:
                final_run_stream_summaries = flush_all_stream_summaries(
                    run_id=str(run.id),
                    final_reason=event_type,
                )

            _project_run_event_state(
                run=run,
                projection_status=run.status,
                trace_id=trace_context["trace_id"],
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                **projection_kwargs,
            )

            if event_type == "run_paused" and node_id:
                _project_pause_state(
                    run=run,
                    node_id=node_id,
                    node_type=str(event.get("node_type") or ""),
                    attempt=int(event.get("attempt") or 1),
                    pause_payload=pause_payload if isinstance(pause_payload, dict) else {},
                    trace_id=trace_context["trace_id"],
                    span_id=trace_context["span_id"],
                    event_time=event_time,
                )
                _project_node_event_state(
                    run=run,
                    node_id=node_id,
                    node_type=str(event.get("node_type") or "human_gate"),
                    attempt=int(event.get("attempt") or 1),
                    projection_status="waiting",
                    trace_id=trace_context["trace_id"],
                    span_id=trace_context["span_id"],
                    event_type=event_type,
                    event_id=event_id,
                    event_time=event_time,
                    started_at=event_time,
                    output_json={"pause_payload": pause_payload} if pause_payload else _UNSET,
                )

            if event_type == "run_started" and previous_status != "running":
                record_run_started()
            if event_type in {
                "run_completed",
                "run_failed",
                "run_canceled",
            } and previous_status not in {
                "succeeded",
                "failed",
                "canceled",
            }:
                record_run_completed(run.status, run.duration_ms)

            _save_event("run.updated", _serialize_event_payload(redact_payload(run_payload)))
            for summary_payload in final_run_stream_summaries:
                broadcast_node_stream_summary(run=run, payload=summary_payload)
            message = broadcast_run_updated(run)
            return success_response(message)

        if event_type in {
            "node_started",
            "node_completed",
            "node_failed",
            "node_skipped",
            "node_retrying",
        }:
            node_id = event.get("node_id") or ""
            node_type = event.get("node_type") or ""
            attempt = int(event.get("attempt") or 1)
            node_payload: dict[str, Any] = {
                "node_id": node_id,
                "node_type": node_type,
                "attempt": attempt,
                "trace_id": trace_context["trace_id"],
                "span_id": trace_context["span_id"],
            }

            if event_type == "node_started":
                node_payload["status"] = "running"
                if event_time:
                    node_payload["started_at"] = event_time
            elif event_type == "node_completed":
                node_payload["status"] = "succeeded"
                if event_time:
                    node_payload["ended_at"] = event_time
                node_payload["output_json"] = redact_payload(event.get("output"))
            elif event_type == "node_failed":
                node_payload["status"] = "failed"
                if event_time:
                    node_payload["ended_at"] = event_time
                error_message = redact_payload(event.get("error") or "")
                error_json: dict[str, Any] = {}
                output_payload = redact_payload(event.get("output") or {})
                if isinstance(output_payload, dict):
                    structured_error = output_payload.get("error")
                    if isinstance(structured_error, dict):
                        error_json = dict(structured_error)
                if not error_json:
                    error_json = {"error": error_message}
                elif error_message:
                    error_json.setdefault("error", error_message)
                node_payload["error_json"] = error_json
            elif event_type == "node_skipped":
                node_payload["status"] = "skipped"
                if event_time:
                    node_payload["ended_at"] = event_time
            elif event_type == "node_retrying":
                node_payload["status"] = "running"

            with transaction.atomic():
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

                if "started_at" in node_payload:
                    node_run.started_at = node_payload["started_at"]
                    node_update_fields.append("started_at")
                if "ended_at" in node_payload:
                    node_run.ended_at = node_payload["ended_at"]
                    node_update_fields.append("ended_at")
                if "output_json" in node_payload:
                    node_run.output_json = node_payload["output_json"]
                    node_update_fields.append("output_json")
                if "error_json" in node_payload:
                    node_run.error_json = node_payload["error_json"]
                    node_update_fields.append("error_json")
                node_run.trace_id = trace_context["trace_id"]
                node_run.span_id = trace_context["span_id"]
                node_update_fields.extend(["trace_id", "span_id"])

                node_run.save(update_fields=sorted(set(node_update_fields)))
                run_update_fields = touch_run_liveness(
                    run,
                    event_time=event_time,
                    recovery_state=recovery_state_for_status(run.status),
                    engine_instance_id=callback_engine_instance_id,
                )
                run.save(update_fields=sorted(set(run_update_fields)))
                if event_type == "node_failed" and _payload_contains_policy_denied(
                    node_payload.get("error_json")
                ):
                    record_audit_log(
                        actor=None,
                        tenant_id=get_tenant_id_for_run(run),
                        action="run.policy_denied",
                        resource_type="node_run",
                        resource_id=str(node_run.id),
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
                    node_type=node_run.node_type,
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
                _save_event(
                    "node_run.updated", _serialize_event_payload(redact_payload(node_payload))
                )

                usage_payload = _extract_llm_usage_payload(
                    node_type=node_type,
                    output_json=node_payload.get("output_json"),
                )
                if node_type in {"prompt", "agent"} and usage_payload:
                    prompt_tokens = usage_payload["prompt_tokens"]
                    completion_tokens = usage_payload["completion_tokens"]
                    total_tokens = usage_payload["total_tokens"]
                    model = usage_payload["model"]
                    provider = usage_payload["provider"]
                    if prompt_tokens or completion_tokens or total_tokens:
                        tenant_id = get_tenant_id_for_run(run)
                        cost = calculate_cost(provider, model, prompt_tokens, completion_tokens)
                        LLMUsage.objects.create(
                            tenant_id=tenant_id,
                            run=run,
                            node_id=node_id,
                            provider=provider,
                            model=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                            cost_usd=cost,
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
            message = broadcast_node_run_updated(run=run, node_run=node_run)
            return success_response(message)

        return problem_response(
            type_uri="https://forgegraph.dev/problems/unknown-engine-event",
            title="Unknown engine event",
            status=status.HTTP_400_BAD_REQUEST,
            detail="Unknown event type.",
        )


class RunEventsView(APIView):
    """Persist + broadcast Run/NodeRun delta events.

    These authenticated events are write requests, not authoritative state by themselves.
    """

    permission_classes = [IsAuthenticated]

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
            payload = serializer.validated_data["run"]
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

            # Handle pause_state fields for human gate
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

            schema_errors: list[dict[str, Any]] | None = None
            if output_schema and payload.get("status") == "succeeded" and "output_json" in payload:
                try:
                    schema_errors = validate_json_schema(payload.get("output_json"), output_schema)
                except SchemaError as exc:
                    log_event(
                        logger,
                        logging.WARNING,
                        "run_output_schema_invalid",
                        run_id=str(run.id),
                        trace_id=run.trace_id,
                        error_message=str(exc),
                    )

            if schema_errors:
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

                if schema_mode == "strict":
                    run.status = "failed"
                    run.error_message = (
                        f"Output schema validation failed: {schema_errors[0]['message']}"
                    )
                    run.save(
                        update_fields=[
                            "status",
                            "error_message",
                        ]
                    )
                    payload["status"] = run.status
                    payload["error_message"] = run.error_message

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

                node_update_fields: list[str] = []

                if not created and node_run.node_type != node_type:
                    node_run.node_type = node_type
                    node_update_fields.append("node_type")

                node_run.status = payload["status"]
                node_update_fields.append("status")

                if "started_at" in payload:
                    node_run.started_at = payload["started_at"]
                    node_update_fields.append("started_at")
                if "ended_at" in payload:
                    node_run.ended_at = payload["ended_at"]
                    node_update_fields.append("ended_at")
                if "input_json" in payload:
                    node_run.input_json = redact_payload(payload["input_json"])
                    payload["input_json"] = node_run.input_json
                    node_update_fields.append("input_json")
                if "output_json" in payload:
                    node_run.output_json = redact_payload(payload["output_json"])
                    payload["output_json"] = node_run.output_json
                    node_update_fields.append("output_json")
                if "error_json" in payload:
                    node_run.error_json = redact_payload(payload["error_json"])
                    payload["error_json"] = node_run.error_json
                    node_update_fields.append("error_json")

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

            message = broadcast_node_run_updated(run=run, node_run=node_run)
            return success_response(message)

        if event_type == "run.schema_validation":
            payload = redact_payload(serializer.validated_data.get("payload") or {})
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

            message = broadcast_run_schema_validation(run=run, payload=payload)
            return success_response(message)

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


def _get_user_from_request(request: Request) -> User | None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return cast(User, user)

    token = request.query_params.get("token")
    if not token:
        return None

    access_token = validate_access_token(cast(Any, token))
    if access_token is None:
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

        def event_stream() -> Any:
            yield _format_sse(
                {
                    "type": "connected",
                    "run_id": str(run.id),
                    "timestamp": timezone.now().isoformat(),
                    "level": requested_level,
                },
                event_name="connected",
            )

            if since:
                for event in RunEvent.objects.filter(run=run, created_at__gt=since).order_by(
                    "created_at"
                ):
                    message = _build_stream_message(run=run, event=event)
                    if not message_allowed_for_level(message, requested_level):
                        continue
                    yield _format_sse(message, event_name=event.event_type)

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
                for group_name in group_names:
                    async_to_sync(channel_layer.group_discard)(group_name, channel_name)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response
