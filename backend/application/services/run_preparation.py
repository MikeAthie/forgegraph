"""
Run preparation helpers for engine dispatch.

These utilities are shared by API handlers and background queue workers.
"""

from __future__ import annotations

import copy
import json as pyjson
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from application.services.credential_state import (
    is_credential_revoked,
    is_oauth_credential,
    is_oauth_provider,
)
from application.services.tenancy import get_tenant_id_for_user
from application.services.trace_context import default_runtime_limits, ensure_trace_context
from infrastructure.orm.models import (
    APIKey,
    GraphVersion,
    MemoryConfiguration,
    MemorySession,
    PromptTemplate,
    TenantPolicy,
    User,
)

START_NODE_ID = "START"
END_NODE_ID = "END"
TOOL_PROVIDER_BY_NAME: dict[str, str] = {
    "gmail_reader": "gmail",
    "google_calendar": "google_calendar",
    "google_tasks": "google_tasks",
}


class RunPreparationError(ValueError):
    """Base error for graph preparation failures before engine dispatch."""


class SubgraphResolutionError(RunPreparationError):
    """Raised when subgraph references cannot be resolved for the current user."""


class PromptTemplateResolutionError(RunPreparationError):
    """Raised when prompt templates cannot be resolved or validated."""


def get_memory_config_for_graph(graph: Any, user: User) -> MemoryConfiguration | None:
    graph_config = getattr(graph, "memory_config", None)
    if isinstance(graph_config, MemoryConfiguration):
        return graph_config
    default_config = MemoryConfiguration.objects.filter(user=user).first()
    if default_config:
        return default_config
    return None


def build_memory_config_json(graph: Any, user: User, session_id: str | None = None) -> str:
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
            raise SubgraphResolutionError("Subgraph reference is invalid or not accessible.")

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


def resolve_prompt_templates(graph_json: dict[str, Any], owner: User) -> dict[str, Any]:
    """
    Resolve prompt node `prompt_id` references into concrete `prompt_template` strings.

    Also enforces that each prompt node has either a non-empty prompt template or
    a valid prompt_id reference before graph dispatch.
    """
    if not isinstance(graph_json, dict):
        return graph_json

    data = copy.deepcopy(graph_json)
    _resolve_prompt_templates_in_place(data, owner)
    return data


def apply_tool_runtime_credentials(graph_json: dict[str, Any], owner: User) -> dict[str, Any]:
    """
    Normalize tool providers and auto-assign provider credentials when available.

    This keeps template tool nodes runnable without requiring manual credential_id on each node.
    """
    if not isinstance(graph_json, dict):
        return graph_json

    data = copy.deepcopy(graph_json)
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return data

    provider_credential_ids: dict[str, str] = {}
    org = owner.default_organization
    if org is not None:
        for provider in set(TOOL_PROVIDER_BY_NAME.values()):
            candidates = APIKey.objects.filter(
                organization=org,
                provider=provider,
            ).order_by("-created_at")
            for candidate in candidates:
                if is_credential_revoked(candidate.token_metadata):
                    continue
                if is_oauth_provider(provider) and not is_oauth_credential(
                    provider=provider,
                    raw_metadata=candidate.token_metadata,
                    has_refresh_token=bool(candidate.encrypted_refresh_token),
                    has_token_expiry=candidate.token_expires_at is not None,
                ):
                    continue
                provider_credential_ids[provider] = str(candidate.id)
                break

    def _walk(nodes_to_walk: list[dict[str, Any]]) -> None:
        for node in nodes_to_walk:
            if not isinstance(node, dict):
                continue

            node_type = str(node.get("type") or "").strip().lower()
            config_raw = node.get("config")
            config = config_raw if isinstance(config_raw, dict) else {}

            if node_type == "tool":
                tool_name = str(config.get("tool") or config.get("tool_name") or "").strip().lower()
                provider = str(config.get("provider") or "").strip().lower()
                if not provider:
                    provider = TOOL_PROVIDER_BY_NAME.get(tool_name, "")

                if provider:
                    config["provider"] = provider
                    if not str(config.get("credential_id") or "").strip():
                        credential_id = provider_credential_ids.get(provider)
                        if credential_id:
                            config["credential_id"] = credential_id

                node["config"] = config
                continue

            if node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
                subgraph = config["graph_json"]
                sub_nodes = subgraph.get("nodes")
                if isinstance(sub_nodes, list):
                    _walk(sub_nodes)
                config["graph_json"] = subgraph
                node["config"] = config

    _walk(nodes)
    return data


