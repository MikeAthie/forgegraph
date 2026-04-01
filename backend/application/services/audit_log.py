from __future__ import annotations

import re
from typing import Any

from application.services.redaction import redact_payload
from infrastructure.orm.models import AuditLog, User


def record_audit_log(
    *,
    actor: User | None,
    tenant_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    safe_metadata = redact_payload(metadata or {})
    if not isinstance(safe_metadata, dict):
        safe_metadata = {}
    return AuditLog.objects.create(
        actor=actor,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=safe_metadata,
    )


def describe_audit_log(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    safe_metadata = metadata or {}

    if action == "memory.observation_created":
        return _describe_memory_observation(
            verb="Created",
            metadata=safe_metadata,
            fallback_id=resource_id,
        )
    if action == "memory.observation_updated":
        changed_fields = safe_metadata.get("changed_fields")
        changed_suffix = ""
        if isinstance(changed_fields, list) and changed_fields:
            changed_suffix = (
                f" Updated fields: {', '.join(str(field) for field in changed_fields)}."
            )
        return (
            _describe_memory_observation(
                verb="Updated",
                metadata=safe_metadata,
                fallback_id=resource_id,
            )
            + changed_suffix
        )
    if action == "memory.observation_deleted":
        return _describe_memory_observation(
            verb="Deleted",
            metadata=safe_metadata,
            fallback_id=resource_id,
        )
    if action == "credential.created":
        provider = safe_metadata.get("provider")
        name = safe_metadata.get("name")
        if provider and name:
            return f"Created {provider} credential '{name}'."
    if action == "credential.deleted":
        provider = safe_metadata.get("provider")
        name = safe_metadata.get("name")
        if provider and name:
            return f"Deleted {provider} credential '{name}'."
    if action == "run.started":
        return f"Started run {resource_id}."
    if action == "run.replayed":
        source_run_id = safe_metadata.get("source_run_id")
        if source_run_id:
            return f"Replayed run {resource_id} from source run {source_run_id}."
        return f"Replayed run {resource_id}."
    if action == "run.policy_denied":
        return f"Blocked run-related action for {resource_id} because a policy denied it."
    if action == "retention_policy_updated":
        return "Updated tenant retention policy."
    if action in {"retention_cleanup", "retention_cleanup_preview"}:
        preview = "previewed" if action.endswith("_preview") else "ran"
        return f"{preview.capitalize()} retention cleanup for this tenant."

    resource_label = resource_type.replace("_", " ")
    return f"{_prettify_action(action)} on {resource_label} {resource_id}."


def _describe_memory_observation(
    *,
    verb: str,
    metadata: dict[str, Any],
    fallback_id: str,
) -> str:
    title = str(metadata.get("title") or fallback_id)
    scope = str(metadata.get("scope") or "memory")
    observation_type = str(metadata.get("type") or "observation")
    return f"{verb} {scope} {observation_type} observation '{title}'."


def _prettify_action(action: str) -> str:
    normalized = re.sub(r"[._]+", " ", action).strip()
    if not normalized:
        return "Updated"
    return normalized[:1].upper() + normalized[1:]
