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

from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    APIKey,
    GraphVersion,
    MemoryConfiguration,
    MemorySession,
    TenantPolicy,
    User,
)

START_NODE_ID = "START"
END_NODE_ID = "END"


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
    ).values("id", "provider")
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

    return errors