def _resolve_prompt_templates_in_place(graph_json: dict[str, Any], owner: User) -> None:
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return

    prompt_nodes: list[tuple[str, dict[str, Any], str]] = []
    prompt_ids: set[str] = set()

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type")
        node_id = str(node.get("id") or "prompt")
        config_raw = node.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}
        node["config"] = config

        if node_type == "prompt":
            prompt_id = str(config.get("prompt_id") or "").strip()
            prompt_template = config.get("prompt_template")

            if prompt_id:
                prompt_nodes.append((node_id, config, prompt_id))
                prompt_ids.add(prompt_id)
            elif not (isinstance(prompt_template, str) and prompt_template.strip()):
                raise PromptTemplateResolutionError(
                    f"Prompt node '{node_id}' must define either 'prompt_template' or 'prompt_id'."
                )

        elif node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
            _resolve_prompt_templates_in_place(config["graph_json"], owner)

    if not prompt_ids:
        return

    templates = (
        PromptTemplate.objects.for_user(owner).filter(id__in=prompt_ids).values("id", "content")
    )
    template_index = {str(item["id"]): str(item["content"]) for item in templates}

    for node_id, config, prompt_id in prompt_nodes:
        content = template_index.get(prompt_id)
        if content is None:
            raise PromptTemplateResolutionError(
                f"Prompt node '{node_id}' references prompt_id '{prompt_id}' that is not accessible."
            )
        config["prompt_template"] = content


def prepare_graph_for_engine(
    graph_json: dict[str, Any],
    owner: User,
    *,
    traceparent: str | None = None,
    tracestate: str | None = None,
) -> dict[str, Any]:
    """Prepare graph JSON for engine execution (strip sentinels, expand subgraphs, enforce memory isolation)."""
    cleaned = strip_sentinel_edges(graph_json)
    expanded = expand_subgraphs(cleaned, owner)
    namespaced = apply_memory_namespace_prefix(expanded, owner.id)
    resolved = resolve_prompt_templates(namespaced, owner)
    prepared = apply_tool_runtime_credentials(resolved, owner)
    metadata_raw = prepared.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    transformations = [
        "strip_sentinel_edges",
        "expand_subgraphs",
        "namespace_memory",
        "resolve_prompt_templates",
        "apply_tool_runtime_credentials",
    ]
    metadata["engine_contract_version"] = "2"
    metadata["dispatch_transformations"] = transformations
    metadata["trace"] = ensure_trace_context(traceparent=traceparent, tracestate=tracestate)
    metadata["runtime_limits"] = default_runtime_limits(settings)
    policy = TenantPolicy.objects.filter(tenant_id=get_tenant_id_for_user(owner)).first()
    if policy:
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
    prepared["metadata"] = metadata
    return prepared


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
                    "suggestion": "Select an API key in the node configuration.",
                }
            )
        else:
            credential_ids.add(credential_id)

        prompt_nodes.append((node_id, provider, credential_id))

    if not credential_ids:
        return errors

    credentials = APIKey.objects.filter(
        id__in=credential_ids,
        organization=user.default_organization,
    ).values("id", "provider", "token_metadata")
    credential_index = {str(item["id"]): item for item in credentials}

    for node_id, provider, credential_id in prompt_nodes:
        stored = credential_index.get(credential_id)
        if stored is None:
            errors.append(
                {
                    "field": "credential_id",
                    "message": f"Prompt node '{node_id}' references a credential you cannot access.",
                    "suggestion": "Choose a credential owned by your organization.",
                }
            )
            continue

        if provider and stored.get("provider") and provider != str(stored["provider"]).lower():
            errors.append(
                {
                    "field": "credential_id",
                    "message": f"Prompt node '{node_id}' credential does not match provider '{provider}'.",
                    "suggestion": "Pick a credential with the same provider as the prompt node.",
                }
            )
        if is_credential_revoked(stored.get("token_metadata")):
            errors.append(
                {
                    "field": "credential_id",
                    "message": f"Prompt node '{node_id}' uses a revoked credential.",
                    "suggestion": "Rotate or reconnect the credential before running this prompt.",
                }
            )

    return errors
