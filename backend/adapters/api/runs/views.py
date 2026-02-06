"""
Runs API views.

Clean Architecture: Interface Adapters layer.
"""

import asyncio
import copy
import json as pyjson
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models import Case, IntegerField, Prefetch, Sum, When
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
    broadcast_node_stream_chunk,
    broadcast_node_run_updated,
    broadcast_run_schema_validation,
    broadcast_run_updated,
)
from application.services.audit_log import record_audit_log
from application.services.llm_pricing import calculate_cost
from application.services.rate_limit import check_rate_limit, rate_limit_response_payload
from application.services.rbac import has_min_role
from application.services.schema_validation import (
    SchemaError,
    extract_schema_metadata,
    validate_json_schema,
)
from application.services.tenancy import get_tenant_id_for_user as resolve_tenant_id_for_user
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    Graph,
    GraphVersion,
    LLMBudget,
    LLMQuota,
    LLMUsage,
    MemoryConfiguration,
    MemorySession,
    NodeRun,
    Run,
    RunCheckpoint,
    RunEvent,
    TenantPolicy,
    TenantSubscription,
    User,
)
from infrastructure.security import s2s

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
    user = cast(User, request.user)
    return get_tenant_id_for_user(user)


def get_tenant_id_for_user(user: User) -> str:
    return resolve_tenant_id_for_user(user)


def get_tenant_id_for_run(run: Run) -> str:
    return get_tenant_id_for_user(run.owner)


