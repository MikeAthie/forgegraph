"""Backend-owned Atlas launch attempt checkpointing."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from infrastructure.orm.models import (
    AtlasLaunchAttempt,
    AtlasLaunchCheckpoint,
    ServiceDeliverable,
    User,
    WorkWhiteboard,
)

STATUS_ORDER = {
    "dry_run": 10,
    "blocked": 20,
    "ready": 30,
    "launched": 40,
    "failed": 50,
}


def launch_status_from_readiness(readiness: dict[str, Any], *, live_mode: bool) -> str:
    """Map a readiness payload to the durable launch-attempt status vocabulary."""
    status = str(readiness.get("status") or "").strip()
    if status == "blocked" or bool(readiness.get("blockers")):
        return "blocked"
    if live_mode and status == "ready":
        return "ready"
    return "dry_run"


def record_launch_attempt_checkpoint(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    idempotency_key: str,
    source_key: str,
    requested_mode: str,
    status: str,
    readiness: dict[str, Any],
    receipt_deliverable: ServiceDeliverable | None = None,
) -> AtlasLaunchAttempt:
    """Create/update a company-scoped attempt and append a checkpoint audit row."""
    normalized_key = str(idempotency_key or "").strip()
    normalized_source = str(source_key or "").strip()
    if not normalized_key:
        msg = "idempotency_key is required to record an Atlas launch attempt"
        raise ValueError(msg)
    if not normalized_source:
        msg = "source_key is required to record an Atlas launch attempt"
        raise ValueError(msg)

    sanitized_readiness = sanitize_outbox_payload(readiness)
    blockers = list(sanitized_readiness.get("blockers") or [])
    receipt = receipt_deliverable or _receipt_from_payload(sanitized_readiness)
    now = timezone.now()

    with transaction.atomic():
        attempt, created = AtlasLaunchAttempt.objects.select_for_update().get_or_create(
            organization=whiteboard.organization,
            company=whiteboard.company,
            source_key=normalized_source,
            defaults={
                "whiteboard": whiteboard,
                "idempotency_key": normalized_key,
                "requested_mode": requested_mode,
                "status": status,
                "blocker_snapshot_json": blockers,
                "readiness_snapshot_json": sanitized_readiness,
                "receipt_deliverable": receipt,
                "created_by": user,
                "last_checkpoint_at": now,
            },
        )
        if not created:
            attempt.whiteboard = whiteboard
            attempt.idempotency_key = normalized_key
            attempt.requested_mode = requested_mode
            attempt.status = _merge_status(attempt.status, status)
            attempt.blocker_snapshot_json = blockers
            attempt.readiness_snapshot_json = sanitized_readiness
            if receipt is not None:
                attempt.receipt_deliverable = receipt
            attempt.last_checkpoint_at = now
            attempt.save(
                update_fields=[
                    "whiteboard",
                    "idempotency_key",
                    "requested_mode",
                    "status",
                    "blocker_snapshot_json",
                    "readiness_snapshot_json",
                    "receipt_deliverable",
                    "last_checkpoint_at",
                    "updated_at",
                ]
            )

        sequence = AtlasLaunchCheckpoint.objects.filter(attempt=attempt).count() + 1
        AtlasLaunchCheckpoint.objects.create(
            organization=whiteboard.organization,
            company=whiteboard.company,
            attempt=attempt,
            whiteboard=whiteboard,
            sequence=sequence,
            status=attempt.status,
            checkpoint_type="readiness_evaluated",
            requested_mode=requested_mode,
            idempotency_key=normalized_key,
            source_key=normalized_source,
            blocker_snapshot_json=blockers,
            readiness_snapshot_json=sanitized_readiness,
            receipt_deliverable=receipt,
            recorded_by=user,
        )
    return attempt


def launch_attempt_payload(attempt: AtlasLaunchAttempt) -> dict[str, Any]:
    return {
        "id": str(attempt.id),
        "company_id": str(attempt.company_id),
        "whiteboard_id": str(attempt.whiteboard_id),
        "source_key": attempt.source_key,
        "idempotency_key": attempt.idempotency_key,
        "requested_mode": attempt.requested_mode,
        "status": attempt.status,
        "blockers": attempt.blocker_snapshot_json,
        "receipt_deliverable_id": (
            str(attempt.receipt_deliverable_id) if attempt.receipt_deliverable_id else ""
        ),
        "last_checkpoint_at": attempt.last_checkpoint_at.isoformat()
        if attempt.last_checkpoint_at
        else None,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        "updated_at": attempt.updated_at.isoformat() if attempt.updated_at else None,
    }


def _merge_status(current: str, incoming: str) -> str:
    if incoming == "failed":
        return "failed"
    if current == "failed" and incoming != "launched":
        return current
    return incoming if STATUS_ORDER.get(incoming, 0) >= STATUS_ORDER.get(current, 0) else current


def _receipt_from_payload(readiness: dict[str, Any]) -> ServiceDeliverable | None:
    receipt = readiness.get("receipt_deliverable")
    if not isinstance(receipt, dict):
        return None
    receipt_id = str(receipt.get("id") or "").strip()
    if not receipt_id:
        return None
    return ServiceDeliverable.objects.filter(id=receipt_id).first()
