from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from application.services.redaction import redact_payload
from infrastructure.orm.models import NodeRun

_PREVIEW_LIMIT = 160


def derive_node_memory_activity(*, node_type: str, output_json: Any) -> dict[str, Any] | None:
    normalized_node_type = str(node_type).strip().lower()
    payload = redact_payload(output_json)
    if not isinstance(payload, dict):
        return None

    if normalized_node_type == "observation_save":
        return _derive_observation_save_activity(payload)
    if normalized_node_type == "observation_search":
        return _derive_observation_retrieval_activity(payload, operation="search")
    if normalized_node_type == "observation_context":
        return _derive_observation_retrieval_activity(payload, operation="context")
    if normalized_node_type == "observation_timeline":
        return _derive_observation_retrieval_activity(payload, operation="timeline")
    if normalized_node_type in {"prompt", "agent"}:
        return _derive_memory_influence_activity(payload)
    return None


def summarize_run_memory_activity(
    node_runs: Sequence[NodeRun], *, include_operations: bool
) -> dict[str, Any] | None:
    operations: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "has_activity": False,
        "save_node_count": 0,
        "saved_observation_count": 0,
        "retrieval_node_count": 0,
        "retrieved_observation_count": 0,
        "influenced_node_count": 0,
        "influenced_observation_count": 0,
        "degraded": False,
    }

    for node_run in node_runs:
        activity = derive_node_memory_activity(
            node_type=str(node_run.node_type),
            output_json=node_run.output_json,
        )
        if activity is None:
            continue

        summary["has_activity"] = True
        category = str(activity.get("category") or "")
        if category == "save":
            summary["save_node_count"] += 1
            summary["saved_observation_count"] += _coerce_int(
                activity.get("saved_observation_count"), default=0
            )
        elif category == "retrieval":
            summary["retrieval_node_count"] += 1
            summary["retrieved_observation_count"] += _coerce_int(activity.get("count"), default=0)
        elif category == "influence":
            summary["influenced_node_count"] += 1
            summary["influenced_observation_count"] += _coerce_int(
                activity.get("observation_count"), default=0
            )

        if bool(activity.get("degraded")):
            summary["degraded"] = True

        if include_operations:
            operations.append(
                {
                    "node_id": str(node_run.node_id),
                    "node_type": str(node_run.node_type),
                    "status": str(node_run.status),
                    "attempt": int(node_run.attempt),
                    "duration_ms": node_run.duration_ms,
                    **activity,
                }
            )

    if not summary["has_activity"]:
        return None

    if include_operations:
        summary["operations"] = operations

    return summary


def _derive_observation_save_activity(payload: dict[str, Any]) -> dict[str, Any] | None:
    normalized_payload = _extract_observation_payload(payload)
    observation = _summarize_observation(normalized_payload.get("observation"))
    saved = bool(normalized_payload.get("saved"))
    if not saved and observation is None:
        return None

    return _clean_dict(
        {
            "category": "save",
            "operation": "save",
            "scope": _clean_string(normalized_payload.get("scope")),
            "saved": saved,
            "saved_observation_count": 1 if observation else 0,
            "observation": observation,
        }
    )


def _derive_observation_retrieval_activity(
    payload: dict[str, Any], *, operation: str
) -> dict[str, Any] | None:
    normalized_payload = _extract_observation_payload(payload)
    observations = _summarize_observations(normalized_payload.get("observations"))
    count = _coerce_int(normalized_payload.get("count"), default=len(observations))
    query = _clean_string(normalized_payload.get("query"))
    scope = _clean_string(normalized_payload.get("scope"))
    degraded = bool(normalized_payload.get("degraded"))
    strategies = _compact_strings(normalized_payload.get("strategies"))

    if (
        count == 0
        and not query
        and not scope
        and not observations
        and not degraded
        and not strategies
    ):
        return None

    return _clean_dict(
        {
            "category": "retrieval",
            "operation": operation,
            "query": query,
            "scope": scope,
            "count": count,
            "degraded": degraded,
            "strategies": strategies,
            "observations": observations,
        }
    )


def _extract_observation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested_output = payload.get("output")
    if isinstance(nested_output, dict):
        return nested_output
    return payload


def _derive_memory_influence_activity(payload: dict[str, Any]) -> dict[str, Any] | None:
    memory_context = _extract_memory_context(payload)
    if not isinstance(memory_context, dict):
        return None

    observations = _summarize_observations(memory_context.get("curated_observations"))
    observation_count = _coerce_int(
        memory_context.get("curated_observation_count"),
        default=len(observations),
    )
    paths = _compact_strings(memory_context.get("curated_context_paths"))
    strategies = _compact_strings(memory_context.get("curated_strategies"))
    degraded = bool(memory_context.get("curated_degraded"))

    if observation_count == 0 and not paths and not strategies and not degraded:
        return None

    return _clean_dict(
        {
            "category": "influence",
            "operation": "context_use",
            "observation_count": observation_count,
            "degraded": degraded,
            "curated_context_paths": paths,
            "strategies": strategies,
            "observations": observations,
        }
    )


def _extract_memory_context(payload: dict[str, Any]) -> dict[str, Any] | None:
    direct = payload.get("memory_context")
    if isinstance(direct, dict):
        return direct

    nested_output = payload.get("output")
    if isinstance(nested_output, dict):
        nested_memory_context = nested_output.get("memory_context")
        if isinstance(nested_memory_context, dict):
            return nested_memory_context

    return None


def _summarize_observations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    summaries: list[dict[str, Any]] = []
    for item in value:
        summary = _summarize_observation(item)
        if summary is not None:
            summaries.append(summary)
    return summaries


def _summarize_observation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    content = _clean_string(value.get("content"))
    summary = _clean_dict(
        {
            "id": _clean_string(value.get("id")),
            "type": _clean_string(value.get("type")),
            "title": _clean_string(value.get("title")),
            "scope": _clean_string(value.get("scope")),
            "topic_key": _clean_string(value.get("topic_key")),
            "tool_name": _clean_string(value.get("tool_name")),
            "content_preview": _truncate_text(content),
        }
    )
    if not summary:
        return None
    return summary


def _truncate_text(value: str) -> str:
    if len(value) <= _PREVIEW_LIMIT:
        return value
    return value[: _PREVIEW_LIMIT - 1].rstrip() + "..."


def _compact_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    compacted: list[str] = []
    for item in value:
        cleaned = _clean_string(item)
        if cleaned:
            compacted.append(cleaned)
    return compacted


def _coerce_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, str) and item == "":
            continue
        if isinstance(item, (list, dict)) and len(item) == 0:
            continue
        cleaned[key] = item
    return cleaned
