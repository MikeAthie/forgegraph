from __future__ import annotations

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
