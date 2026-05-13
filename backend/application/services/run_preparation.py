"""
Run preparation helpers for engine dispatch.

These utilities are shared by API handlers and background queue workers.
"""

from __future__ import annotations

import copy
import json as pyjson
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from application.services.credential_state import (
    is_credential_revoked,
    is_oauth_credential,
    is_oauth_provider,
)
from application.services.llm_access import LLM_MODE_BYOK, LLMAccessConfig
from application.services.marketplace_runtime import (
    build_runtime_manifest_payload,
    normalize_runtime_mode,
    select_agent_runtime_tools,
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
        _expand_subgraph_node(node, owner=owner, tenant_uuid=tenant_uuid)

    return data


def _expand_subgraph_node(node: dict[str, Any], *, owner: User, tenant_uuid: UUID) -> None:
    config = node.get("config")
    if not isinstance(config, dict):
        config = {}

    if isinstance(config.get("graph_json"), dict):
        config["graph_json"] = expand_subgraphs(config["graph_json"], owner)
        node["config"] = config
        return

    graph_version = _resolve_subgraph_version(config, tenant_uuid)
    if graph_version is None:
        raise SubgraphResolutionError("Subgraph reference is invalid or not accessible.")

    subgraph_json = strip_sentinel_edges(graph_version.graph_json)
    config["graph_json"] = expand_subgraphs(subgraph_json, owner)
    config["graph_id"] = str(graph_version.graph_id)
    config["graph_version_id"] = str(graph_version.id)
    config["graph_version"] = graph_version.version
    node["config"] = config


def _resolve_subgraph_version(config: dict[str, Any], tenant_uuid: UUID) -> GraphVersion | None:
    scope = Q(graph__organization_id=tenant_uuid) | Q(
        graph__organization__isnull=True,
        graph__owner__default_organization_id=tenant_uuid,
    )
    graph_version_id = config.get("graph_version_id")
    if graph_version_id:
        return cast(
            GraphVersion | None,
            GraphVersion.objects.select_related("graph").filter(scope, id=graph_version_id).first(),
        )
    graph_id = config.get("graph_id")
    if graph_id:
        return cast(
            GraphVersion | None,
            GraphVersion.objects.select_related("graph")
            .filter(scope, graph_id=graph_id)
            .order_by("-version")
            .first(),
        )
    return None


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


def _active_tool_provider_credential_ids(owner: User) -> dict[str, str]:
    provider_credential_ids: dict[str, str] = {}
    org = owner.default_organization
    if org is None:
        return provider_credential_ids
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
    return provider_credential_ids


def _apply_tool_node_runtime_credentials(
    *,
    node: dict[str, Any],
    config: dict[str, Any],
    provider_credential_ids: dict[str, str],
) -> None:
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


def _apply_tool_runtime_credentials_to_nodes(
    nodes: list[Any],
    provider_credential_ids: dict[str, str],
) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = str(node.get("type") or "").strip().lower()
        config_raw = node.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}

        if node_type == "tool":
            _apply_tool_node_runtime_credentials(
                node=node,
                config=config,
                provider_credential_ids=provider_credential_ids,
            )
            continue

        if node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
            subgraph = config["graph_json"]
            sub_nodes = subgraph.get("nodes")
            if isinstance(sub_nodes, list):
                _apply_tool_runtime_credentials_to_nodes(sub_nodes, provider_credential_ids)
            config["graph_json"] = subgraph
            node["config"] = config


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

    _apply_tool_runtime_credentials_to_nodes(nodes, _active_tool_provider_credential_ids(owner))
    return data


