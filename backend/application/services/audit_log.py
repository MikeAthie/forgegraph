from __future__ import annotations

from typing import Any

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
    return AuditLog.objects.create(
        actor=actor,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
    )
