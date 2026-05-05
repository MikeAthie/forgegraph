from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.redaction import redact_payload
from infrastructure.orm.models import (
    EventDeadLetterRecord,
    OperatorActionLog,
    Organization,
    RuntimeIntentOutcome,
    TaskDeadLetterRecord,
    User,
)

DeadLetterItem = TaskDeadLetterRecord | EventDeadLetterRecord | RuntimeIntentOutcome


@dataclass(frozen=True)
class DeadLetterResolution:
    kind: str
    target_type: str
    target_id: str
    item: DeadLetterItem


def record_operator_action(
    *,
    actor: User,
    organization: Organization,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    status: str,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> OperatorActionLog:
    safe_metadata = redact_payload(metadata or {})
    if not isinstance(safe_metadata, dict):
        safe_metadata = {}
    log = OperatorActionLog.objects.create(
        actor=actor,
        organization=organization,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason=str(reason or "")[:2000],
        status=str(status or "applied")[:32],
        idempotency_key=str(idempotency_key or "")[:255],
        metadata=safe_metadata,
    )
    record_audit_log(
        actor=actor,
        tenant_id=str(organization.id),
        action=f"operator.{action}",
        resource_type=target_type,
        resource_id=str(target_id),
        metadata={
            "reason": reason,
            "status": status,
            "idempotency_key": idempotency_key,
            **safe_metadata,
        },
    )
    return log


@transaction.atomic
def resolve_dead_letter_record(
    *,
    actor: User,
    organization: Organization,
    kind: str,
    item: DeadLetterItem,
    reason: str,
    dead_letter_key: str,
    idempotency_key: str,
) -> DeadLetterResolution:
    """Resolve an operator-visible dead letter through a backend-owned write boundary."""

    now = timezone.now()
    if kind == "task":
        task = item
        if not isinstance(task, TaskDeadLetterRecord):
            raise TypeError("Expected TaskDeadLetterRecord for task dead letter resolution")
        task.status = "acknowledged"
        task.acknowledged_at = now
        task.acknowledged_by = actor
        task.acknowledgement_reason = reason
        task.save(
            update_fields=[
                "status",
                "acknowledged_at",
                "acknowledged_by",
                "acknowledgement_reason",
                "updated_at",
            ]
        )
        resolution = DeadLetterResolution(
            kind="task",
            target_type="task",
            target_id=str(task.id),
            item=task,
        )
    elif kind == "event":
        event = item
        if not isinstance(event, EventDeadLetterRecord):
            raise TypeError("Expected EventDeadLetterRecord for event dead letter resolution")
        event.status = "resolved"
        event.acknowledged_at = now
        event.acknowledged_by = actor
        event.acknowledgement_reason = reason
        event.save(
            update_fields=[
                "status",
                "acknowledged_at",
                "acknowledged_by",
                "acknowledgement_reason",
                "last_seen_at",
            ]
        )
        resolution = DeadLetterResolution(
            kind="event",
            target_type="event",
            target_id=str(event.id),
            item=event,
        )
    elif kind == "runtime_intent":
        outcome = item
        if not isinstance(outcome, RuntimeIntentOutcome):
            raise TypeError(
                "Expected RuntimeIntentOutcome for runtime intent dead letter resolution"
            )
        outcome.acknowledged_at = now
        outcome.acknowledged_by = actor
        outcome.acknowledgement_reason = reason
        outcome.save(
            update_fields=[
                "acknowledged_at",
                "acknowledged_by",
                "acknowledgement_reason",
                "updated_at",
            ]
        )
        TaskDeadLetterRecord.objects.filter(
            intent_id=outcome.intent_id,
            status="active",
        ).update(
            status="acknowledged",
            acknowledged_at=now,
            acknowledged_by=actor,
            acknowledgement_reason=reason,
        )
        resolution = DeadLetterResolution(
            kind="runtime_intent",
            target_type="runtime_intent",
            target_id=str(outcome.intent_id),
            item=outcome,
        )
    else:
        raise ValueError(f"Unsupported dead letter kind: {kind}")

    record_operator_action(
        actor=actor,
        organization=organization,
        action="ops.dead_letter.resolve",
        target_type=resolution.target_type,
        target_id=resolution.target_id,
        reason=reason,
        status="resolved",
        idempotency_key=idempotency_key,
        metadata={"dead_letter_key": dead_letter_key},
    )
    return resolution