def _normalize_agent_tool_names(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _get_runtime_tool_catalog(owner: User, company_id: UUID | str | None = None) -> dict[str, Any]:
    tenant_id = get_tenant_id_for_user(owner)
    runtime_mode = normalize_runtime_mode(getattr(settings, "FORGEGRAPH_RUNTIME_MODE", "cloud"))
    payload = build_runtime_manifest_payload(tenant_id, runtime_mode, company_id=company_id)
    tools = payload.get("tools")
    return {
        "tenant_id": tenant_id,
        "company_id": str(payload.get("company_id") or ""),
        "runtime_mode": runtime_mode,
        "manifest_checksum": str(payload.get("checksum") or ""),
        "manifest_version": int(payload.get("manifest_version") or 2),
        "tools": [tool for tool in tools if isinstance(tool, dict)]
        if isinstance(tools, list)
        else [],
    }


def _index_runtime_tools(available_tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed_tools: dict[str, dict[str, Any]] = {}
    for definition in available_tools:
        name = str(definition.get("name") or "").strip()
        version = str(definition.get("version") or "").strip()
        if not name or not version:
            continue
        indexed_tools[f"{name}@{version}"] = definition
        indexed_tools.setdefault(name, definition)
    return indexed_tools


def _record_pinned_runtime_tool(
    pinned_tools: dict[str, dict[str, Any]],
    definition: dict[str, Any] | None,
) -> None:
    if not isinstance(definition, dict):
        return
    name = str(definition.get("name") or "").strip()
    version = str(definition.get("version") or "").strip()
    if not name or not version:
        return
    pinned_tools[f"{name}@{version}"] = definition


def _apply_agent_node_tool_selection(
    *,
    node: dict[str, Any],
    node_id: str,
    config: dict[str, Any],
    available_tools: list[dict[str, Any]],
    pinned_tools: dict[str, dict[str, Any]],
    agent_nodes: dict[str, dict[str, Any]],
) -> None:
    explicit_tools = _normalize_agent_tool_names(config.get("tools"))
    tool_selection = (
        config.get("tool_selection") if isinstance(config.get("tool_selection"), dict) else {}
    )
    resolved = select_agent_runtime_tools(
        available_tools=available_tools,
        explicit_tool_names=explicit_tools,
        tool_selection=tool_selection,
    )

    selected_names = resolved["tool_names"]
    tool_versions = resolved["tool_versions"]
    config["tools"] = selected_names
    if tool_versions:
        config["tool_versions"] = tool_versions

    approval_required_tools = _normalize_agent_tool_names(config.get("approval_required_tools"))
    invalid_tools = [
        tool_name for tool_name in approval_required_tools if tool_name not in selected_names
    ]
    if invalid_tools:
        raise RunPreparationError(
            "Agent approval_required_tools must be included in the resolved tool set."
        )

    for definition in resolved["tool_definitions"]:
        _record_pinned_runtime_tool(pinned_tools, definition)

    agent_nodes[node_id] = {
        "tools": selected_names,
        "tool_versions": tool_versions,
        "unresolved_explicit_tools": resolved["unresolved_explicit_tools"],
    }
    node["config"] = config


def _apply_tool_node_runtime_version(
    *,
    node: dict[str, Any],
    config: dict[str, Any],
    indexed_tools: dict[str, dict[str, Any]],
    pinned_tools: dict[str, dict[str, Any]],
) -> None:
    tool_name = str(config.get("tool") or config.get("tool_name") or "").strip()
    if tool_name and not str(config.get("version") or "").strip():
        matched = indexed_tools.get(tool_name)
        if matched is not None:
            config["version"] = str(matched.get("version") or "")
            _record_pinned_runtime_tool(pinned_tools, matched)
    node["config"] = config


def _apply_backend_tool_selection_to_nodes(
    *,
    nodes: list[Any],
    available_tools: list[dict[str, Any]],
    indexed_tools: dict[str, dict[str, Any]],
    pinned_tools: dict[str, dict[str, Any]],
    agent_nodes: dict[str, dict[str, Any]],
) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "").strip().lower()
        node_id = str(node.get("id") or "").strip() or "node"
        config_raw = node.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}

        if node_type == "agent":
            _apply_agent_node_tool_selection(
                node=node,
                node_id=node_id,
                config=config,
                available_tools=available_tools,
                pinned_tools=pinned_tools,
                agent_nodes=agent_nodes,
            )
        elif node_type == "tool":
            _apply_tool_node_runtime_version(
                node=node,
                config=config,
                indexed_tools=indexed_tools,
                pinned_tools=pinned_tools,
            )
        elif node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
            subgraph = config["graph_json"]
            sub_nodes = subgraph.get("nodes")
            if isinstance(sub_nodes, list):
                _apply_backend_tool_selection_to_nodes(
                    nodes=sub_nodes,
                    available_tools=available_tools,
                    indexed_tools=indexed_tools,
                    pinned_tools=pinned_tools,
                    agent_nodes=agent_nodes,
                )
            config["graph_json"] = subgraph
            node["config"] = config