def run_queryset_for_user(user: User) -> models.QuerySet[Run]:
    tenant_id = get_tenant_id_for_user(user)
    tenant_uuid = UUID(tenant_id)
    return Run.objects.filter(owner__default_organization_id=tenant_uuid)


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
        )

    if quota.monthly_cost_limit_usd and total_cost >= quota.monthly_cost_limit_usd:
        return error_response(
            code="QUOTA_EXCEEDED",
            message="Monthly LLM cost quota exceeded. Increase your quota or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
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


def get_memory_config_for_graph(graph: Graph, user: User) -> MemoryConfiguration | None:
    if hasattr(graph, "memory_config") and graph.memory_config:
        return graph.memory_config
    default_config = MemoryConfiguration.objects.filter(user=user).first()
    if default_config:
        return default_config
    return None


def build_memory_config_json(graph: Graph, user: User, session_id: str | None = None) -> str:
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


def upsert_memory_session(user: User, session_id: str | None, ttl_hours: int = 24) -> None:
    if not session_id:
        return
    expires_at = timezone.now() + timedelta(hours=ttl_hours)
    MemorySession.objects.update_or_create(
        session_id=session_id,
        defaults={"owner": user, "expires_at": expires_at},
    )


START_NODE_ID = "START"
END_NODE_ID = "END"


def strip_sentinel_edges(graph_json: dict[str, Any]) -> dict[str, Any]:
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


def expand_subgraphs(graph_json: dict[str, Any], owner: User) -> dict[str, Any]:
    """Inline subgraph graph_json for subgraph nodes."""
    if not isinstance(graph_json, dict):
        return graph_json

    tenant_id = get_tenant_id_for_user(owner)
    tenant_uuid = UUID(tenant_id)
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
                .filter(
                    id=graph_version_id,
                    graph__owner__default_organization_id=tenant_uuid,
                )
                .first()
            )
        elif graph_id:
            graph_version = (
                GraphVersion.objects.select_related("graph")
                .filter(
                    graph_id=graph_id,
                    graph__owner__default_organization_id=tenant_uuid,
                )
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


def apply_memory_namespace_prefix(
    graph_json: dict[str, Any], owner_id: UUID | str
) -> dict[str, Any]:
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


def prepare_graph_for_engine(graph_json: dict[str, Any], owner: User) -> dict[str, Any]:
    """Prepare graph JSON for engine execution (strip sentinels, expand subgraphs, enforce memory isolation)."""
    cleaned = strip_sentinel_edges(graph_json)
    expanded = expand_subgraphs(cleaned, owner)
    namespaced = apply_memory_namespace_prefix(expanded, owner.id)
    policy = TenantPolicy.objects.filter(tenant_id=get_tenant_id_for_user(owner)).first()
    if policy:
        metadata_raw = namespaced.get("metadata")
        metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
        metadata["policy"] = {
            "http": {
                "allowlist": policy.http_allowlist,
                "denylist": policy.http_denylist,
                "default_deny": policy.http_default_deny,
            },
            "llm": {
                "allowed_providers": policy.allowed_providers,
                "allowed_models": policy.allowed_models,
            },
        }
        namespaced["metadata"] = metadata
    return namespaced


def validate_prompt_credentials(graph_json: dict[str, Any], user: User) -> list[dict[str, Any]]:
    allowed_providers = set(getattr(settings, "ALLOWED_LLM_PROVIDERS", ["openai", "anthropic"]))
    policy = TenantPolicy.objects.filter(tenant_id=get_tenant_id_for_user(user)).first()
    allowed_policy_providers = (
        {str(value).lower() for value in policy.allowed_providers} if policy else set()
    )
    allowed_policy_models = {str(value) for value in policy.allowed_models} if policy else set()
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return []

    errors: list[dict[str, Any]] = []
    prompt_nodes: list[tuple[str, str, str]] = []
    credential_ids: set[str] = set()

    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") != "prompt":
            continue

        node_id = str(node.get("id") or "prompt")
        config_raw = node.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}
        provider = str(config.get("provider") or "").strip().lower()
        credential_id = str(config.get("credential_id") or "").strip()

        if provider and provider not in allowed_providers:
            errors.append(
                {
                    "field": "provider",
                    "message": f"Prompt node '{node_id}' uses unsupported provider '{provider}'.",
                    "suggestion": f"Use one of: {', '.join(sorted(allowed_providers))}.",
                }
            )
        if allowed_policy_providers and provider and provider not in allowed_policy_providers:
            errors.append(
                {
                    "field": "provider",
                    "message": f"Prompt node '{node_id}' uses a provider blocked by policy.",
                    "suggestion": f"Use one of: {', '.join(sorted(allowed_policy_providers))}.",
                }
            )

        model = str(config.get("model") or "").strip()
        if allowed_policy_models and model and model not in allowed_policy_models:
            errors.append(
                {
                    "field": "model",
                    "message": f"Prompt node '{node_id}' uses a model blocked by policy.",
                    "suggestion": f"Use one of: {', '.join(sorted(allowed_policy_models))}.",
                }
            )

        if not credential_id:
            errors.append(
                {
                    "field": "credential_id",
                    "message": f"Prompt node '{node_id}' is missing a credential.",
                    "suggestion": "Select a credential for each prompt node before running.",
                }
            )
            continue

        credential_ids.add(credential_id)
        prompt_nodes.append((node_id, provider, credential_id))

    if not credential_ids:
        return errors

    credentials = APIKey.objects.filter(
        id__in=credential_ids,
        organization=user.default_organization,
    )
    credential_map = {str(credential.id): credential for credential in credentials}

    for node_id, provider, credential_id in prompt_nodes:
        credential = credential_map.get(credential_id)
        if credential is None:
            errors.append(
                {
                    "field": "credential_id",
                    "message": f"Credential '{credential_id}' for node '{node_id}' was not found.",
                    "suggestion": "Select a credential available to your organization for this node.",
                }
            )
            continue
        if provider and provider != credential.provider:
            errors.append(
                {
                    "field": "provider",
                    "message": f"Provider mismatch for node '{node_id}'.",
                    "suggestion": f"Choose a {credential.provider} provider or update the credential.",
                }
            )

    return errors


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


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's runs."""
        user = cast(User, request.user)
        runs = run_queryset_for_user(user).select_related("graph_version__graph")

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
            prepared_graph = prepare_graph_for_engine(graph_version.graph_json, user)
        except ValueError as exc:
            return error_response(
                code="INVALID_SUBGRAPH",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        )
        broadcast_run_updated(run)
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="run.started",
            resource_type="run",
            resource_id=str(run.id),
            metadata={"graph_id": str(graph_version.graph_id)},
        )

        # Track memory session for cross-run buffers.
        upsert_memory_session(user, session_id)

        # Send run to the engine
        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=run.id)
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
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

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to invoke runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
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

        graph_version = latest_run.graph_version
        try:
            graph_json = prepare_graph_for_engine(graph_version.graph_json, user)
        except ValueError as exc:
            return error_response(
                code="INVALID_SUBGRAPH",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            metadata={"graph_id": str(graph_version.graph_id)},
        )

        upsert_memory_session(user, session_id)

        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=run.id)
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
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

        graph_version = run.graph_version
        try:
            prepared_graph = prepare_graph_for_engine(graph_version.graph_json, user)
        except ValueError as exc:
            return error_response(
                code="INVALID_SUBGRAPH",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            )

        broadcast_run_updated(replay_run)
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="run.replayed",
            resource_type="run",
            resource_id=str(replay_run.id),
            metadata={"source_run_id": str(run.id), "from_node_id": node_id or None},
        )
        upsert_memory_session(user, session_id)

        callback_url = settings.ENGINE_CALLBACK_URL.format(run_id=replay_run.id)
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
        )
        tenant_id = get_tenant_id(request)
        try:
            with get_engine_client(callback_url) as engine:
                engine.start_run(
                    run_id=replay_run.id,
                    graph_json=prepared_graph,
                    input_json=input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=tenant_id,
                    session_id=session_id,
                )
                replay_run.status = "running"
                replay_run.save(update_fields=["status"])
                broadcast_run_updated(replay_run)

        except EngineConnectionError as e:
            logger.error(f"Engine connection failed for replay {replay_run.id}: {e}")
            replay_run.status = "failed"
            replay_run.ended_at = timezone.now()
            replay_run.error_message = f"Engine connection failed: {e}"
            replay_run.save(update_fields=["status", "ended_at", "error_message"])
            broadcast_run_updated(replay_run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except EngineExecutionError as e:
            logger.error(f"Engine rejected replay {replay_run.id}: {e}")
            replay_run.status = "failed"
            replay_run.ended_at = timezone.now()
            replay_run.error_message = f"Engine rejected run: {e}"
            replay_run.save(update_fields=["status", "ended_at", "error_message"])
            broadcast_run_updated(replay_run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        run_data = {
            "id": replay_run.id,
            "owner_id": replay_run.owner_id,
            "thread_id": replay_run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": replay_run.status,
            "started_at": replay_run.started_at,
            "ended_at": replay_run.ended_at,
            "input_json": replay_run.input_json,
            "output_json": replay_run.output_json,
            "error_message": replay_run.error_message,
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

        return success_response({"resumed": True, "run_id": str(run.id)})


class EngineRunEventsView(APIView):
    """Persist + broadcast engine execution events (S2S)."""

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
            return Response(
                {"detail": "Unauthorized", "reason": reason}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = EngineExecutionEventSerializer(data=request.data)
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

        event = serializer.validated_data
        run_id = event.get("run_id")
        try:
            run = Run.objects.get(id=run_id)
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        tenant_id = str(event.get("tenant_id"))
        expected_tenant_id = get_tenant_id_for_run(run)
        if tenant_id != expected_tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Tenant mismatch for run event",
                status=status.HTTP_403_FORBIDDEN,
            )

        event_id = event.get("event_id")
        if event_id and RunEvent.objects.filter(run=run, external_id=event_id).exists():
            return success_response({"received": True, "duplicate": True})

        event_type = event.get("type", "")
        timestamp_ms = event.get("timestamp")
        event_time = _datetime_from_timestamp_ms(timestamp_ms)

        def _save_event(event_type_name: str, payload: dict[str, Any]) -> None:
            try:
                RunEvent.objects.create(
                    run=run,
                    event_type=event_type_name,
                    payload=payload,
                    external_id=event_id,
                )
            except IntegrityError:
                logger.info(
                    "Duplicate run event ignored",
                    extra={
                        "run_id": str(run.id),
                        "event_id": event_id,
                        "event_type": event_type_name,
                    },
                )

        if event_type == "run.schema_validation":
            payload = event.get("output") or {}
            _save_event("run.schema_validation", payload)
            message = broadcast_run_schema_validation(run=run, payload=payload)
            return success_response(message)

        if event_type == "node_stream_chunk":
            output = event.get("output")
            payload = output if isinstance(output, dict) else {}
            chunk = str(payload.get("chunk") or "")
            node_payload = {
                "node_id": str(event.get("node_id") or ""),
                "node_type": str(event.get("node_type") or ""),
                "attempt": int(event.get("attempt") or 1),
                "chunk": chunk,
                "chunk_index": int(payload.get("chunk_index") or 0),
            }
            _save_event("node_stream.chunk", node_payload)
            message = broadcast_node_stream_chunk(run=run, payload=node_payload)
            return success_response(message)

        if event_type in {
            "run_started",
            "run_completed",
            "run_failed",
            "run_paused",
            "run_resumed",
            "run_canceled",
        }:
            run_payload: dict[str, Any] = {}
            update_fields: list[str] = []

            if event_type == "run_started":
                run_payload["status"] = "running"
                run.status = "running"
                update_fields.append("status")
                if event_time:
                    run_payload["started_at"] = event_time
                    run.started_at = event_time
                    update_fields.append("started_at")

            if event_type == "run_completed":
                run_payload["status"] = "succeeded"
                run.status = "succeeded"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")
                if "output" in event:
                    run_payload["output_json"] = event.get("output")
                    run.output_json = event.get("output")
                    update_fields.append("output_json")

            if event_type == "run_failed":
                run_payload["status"] = "failed"
                run.status = "failed"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")
                error_message = event.get("error") or ""
                run_payload["error_message"] = error_message
                run.error_message = error_message
                update_fields.append("error_message")

            if event_type == "run_canceled":
                run_payload["status"] = "canceled"
                run.status = "canceled"
                update_fields.append("status")
                if event_time:
                    run_payload["ended_at"] = event_time
                    run.ended_at = event_time
                    update_fields.append("ended_at")

            if event_type == "run_paused":
                run_payload["status"] = "paused"
                run.status = "paused"
                update_fields.append("status")
                node_id = event.get("node_id") or ""
                if node_id:
                    run_payload["paused_node_id"] = node_id
                    run.paused_node_id = node_id
                    update_fields.append("paused_node_id")
                pause_payload = event.get("output") or {}
                run_payload["pause_payload"] = pause_payload
                if pause_payload:
                    run_payload["pause_state_json"] = pause_payload
                    run.pause_state_json = pause_payload
                    update_fields.append("pause_state_json")

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

            if update_fields:
                run.save(update_fields=sorted(set(update_fields)))

            _save_event("run.updated", _serialize_event_payload(run_payload))
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
            }

            if event_type == "node_started":
                node_payload["status"] = "running"
                if event_time:
                    node_payload["started_at"] = event_time
            elif event_type == "node_completed":
                node_payload["status"] = "succeeded"
                if event_time:
                    node_payload["ended_at"] = event_time
                node_payload["output_json"] = event.get("output")
            elif event_type == "node_failed":
                node_payload["status"] = "failed"
                if event_time:
                    node_payload["ended_at"] = event_time
                error_message = event.get("error") or ""
                node_payload["error_json"] = {"error": error_message}
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

                node_run.save(update_fields=sorted(set(node_update_fields)))
                _save_event("node_run.updated", _serialize_event_payload(node_payload))

                if node_type == "prompt" and node_payload.get("output_json"):
                    output_json = node_payload.get("output_json") or {}
                    usage = output_json.get("usage") or {}
                    prompt_tokens = int(usage.get("prompt_tokens") or 0)
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                    total_tokens = int(usage.get("total_tokens") or 0)
                    model = str(output_json.get("model") or "")
                    provider = str(output_json.get("provider") or "openai")
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

            message = broadcast_node_run_updated(run=run, node_run=node_run)
            return success_response(message)

        return error_response(
            code="VALIDATION_ERROR",
            message="Unknown event type",
            status=status.HTTP_400_BAD_REQUEST,
        )


class RunEventsView(APIView):
    """Persist + broadcast Run/NodeRun delta events."""

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

            schema_errors: list[dict[str, Any]] | None = None
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
                    node_run.input_json = payload["input_json"]
                    node_update_fields.append("input_json")
                if "output_json" in payload:
                    node_run.output_json = payload["output_json"]
                    node_update_fields.append("output_json")
                if "error_json" in payload:
                    node_run.error_json = payload["error_json"]
                    node_update_fields.append("error_json")

                node_run.save(update_fields=sorted(set(node_update_fields)))

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
    }
    if event.event_type == "run.updated":
        message["run"] = payload
    elif event.event_type == "node_run.updated":
        message["node_run"] = payload
    elif event.event_type == "node_stream.chunk":
        message["node_stream"] = payload
    else:
        message["payload"] = payload
    return message


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

    try:
        access_token = AccessToken(cast(Any, token))
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

        def event_stream() -> Any:
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
