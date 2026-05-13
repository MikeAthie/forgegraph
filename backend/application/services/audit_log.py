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

    memory_description = _describe_memory_action(action, safe_metadata, resource_id)
    if memory_description:
        return memory_description

    credential_description = _describe_credential_action(action, safe_metadata)
    if credential_description:
        return credential_description

    run_description = _describe_run_action(action, safe_metadata, resource_id)
    if run_description:
        return run_description

    if action == "run.policy_denied":
        return f"Blocked run-related action for {resource_id} because a policy denied it."
    if action == "retention_policy_updated":
        return "Updated tenant retention policy."
    if action in {"retention_cleanup", "retention_cleanup_preview"}:
        preview = "previewed" if action.endswith("_preview") else "ran"
        return f"{preview.capitalize()} retention cleanup for this tenant."

    resource_label = resource_type.replace("_", " ")
    return f"{_prettify_action(action)} on {resource_label} {resource_id}."


def _describe_memory_action(
    action: str,
    metadata: dict[str, Any],
    resource_id: str,
) -> str:
    verbs = {
        "memory.observation_created": "Created",
        "memory.observation_updated": "Updated",
        "memory.observation_deleted": "Deleted",
    }
    verb = verbs.get(action)
    if not verb:
        return ""

    description = _describe_memory_observation(
        verb=verb,
        metadata=metadata,
        fallback_id=resource_id,
    )
    if action != "memory.observation_updated":
        return description

    changed_fields = metadata.get("changed_fields")
    if isinstance(changed_fields, list) and changed_fields:
        return f"{description} Updated fields: {', '.join(str(field) for field in changed_fields)}."
    return description


def _describe_credential_action(action: str, metadata: dict[str, Any]) -> str:
    verbs = {
        "credential.created": "Created",
        "credential.deleted": "Deleted",
    }
    verb = verbs.get(action)
    provider = metadata.get("provider")
    name = metadata.get("name")
    if verb and provider and name:
        return f"{verb} {provider} credential '{name}'."
    return ""


def _describe_run_action(
    action: str,
    metadata: dict[str, Any],
    resource_id: str,
) -> str:
    if action == "run.started":
        return f"Started run {resource_id}."
    if action != "run.replayed":
        return ""
    source_run_id = metadata.get("source_run_id")
    if source_run_id:
        return f"Replayed run {resource_id} from source run {source_run_id}."
    return f"Replayed run {resource_id}."


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