def apply_backend_tool_selection(
    graph_json: dict[str, Any],
    owner: User,
    *,
    company_id: UUID | str | None = None,
) -> dict[str, Any]:
    """
    Resolve agent/tool node tool references against the backend-owned tenant tool catalog.

    The rendered graph becomes the execution contract for the run and is safe to persist
    for queueing, replay, and retry without giving the engine authority over tool selection.
    """
    if not isinstance(graph_json, dict):
        return graph_json

    catalog = _get_runtime_tool_catalog(owner, company_id=company_id)
    available_tools = catalog["tools"]
    indexed_tools = _index_runtime_tools(available_tools)

    data = copy.deepcopy(graph_json)
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return data

    pinned_tools: dict[str, dict[str, Any]] = {}
    agent_nodes: dict[str, dict[str, Any]] = {}
    _apply_backend_tool_selection_to_nodes(
        nodes=nodes,
        available_tools=available_tools,
        indexed_tools=indexed_tools,
        pinned_tools=pinned_tools,
        agent_nodes=agent_nodes,
    )

    metadata_raw = data.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    metadata["tool_resolution"] = {
        "manifest_version": catalog["manifest_version"],
        "manifest_checksum": catalog["manifest_checksum"],
        "tenant_id": catalog["tenant_id"],
        "company_id": catalog["company_id"],
        "runtime_mode": catalog["runtime_mode"],
        "tool_catalog_size": len(available_tools),
        "pinned_tools": sorted(
            pinned_tools.values(),
            key=lambda item: (str(item.get("name") or ""), str(item.get("version") or "")),
        ),
        "agent_nodes": agent_nodes,
    }
    data["metadata"] = metadata
    return data


def _resolve_prompt_templates_in_place(graph_json: dict[str, Any], owner: User) -> None:
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return

    prompt_nodes, prompt_ids = _collect_prompt_template_refs(nodes, owner)
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


def _collect_prompt_template_refs(
    nodes: list[Any],
    owner: User,
) -> tuple[list[tuple[str, dict[str, Any], str]], set[str]]:
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

    return prompt_nodes, prompt_ids


def prepare_graph_for_engine(
    graph_json: dict[str, Any],
    owner: User,
    *,
    company_id: UUID | str | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
) -> dict[str, Any]:
    """Prepare graph JSON for engine execution (strip sentinels, expand subgraphs, enforce memory isolation)."""
    cleaned = strip_sentinel_edges(graph_json)
    expanded = expand_subgraphs(cleaned, owner)
    namespaced = apply_memory_namespace_prefix(expanded, owner.id)
    resolved = resolve_prompt_templates(namespaced, owner)
    credentialized = apply_tool_runtime_credentials(resolved, owner)
    prepared = apply_backend_tool_selection(credentialized, owner, company_id=company_id)
    metadata_raw = prepared.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    transformations = [
        "strip_sentinel_edges",
        "expand_subgraphs",
        "namespace_memory",
        "resolve_prompt_templates",
        "apply_tool_runtime_credentials",
        "apply_backend_tool_selection",
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


def validate_prompt_credentials(
    graph_json: dict[str, Any],
    user: User,
    *,
    llm_access: LLMAccessConfig | None = None,
) -> list[dict[str, Any]]:
    allowed_providers = set(getattr(settings, "ALLOWED_LLM_PROVIDERS", ["openai", "anthropic"]))
    policy = TenantPolicy.objects.filter(tenant_id=get_tenant_id_for_user(user)).first()
    allowed_policy_providers = (
        {str(value).lower() for value in policy.allowed_providers} if policy else set()
    )
    allowed_policy_models = {str(value) for value in policy.allowed_models} if policy else set()
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return []

    errors, prompt_nodes, credential_ids = _collect_prompt_credential_refs(
        nodes=nodes,
        allowed_providers=allowed_providers,
        allowed_policy_providers=allowed_policy_providers,
        allowed_policy_models=allowed_policy_models,
        llm_access=llm_access,
    )

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


def _collect_prompt_credential_refs(
    *,
    nodes: list[Any],
    allowed_providers: set[str],
    allowed_policy_providers: set[str],
    allowed_policy_models: set[str],
    llm_access: LLMAccessConfig | None,
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]], set[str]]:
    errors: list[dict[str, Any]] = []
    prompt_nodes: list[tuple[str, str, str]] = []
    credential_ids: set[str] = set()

    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "prompt":
            continue
        node_errors, prompt_node, credential_id = _validate_prompt_credential_node(
            node,
            allowed_providers=allowed_providers,
            allowed_policy_providers=allowed_policy_providers,
            allowed_policy_models=allowed_policy_models,
            llm_access=llm_access,
        )
        errors.extend(node_errors)
        prompt_nodes.append(prompt_node)
        if credential_id:
            credential_ids.add(credential_id)
    return errors, prompt_nodes, credential_ids


