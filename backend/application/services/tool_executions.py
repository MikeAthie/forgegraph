from __future__ import annotations

import copy
import hashlib
import logging
from typing import Any

from django.db import transaction

from infrastructure.orm.models import Run, ToolExecution

logger = logging.getLogger(__name__)

SAFE_RETRY_CLASSES = {"pure", "idempotent"}
UNSAFE_RETRY_CLASSES = {"non_idempotent", "critical"}


class ToolExecutionDispatchBlocked(RuntimeError):
    """Raised when dispatch would blindly retry an unsafe tool execution."""


def backend_attempt_id_for_run(run: Run) -> str:
    if run.resume_attempt_id:
        return str(run.resume_attempt_id)
    return f"backend-attempt-{run.id}"


def stable_tool_idempotency_key(*, run_id: object, node_id: str, attempt_id: str) -> str:
    material = f"{run_id}:{node_id}:{attempt_id}".encode()
    return "fg-tool-" + hashlib.sha256(material).hexdigest()[:48]


def prepare_tool_executions_for_dispatch(
    *,
    run: Run,
    graph_json: dict[str, Any],
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """
    Create backend-owned ToolExecution rows and annotate dispatch_graph_json.

    The engine receives identity, but the DB row remains the durable source of truth.
    """

    attempt = (attempt_id or backend_attempt_id_for_run(run)).strip()
    if not attempt:
        raise ToolExecutionDispatchBlocked("tool execution attempt_id could not be derived")

    data = copy.deepcopy(graph_json)
    metadata_raw = data.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    metadata["backend_attempt_id"] = attempt
    data["metadata"] = metadata
    pinned_tools = _index_pinned_tools(metadata)

    with transaction.atomic():
        _annotate_tool_nodes(
            run=run, graph_json=data, attempt_id=attempt, pinned_tools=pinned_tools
        )

    return data


def transition_tool_execution(
    *,
    tool_execution: ToolExecution,
    status: str,
) -> ToolExecution:
    allowed = {
        "planned": {"planned", "in_progress", "succeeded", "failed", "ambiguous"},
        "in_progress": {"in_progress", "succeeded", "failed", "ambiguous"},
        "succeeded": {"succeeded"},
        "failed": {"failed"},
        "ambiguous": {"ambiguous"},
    }
    if status not in allowed.get(tool_execution.status, {tool_execution.status}):
        logger.warning(
            "tool_execution_status_transition_rejected",
            extra={
                "tool_execution_id": str(tool_execution.id),
                "run_id": str(tool_execution.run_id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "from_status": tool_execution.status,
                "to_status": status,
            },
        )
        return tool_execution
    if tool_execution.status != status:
        previous = tool_execution.status
        tool_execution.status = status
        tool_execution.save(update_fields=["status", "updated_at"])
        logger.info(
            "tool_execution_status_transitioned",
            extra={
                "tool_execution_id": str(tool_execution.id),
                "run_id": str(tool_execution.run_id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "from_status": previous,
                "to_status": status,
                "idempotency_key": tool_execution.idempotency_key,
                "side_effect_class": tool_execution.side_effect_class,
            },
        )
    return tool_execution


def _annotate_tool_nodes(
    *,
    run: Run,
    graph_json: dict[str, Any],
    attempt_id: str,
    pinned_tools: dict[str, dict[str, Any]],
) -> None:
    nodes = graph_json.get("nodes")
    if not isinstance(nodes, list):
        return

    for node in nodes:
        if not isinstance(node, dict):
            continue
        config_raw = node.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}
        node["config"] = config

        if node.get("type") == "tool":
            _annotate_one_tool_node(
                run=run,
                node=node,
                config=config,
                attempt_id=attempt_id,
                pinned_tools=pinned_tools,
            )
            continue

        subgraph = config.get("graph_json")
        if node.get("type") == "subgraph" and isinstance(subgraph, dict):
            _annotate_tool_nodes(
                run=run,
                graph_json=subgraph,
                attempt_id=attempt_id,
                pinned_tools=pinned_tools,
            )
            config["graph_json"] = subgraph


def _annotate_one_tool_node(
    *,
    run: Run,
    node: dict[str, Any],
    config: dict[str, Any],
    attempt_id: str,
    pinned_tools: dict[str, dict[str, Any]],
) -> None:
    node_id = str(node.get("id") or "").strip()
    if not node_id:
        raise ToolExecutionDispatchBlocked("tool node is missing id")

    tool_name = str(config.get("tool") or config.get("tool_name") or "").strip()
    tool_version = str(config.get("version") or "").strip()
    definition = _find_tool_definition(
        pinned_tools=pinned_tools,
        tool_name=tool_name,
        tool_version=tool_version,
    )
    if definition is not None:
        tool_name = str(definition.get("name") or tool_name).strip()
        tool_version = str(definition.get("version") or tool_version).strip()
        if tool_version:
            config["version"] = tool_version

    if not tool_name:
        raise ToolExecutionDispatchBlocked(f"tool node {node_id} is missing tool name")

    side_effect_class = _side_effect_class(definition, config)
    idempotency_key = stable_tool_idempotency_key(
        run_id=run.id,
        node_id=node_id,
        attempt_id=attempt_id,
    )

    tool_execution, created = ToolExecution.objects.select_for_update().get_or_create(
        run=run,
        node_id=node_id,
        attempt_id=attempt_id,
        defaults={
            "tool_name": tool_name,
            "tool_version": tool_version,
            "idempotency_key": idempotency_key,
            "side_effect_class": side_effect_class,
            "status": "planned",
        },
    )
    if not created:
        _enforce_retry_policy(tool_execution)
        update_fields: list[str] = []
        if tool_execution.tool_name != tool_name:
            tool_execution.tool_name = tool_name
            update_fields.append("tool_name")
        if tool_execution.tool_version != tool_version:
            tool_execution.tool_version = tool_version
            update_fields.append("tool_version")
        if tool_execution.idempotency_key != idempotency_key:
            raise ToolExecutionDispatchBlocked(
                f"tool execution {tool_execution.id} idempotency key changed"
            )
        if tool_execution.side_effect_class != side_effect_class:
            tool_execution.side_effect_class = side_effect_class
            update_fields.append("side_effect_class")
        if update_fields:
            update_fields.append("updated_at")
            tool_execution.save(update_fields=update_fields)

    config["tool_execution_id"] = str(tool_execution.id)
    config["idempotency_key"] = tool_execution.idempotency_key
    config["side_effect_class"] = tool_execution.side_effect_class
    if tool_execution.status == "succeeded":
        config["skip_tool_execution"] = True

    logger.info(
        "tool_execution_planned",
        extra={
            "tool_execution_id": str(tool_execution.id),
            "run_id": str(run.id),
            "node_id": node_id,
            "attempt_id": attempt_id,
            "tool_name": tool_execution.tool_name,
            "tool_version": tool_execution.tool_version,
            "idempotency_key": tool_execution.idempotency_key,
            "side_effect_class": tool_execution.side_effect_class,
            "status": tool_execution.status,
            "retry_decision": "dispatch_allowed",
        },
    )


def _enforce_retry_policy(tool_execution: ToolExecution) -> None:
    if tool_execution.status == "succeeded":
        logger.info(
            "tool_execution_retry_skipped_succeeded",
            extra={
                "tool_execution_id": str(tool_execution.id),
                "run_id": str(tool_execution.run_id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "retry_decision": "skip_reexecution",
            },
        )
        return
    if tool_execution.status == "ambiguous":
        logger.warning(
            "tool_execution_retry_blocked_ambiguous",
            extra={
                "tool_execution_id": str(tool_execution.id),
                "run_id": str(tool_execution.run_id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "retry_decision": "blocked",
            },
        )
        raise ToolExecutionDispatchBlocked(
            "ambiguous tool execution cannot be retried automatically"
        )
    if (
        tool_execution.status == "failed"
        and tool_execution.side_effect_class in UNSAFE_RETRY_CLASSES
    ):
        logger.warning(
            "tool_execution_retry_blocked_unsafe",
            extra={
                "tool_execution_id": str(tool_execution.id),
                "run_id": str(tool_execution.run_id),
                "node_id": tool_execution.node_id,
                "attempt_id": tool_execution.attempt_id,
                "side_effect_class": tool_execution.side_effect_class,
                "retry_decision": "blocked",
            },
        )
        raise ToolExecutionDispatchBlocked("unsafe tool execution cannot be retried automatically")


def _index_pinned_tools(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resolution = metadata.get("tool_resolution")
    if not isinstance(resolution, dict):
        return {}
    pinned = resolution.get("pinned_tools")
    if not isinstance(pinned, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in pinned:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        version = str(item.get("version") or "").strip()
        if not name:
            continue
        result[name] = item
        if version:
            result[f"{name}@{version}"] = item
    return result


def _find_tool_definition(
    *,
    pinned_tools: dict[str, dict[str, Any]],
    tool_name: str,
    tool_version: str,
) -> dict[str, Any] | None:
    if tool_name and tool_version:
        matched = pinned_tools.get(f"{tool_name}@{tool_version}")
        if matched is not None:
            return matched
    if tool_name:
        return pinned_tools.get(tool_name)
    return None


def _side_effect_class(
    definition: dict[str, Any] | None,
    config: dict[str, Any],
) -> str:
    explicit = str(config.get("side_effect_class") or "").strip()
    if explicit in {"pure", "idempotent", "non_idempotent", "critical"}:
        return explicit

    side_effects = definition.get("side_effects") if isinstance(definition, dict) else None
    if not isinstance(side_effects, dict):
        return "non_idempotent"

    effect_type = str(side_effects.get("type") or "").strip().lower()
    is_idempotent = bool(side_effects.get("idempotent"))
    if effect_type == "read":
        return "pure"
    if is_idempotent:
        return "idempotent"
    if effect_type in {"write", "external"}:
        return "non_idempotent"
    return "non_idempotent"