def _validate_prompt_credential_node(
    node: dict[str, Any],
    *,
    allowed_providers: set[str],
    allowed_policy_providers: set[str],
    allowed_policy_models: set[str],
    llm_access: LLMAccessConfig | None,
) -> tuple[list[dict[str, Any]], tuple[str, str, str], str]:
    node_id = str(node.get("id") or "prompt")
    config_raw = node.get("config")
    config = config_raw if isinstance(config_raw, dict) else {}
    provider = str(config.get("provider") or "").strip().lower()
    credential_id = str(config.get("credential_id") or "").strip()
    access_provider = str(getattr(llm_access, "provider", "") or "").strip().lower()
    effective_provider = provider or access_provider

    errors = _prompt_provider_errors(
        node_id=node_id,
        effective_provider=effective_provider,
        allowed_providers=allowed_providers,
        allowed_policy_providers=allowed_policy_providers,
    )
    model = str(config.get("model") or "").strip()
    errors.extend(_prompt_model_errors(node_id, model, allowed_policy_models))
    if not credential_id and not _prompt_fallback_available(
        provider=provider,
        access_provider=access_provider,
        effective_provider=effective_provider,
        llm_access=llm_access,
    ):
        errors.append(
            {
                "field": "credential_id",
                "message": f"Prompt node '{node_id}' is missing a credential.",
                "suggestion": "Select an API key in the node configuration or use run-level BYOK.",
            }
        )
    return errors, (node_id, provider, credential_id), credential_id


def _prompt_provider_errors(
    *,
    node_id: str,
    effective_provider: str,
    allowed_providers: set[str],
    allowed_policy_providers: set[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if effective_provider and effective_provider not in allowed_providers:
        errors.append(
            {
                "field": "provider",
                "message": f"Prompt node '{node_id}' uses unsupported provider '{effective_provider}'.",
                "suggestion": f"Use one of: {', '.join(sorted(allowed_providers))}.",
            }
        )
    if allowed_policy_providers and effective_provider not in {"", *allowed_policy_providers}:
        errors.append(
            {
                "field": "provider",
                "message": f"Prompt node '{node_id}' uses a provider blocked by policy.",
                "suggestion": f"Use one of: {', '.join(sorted(allowed_policy_providers))}.",
            }
        )
    return errors


def _prompt_model_errors(
    node_id: str,
    model: str,
    allowed_policy_models: set[str],
) -> list[dict[str, Any]]:
    if not allowed_policy_models or not model or model in allowed_policy_models:
        return []
    return [
        {
            "field": "model",
            "message": f"Prompt node '{node_id}' uses a model blocked by policy.",
            "suggestion": f"Use one of: {', '.join(sorted(allowed_policy_models))}.",
        }
    ]


def _prompt_fallback_available(
    *,
    provider: str,
    access_provider: str,
    effective_provider: str,
    llm_access: LLMAccessConfig | None,
) -> bool:
    run_byok_available = (
        getattr(llm_access, "llm_mode", "") == LLM_MODE_BYOK
        and bool(str(getattr(llm_access, "api_key", "") or "").strip())
        and (not provider or not access_provider or provider == access_provider)
    )
    fallback_provider_available = effective_provider in {"", "openai"} and bool(
        str(getattr(settings, "OPENAI_API_KEY", "")).strip()
    )
    return run_byok_available or fallback_provider_available
