"""Project Kanban board services backed by WorkWhiteboard and TaskRoutingRecord."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.departments import active_department_membership, has_department_role
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.domain_events import record_domain_event
from application.services.rbac import has_min_role
from application.services.redis_connections import build_redis_client
from application.services.work_whiteboards import (
    _whiteboard_queryset,
    effective_work_status_for_whiteboard,
    whiteboard_semantic_aliases,
    whiteboard_snapshot_key,
    whiteboard_snapshot_ttl_seconds,
)
from infrastructure.orm.models import (
    DecisionRecord,
    DepartmentRegistry,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    RequestClassificationRecord,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

WHITEBOARD_BOARD_SNAPSHOT_VERSION = "whiteboard_board_v1"
WHITEBOARD_BOARD_EVENT_SCHEMA_VERSION = "whiteboard_board_event_v1"
WHITEBOARD_BOARD_OUTBOX_TOPIC = "forgegraph.whiteboard.board.events.v1"

BOARD_STATUSES = {
    "queued",
    "assigned",
    "claimed",
    "in_progress",
    "blocked",
    "ready_for_review",
    "completed",
    "cancelled",
}
BOARD_STATUS_CONTRACT = {
    "queued",
    "assigned",
    "in_progress",
    "blocked",
    "ready_for_review",
    "completed",
    "cancelled",
}
BOARD_PRIORITIES = {choice[0] for choice in TaskRoutingRecord.PRIORITY_CHOICES}
ROUTING_DEPARTMENT_MARKERS = {"traffic", "routing", "router", "request-routing", "board-routing"}
STRUCTURAL_EVENT_TYPES = {
    "created": "whiteboard.card.created",
    "reassigned": "whiteboard.card.reassigned",
    "priority_changed": "whiteboard.card.priority_changed",
    "due_date_changed": "whiteboard.card.due_date_changed",
    "status_changed": "whiteboard.card.status_changed",
}
WHITEBOARD_BOARD_EVENT_TYPES = {
    "whiteboard.board.snapshot_refreshed",
    "whiteboard.card.created",
    "whiteboard.card.status_changed",
    "whiteboard.card.assigned",
    "whiteboard.card.blocked",
    "whiteboard.card.unblocked",
    "whiteboard.card.completed",
    "whiteboard.card.evidence_attached",
    "whiteboard.card.reassigned",
    "whiteboard.card.priority_changed",
    "whiteboard.card.due_date_changed",
}
DEPARTMENT_PROGRESS_TRANSITIONS = {
    "queued": {"in_progress", "blocked"},
    "assigned": {"in_progress", "blocked"},
    "claimed": {"in_progress", "blocked"},
    "in_progress": {"blocked", "ready_for_review", "completed"},
    "blocked": {"in_progress", "ready_for_review"},
    "ready_for_review": {"completed", "blocked", "in_progress"},
}
SAFE_LINK_KEYS = (
    "communication_message_id",
    "run_id",
    "task_lifecycle_id",
    "approval_task_id",
    "decision_record_id",
    "company_signal_id",
    "tool_execution_id",
    "asset_id",
    "asset_version_id",
    "report_run_id",
    "evaluation_run_id",
    "scorecard_id",
    "metric_snapshot_id",
)
HUMAN_APPROVAL_SATISFIED_STATUSES = {"approved", "resolved"}
AUTOMATED_GATE_SATISFIED_STATUSES = {"PASS", "WARN"}


class WhiteboardBoardError(ValueError):
    """Domain error for WorkWhiteboard board operations."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BoardMutationResult:
    record: TaskRoutingRecord
    changed: bool


class _Unset:
    pass


_UNSET = _Unset()


def build_whiteboard_board_snapshot(
    whiteboard: WorkWhiteboard,
    *,
    user: User | None = None,
    include_internal: bool | None = None,
) -> dict[str, Any]:
    """Build the board projection directly from durable DB state."""

    internal = (
        _can_view_internal(user=user, whiteboard=whiteboard)
        if include_internal is None
        else include_internal
    )
    can_structure = _can_modify_board_structure(user=user, whiteboard=whiteboard) if user else False
    can_update_any = (
        _can_update_any_assigned_card(user=user, whiteboard=whiteboard) if user else False
    )
    records = [
        record
        for record in _routing_records_for_whiteboard(whiteboard)
        if internal or _is_customer_visible(record)
    ]
    cards = [_card_payload(record, internal=internal, user=user) for record in records]
    lanes = _lanes_payload(cards)
    project = _project_payload(whiteboard, records=records, internal=internal)
    payload = {
        "whiteboard_id": str(whiteboard.id),
        "company_id": str(whiteboard.company_id),
        "company_name": whiteboard.company.name,
        "organization_id": str(whiteboard.organization_id),
        "organization_name": whiteboard.organization.name,
        "project": project,
        "departments": [
            _department_payload(department) for department in _board_departments(whiteboard.company)
        ],
        "lanes": lanes,
        "cards": cards,
        "allowed_actions": {
            "can_modify_structure": can_structure,
            "can_update_assigned_cards": can_update_any,
            "can_view_internal": internal,
        },
        "event_version": WHITEBOARD_BOARD_SNAPSHOT_VERSION,
        "snapshot_source": "db",
    }
    return sanitize_outbox_payload(payload)


def rebuild_whiteboard_board_snapshot_from_db(whiteboard_id: UUID | str) -> dict[str, Any] | None:
    whiteboard = _whiteboard_queryset().filter(id=whiteboard_id).first()
    if whiteboard is None:
        return None
    return refresh_whiteboard_board_redis_snapshot(whiteboard.id)


def refresh_whiteboard_board_redis_snapshot(whiteboard_id: UUID | str) -> dict[str, Any] | None:
    whiteboard = _whiteboard_queryset().filter(id=whiteboard_id).first()
    if whiteboard is None:
        return None
    payload = build_whiteboard_board_snapshot(whiteboard, include_internal=True)
    payload["snapshot_version"] = WHITEBOARD_BOARD_SNAPSHOT_VERSION
    payload["snapshot_refreshed_at"] = timezone.now().isoformat()
    key = whiteboard_board_snapshot_key(whiteboard)
    serialized = json.dumps(sanitize_outbox_payload(payload), sort_keys=True)
    ttl_seconds = whiteboard_snapshot_ttl_seconds()
    if not _use_cache_snapshot_store():
        try:
            redis_client = build_redis_client(
                db=int(
                    os.environ.get("WHITEBOARD_SNAPSHOT_REDIS_DB", os.environ.get("REDIS_DB", "0"))
                ),
                decode_responses=True,
            )
            redis_client.setex(key, ttl_seconds, serialized)
            return payload
        except Exception:
            pass
    cache.set(key, serialized, timeout=ttl_seconds)
    return payload


def whiteboard_board_snapshot_key(whiteboard: WorkWhiteboard) -> str:
    return f"{whiteboard_snapshot_key(whiteboard)}:board"


def list_whiteboard_cards_for_user(
    *,
    user: User,
    whiteboard_id: UUID | str,
) -> QuerySet[TaskRoutingRecord]:
    whiteboard = _whiteboard_queryset().filter(id=whiteboard_id).first()
    if whiteboard is None or not has_company_access(user, whiteboard.company, "viewer"):
        return TaskRoutingRecord.objects.none()
    queryset = _routing_records_for_whiteboard(whiteboard)
    if not _can_view_internal(user=user, whiteboard=whiteboard):
        queryset = queryset.filter(metadata_json__customer_visible=True)
    return queryset


def create_whiteboard_card(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    department_id: UUID | str,
    title: str,
    reason: str = "",
    assigned_user_id: UUID | str | None = None,
    status: str = "queued",
    priority: str = "normal",
    due_at: datetime | None = None,
    links: dict[str, Any] | None = None,
    customer_visible: bool = False,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    if not _can_modify_board_structure(user=user, whiteboard=whiteboard):
        raise WhiteboardBoardError("permission_denied", "Only routing can create board cards.")
    department = _department_for_board(whiteboard=whiteboard, department_id=department_id)
    assigned_user = _assigned_user_for_board(
        company=whiteboard.company,
        department=department,
        assigned_user_id=assigned_user_id,
    )
    board_status = _normalize_status(status)
    request_fingerprint = _mutation_fingerprint(
        {
            "department_id": str(department_id or ""),
            "title": title,
            "reason": reason,
            "assigned_user_id": str(assigned_user_id) if assigned_user_id is not None else None,
            "status": board_status,
            "priority": priority,
            "due_at": due_at.isoformat() if isinstance(due_at, datetime) else None,
            "links": links or {},
            "customer_visible": customer_visible,
        }
    )
    key = _mutation_key(whiteboard=whiteboard, action="create", idempotency_key=idempotency_key)
    if key:
        existing = _routing_records_for_whiteboard(whiteboard).filter(idempotency_key=key).first()
        if existing is not None:
            _already_applied(existing, idempotency_key, fingerprint=request_fingerprint)
            _set_idempotency_status(existing, "already_applied", idempotency_key)
            return existing
    metadata = {
        "whiteboard_id": str(whiteboard.id),
        "title": _bounded_text(title, 240),
        "customer_visible": bool(customer_visible),
        "links": _safe_links(links or {}),
        "board_card": True,
        "board_schema_version": WHITEBOARD_BOARD_SNAPSHOT_VERSION,
    }
    if idempotency_key:
        _mark_applied(
            metadata,
            idempotency_key,
            action="create",
            fingerprint=request_fingerprint,
        )
    record = TaskRoutingRecord(
        organization=whiteboard.organization,
        company=whiteboard.company,
        communication_thread=whiteboard.communication_thread,
        communication_message=whiteboard.source_message,
        service_engagement=whiteboard.service_engagement,
        to_department=department,
        assigned_user=assigned_user,
        reason=_bounded_text(reason or title, 4000),
        status=board_status,
        priority=_normalize_priority(priority),
        due_at=due_at,
        idempotency_key=key,
        metadata_json=sanitize_outbox_payload(metadata),
    )
    try:
        with transaction.atomic():
            record.full_clean()
            record.save()
            emit_whiteboard_board_event(
                event_type="whiteboard.card.created",
                whiteboard=whiteboard,
                record=record,
                actor=user,
                idempotency_key=key or f"whiteboard-board:{whiteboard.id}:card:{record.id}:created",
            )
            _refresh_after_commit(whiteboard.id)
    except IntegrityError:
        if key:
            existing = (
                _routing_records_for_whiteboard(whiteboard).filter(idempotency_key=key).first()
            )
            if existing is not None:
                _already_applied(existing, idempotency_key, fingerprint=request_fingerprint)
                _set_idempotency_status(existing, "already_applied", idempotency_key)
                return existing
        raise
    _set_idempotency_status(record, "applied", idempotency_key)
    return record


def update_whiteboard_card(  # noqa: C901
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    status: str | None = None,
    department_id: UUID | str | None = None,
    assigned_user_id: UUID | str | None = None,
    priority: str | None = None,
    due_at: datetime | None | object = _UNSET,
    blocker_reason: str = "",
    title: str | None = None,
    customer_visible: bool | None = None,
    expected_updated_at: str = "",
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    request_fingerprint = _mutation_fingerprint(
        {
            "status": status,
            "department_id": str(department_id or ""),
            "assigned_user_id": str(assigned_user_id) if assigned_user_id is not None else None,
            "priority": priority,
            "due_at": due_at.isoformat()
            if isinstance(due_at, datetime)
            else None
            if due_at is not _UNSET
            else "",
            "blocker_reason": blocker_reason,
            "title": title,
            "customer_visible": customer_visible,
        }
    )
    with transaction.atomic():
        record = _card_for_update(whiteboard=whiteboard, card_id=card_id)
        if _already_applied(record, idempotency_key, fingerprint=request_fingerprint):
            _set_idempotency_status(record, "already_applied", idempotency_key)
            return record
        _reject_stale_update(record, expected_updated_at)
        can_structure = _can_modify_board_structure(user=user, whiteboard=whiteboard)
        can_progress = _can_update_card_progress(user=user, record=record)
        if not can_structure and not can_progress:
            raise WhiteboardBoardError(
                "permission_denied", "You do not have permission to update this board card."
            )

        update_fields: set[str] = {"updated_at"}
        metadata = dict(record.metadata_json or {})
        resolution = dict(record.resolution_json or {})
        event_types: list[str] = []
        previous_status = record.status
        previous_department_id = str(record.to_department_id)
        previous_priority = record.priority
        previous_due_at = record.due_at.isoformat() if record.due_at else None

        if department_id:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can reassign board cards."
                )
            department = _department_for_board(whiteboard=whiteboard, department_id=department_id)
            if department.id != record.to_department_id:
                record.from_department = record.to_department
                record.to_department = department
                update_fields.update({"from_department", "to_department"})
                event_types.append("whiteboard.card.reassigned")

        if assigned_user_id is not None:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can change board card assignees."
                )
            assigned_user = _assigned_user_for_board(
                company=whiteboard.company,
                department=record.to_department,
                assigned_user_id=assigned_user_id,
            )
            if assigned_user != record.assigned_user:
                record.assigned_user = assigned_user
                update_fields.add("assigned_user")
                event_types.append("whiteboard.card.assigned")

        if priority is not None:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can change board card priority."
                )
            normalized_priority = _normalize_priority(priority)
            if normalized_priority != record.priority:
                record.priority = normalized_priority
                update_fields.add("priority")
                event_types.append("whiteboard.card.priority_changed")

        if due_at is not _UNSET:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can change board card due dates."
                )
            if due_at != record.due_at:
                record.due_at = due_at  # type: ignore[assignment]
                update_fields.add("due_at")
                event_types.append("whiteboard.card.due_date_changed")

        if title is not None:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can change board card titles."
                )
            metadata["title"] = _bounded_text(title, 240)
            update_fields.add("metadata_json")

        if customer_visible is not None:
            if not can_structure:
                raise WhiteboardBoardError(
                    "permission_denied", "Only routing can change customer visibility."
                )
            metadata["customer_visible"] = bool(customer_visible)
            update_fields.add("metadata_json")

        if status is not None:
            normalized_status = _normalize_status(status)
            if not can_structure:
                _validate_department_transition(record.status, normalized_status)
            if normalized_status == "completed" and _has_unsatisfied_human_approval(record):
                raise WhiteboardBoardError(
                    "human_approval_required",
                    "Human approval must be approved before this board card can be completed.",
                )
            if (
                normalized_status == "blocked"
                and not str(blocker_reason or resolution.get("blocker_reason") or "").strip()
            ):
                raise WhiteboardBoardError(
                    "blocker_reason_required", "Blocked cards require a blocker reason."
                )
            if normalized_status != record.status:
                record.status = normalized_status
                update_fields.add("status")
                event_types.append(_status_event_type(previous_status, normalized_status))
            _apply_status_resolution(
                resolution=resolution,
                status=normalized_status,
                blocker_reason=blocker_reason,
                actor=user,
            )
            update_fields.add("resolution_json")

        if idempotency_key:
            _mark_applied(
                metadata,
                idempotency_key,
                action="update",
                fingerprint=request_fingerprint,
            )
            update_fields.add("metadata_json")

        if "metadata_json" in update_fields:
            record.metadata_json = sanitize_outbox_payload(metadata)
        if "resolution_json" in update_fields:
            record.resolution_json = sanitize_outbox_payload(resolution)
        record.full_clean()
        record.save(update_fields=sorted(update_fields))
        if event_types:
            for event_type in dict.fromkeys(event_types):
                emit_whiteboard_board_event(
                    event_type=event_type,
                    whiteboard=whiteboard,
                    record=record,
                    actor=user,
                    previous_status=previous_status,
                    new_status=record.status,
                    previous_department_id=previous_department_id,
                    new_department_id=str(record.to_department_id),
                    previous_priority=previous_priority,
                    new_priority=record.priority,
                    previous_due_at=previous_due_at,
                    new_due_at=record.due_at.isoformat() if record.due_at else None,
                    idempotency_key=_event_idempotency_key(
                        whiteboard=whiteboard,
                        record=record,
                        event_type=event_type,
                        explicit=idempotency_key,
                    ),
                )
        _refresh_after_commit(whiteboard.id)
    _set_idempotency_status(record, "applied", idempotency_key)
    return record


def update_whiteboard_card_status(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    status: str,
    blocker_reason: str = "",
    idempotency_key: str = "",
    expected_updated_at: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        status=status,
        blocker_reason=blocker_reason,
        idempotency_key=idempotency_key,
        expected_updated_at=expected_updated_at,
    )


def reassign_whiteboard_card(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    department_id: UUID | str,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        department_id=department_id,
        idempotency_key=idempotency_key,
    )


def update_whiteboard_card_priority(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    priority: str,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        priority=priority,
        idempotency_key=idempotency_key,
    )


def update_whiteboard_card_due_date(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    due_at: datetime | None,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        due_at=due_at,
        idempotency_key=idempotency_key,
    )


def mark_whiteboard_card_blocked(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    blocker_reason: str,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card_status(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        status="blocked",
        blocker_reason=blocker_reason,
        idempotency_key=idempotency_key,
    )


def complete_whiteboard_card(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    return update_whiteboard_card_status(
        user=user,
        whiteboard=whiteboard,
        card_id=card_id,
        status="completed",
        idempotency_key=idempotency_key,
    )


def attach_card_evidence(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    card_id: UUID | str,
    evidence_type: str = "",
    target_id: UUID | str | None = None,
    summary: str = "",
    metadata: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> TaskRoutingRecord:
    request_fingerprint = _mutation_fingerprint(
        {
            "evidence_type": evidence_type,
            "target_id": str(target_id or ""),
            "summary": summary,
            "metadata": metadata or {},
        }
    )
    with transaction.atomic():
        record = _card_for_update(whiteboard=whiteboard, card_id=card_id)
        if _already_applied(record, idempotency_key, fingerprint=request_fingerprint):
            _set_idempotency_status(record, "already_applied", idempotency_key)
            return record
        if not (
            _can_modify_board_structure(user=user, whiteboard=whiteboard)
            or _can_update_card_progress(user=user, record=record)
        ):
            raise WhiteboardBoardError(
                "permission_denied", "You do not have permission to attach evidence."
            )
        resolution = dict(record.resolution_json or {})
        evidence = list(resolution.get("evidence") or [])
        safe_metadata = sanitize_outbox_payload(metadata or {})
        item = {
            "evidence_type": _bounded_text(evidence_type or "note", 64),
            "target_id": str(target_id or "")[:64],
            "summary": _bounded_text(summary, 600),
            "metadata": safe_metadata,
            "attached_by_id": str(user.id),
            "attached_at": timezone.now().isoformat(),
        }
        evidence.append(sanitize_outbox_payload(item))
        resolution["evidence"] = evidence[-25:]
        metadata_json = dict(record.metadata_json or {})
        if idempotency_key:
            _mark_applied(
                metadata_json,
                idempotency_key,
                action="evidence",
                fingerprint=request_fingerprint,
            )
        record.resolution_json = sanitize_outbox_payload(resolution)
        record.metadata_json = sanitize_outbox_payload(metadata_json)
        record.full_clean()
        record.save(update_fields=["resolution_json", "metadata_json", "updated_at"])
        emit_whiteboard_board_event(
            event_type="whiteboard.card.evidence_attached",
            whiteboard=whiteboard,
            record=record,
            actor=user,
            idempotency_key=_event_idempotency_key(
                whiteboard=whiteboard,
                record=record,
                event_type="whiteboard.card.evidence_attached",
                explicit=idempotency_key,
            ),
            extra={
                "evidence_type": item["evidence_type"],
                "target_id": item["target_id"],
            },
        )
        _refresh_after_commit(whiteboard.id)
    _set_idempotency_status(record, "applied", idempotency_key)
    return record


def emit_whiteboard_board_event(
    *,
    event_type: str,
    whiteboard: WorkWhiteboard,
    record: TaskRoutingRecord | None = None,
    actor: User | None = None,
    idempotency_key: str = "",
    previous_status: str | None = None,
    new_status: str | None = None,
    previous_department_id: str | None = None,
    new_department_id: str | None = None,
    previous_priority: str | None = None,
    new_priority: str | None = None,
    previous_due_at: str | None = None,
    new_due_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if event_type not in WHITEBOARD_BOARD_EVENT_TYPES:
        raise WhiteboardBoardError(
            "unsupported_event_type", "Unsupported whiteboard board event type."
        )
    now = timezone.now()
    routing_record_id = str(record.id) if record is not None else ""
    department_id = str(record.to_department_id) if record is not None else ""
    payload = sanitize_outbox_payload(
        {
            "schema_version": WHITEBOARD_BOARD_EVENT_SCHEMA_VERSION,
            "organization_id": str(whiteboard.organization_id),
            "company_id": str(whiteboard.company_id),
            "whiteboard_id": str(whiteboard.id),
            "routing_record_id": routing_record_id,
            "department_id": department_id,
            "previous_status": previous_status,
            "new_status": new_status or (record.status if record is not None else None),
            "previous_department_id": previous_department_id,
            "new_department_id": new_department_id,
            "previous_priority": previous_priority,
            "new_priority": new_priority,
            "previous_due_at": previous_due_at,
            "new_due_at": new_due_at,
            "actor_kind": "user" if actor is not None else "system",
            "actor_id": str(actor.id) if actor is not None else "",
            "created_at": now.isoformat(),
            "idempotency_key": idempotency_key,
            **(extra or {}),
        }
    )
    aggregate_id = record.id if record is not None else whiteboard.id
    aggregate_type = "task_routing_record" if record is not None else "work_whiteboard"
    record_domain_event(
        organization=whiteboard.organization,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_version=1,
        idempotency_key=idempotency_key
        or f"whiteboard-board:{whiteboard.id}:{event_type}:{now.timestamp()}",
        payload=payload,
        outbox_topic=WHITEBOARD_BOARD_OUTBOX_TOPIC,
        outbox_schema_version=WHITEBOARD_BOARD_EVENT_SCHEMA_VERSION,
        outbox_payload=payload,
        outbox_visibility="operator",
        outbox_company=whiteboard.company,
    )


def _routing_records_for_whiteboard(whiteboard: WorkWhiteboard) -> QuerySet[TaskRoutingRecord]:
    return (
        TaskRoutingRecord.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            metadata_json__whiteboard_id=str(whiteboard.id),
        )
        .select_related(
            "to_department",
            "from_department",
            "assigned_user",
            "task_lifecycle",
            "task_lifecycle__run",
            "operation",
            "approval_task",
            "company_signal",
            "communication_message",
        )
        .order_by("to_department__name", "due_at", "created_at")
    )


def _project_payload(
    whiteboard: WorkWhiteboard,
    *,
    records: list[TaskRoutingRecord],
    internal: bool,
) -> dict[str, Any]:
    blocked = [record for record in records if _board_status(record.status) == "blocked"]
    classification = _classification_payload(whiteboard) if internal else None
    project_name = whiteboard.project_name or whiteboard.client_name or whiteboard.request_type
    work_status = effective_work_status_for_whiteboard(whiteboard)
    payload = {
        "title": project_name or "Project",
        "project_name": project_name or "Project",
        "request_classification": classification,
        "ultimate_goal": _bounded_text(whiteboard.objective or whiteboard.request_summary, 1200),
        "context_summary": _bounded_text(whiteboard.request_summary or whiteboard.objective, 1200),
        "constraints_summary": _summary_from_mapping(whiteboard.constraints_json),
        "work_status": work_status,
        "status": work_status,
        "legacy_status": whiteboard.status,
        "semantic_aliases": whiteboard_semantic_aliases(whiteboard),
        "completion_score": whiteboard.completion_score,
        "risk_blocker_summary": _risk_blocker_summary(whiteboard=whiteboard, blocked=blocked),
        "service_engagement_id": str(whiteboard.service_engagement_id)
        if whiteboard.service_engagement_id
        else None,
        "communication_thread_id": str(whiteboard.communication_thread_id)
        if whiteboard.communication_thread_id
        else None,
        "source_message_id": str(whiteboard.source_message_id)
        if whiteboard.source_message_id
        else None,
        "updated_at": whiteboard.updated_at.isoformat(),
    }
    if not internal:
        payload.pop("request_classification", None)
    return payload


def _classification_payload(whiteboard: WorkWhiteboard) -> dict[str, Any] | None:
    classification = (
        RequestClassificationRecord.objects.filter(
            Q(matched_whiteboard=whiteboard) | Q(communication_message=whiteboard.source_message),
            organization=whiteboard.organization,
            company=whiteboard.company,
        )
        .order_by("-created_at")
        .first()
    )
    if classification is None:
        return None
    return {
        "id": str(classification.id),
        "classification": classification.classification,
        "confidence": classification.confidence,
    }


def _card_payload(
    record: TaskRoutingRecord, *, internal: bool, user: User | None
) -> dict[str, Any]:
    metadata = dict(record.metadata_json or {})
    resolution = dict(record.resolution_json or {})
    title = str(metadata.get("title") or "").strip() or _bounded_text(record.reason, 160)
    blocker_reason = str(
        resolution.get("blocker_reason") or metadata.get("blocker_reason") or ""
    ).strip()
    links = _links_for_record(record)
    visible_links = links if internal else _customer_safe_links(links, metadata)
    review = _review_payload(record, links=visible_links, internal=internal)
    payload = {
        "id": str(record.id),
        "routing_record_id": str(record.id),
        "title": title,
        "reason": _bounded_text(record.reason, 1000) if internal else "",
        "department_id": str(record.to_department_id),
        "department_slug": record.to_department.slug,
        "department_name": record.to_department.name,
        "assigned_user_id": str(record.assigned_user_id) if record.assigned_user_id else None,
        "status": _board_status(record.status),
        "priority": record.priority,
        "due_at": record.due_at.isoformat() if record.due_at else None,
        "sla_state": _sla_state(record),
        "blocker_reason": _bounded_text(blocker_reason, 600) if internal else "",
        "links": visible_links,
        "review_kind": review["kind"] if review else None,
        "review": review,
        "customer_visible": bool(metadata.get("customer_visible")),
        "evidence": list(resolution.get("evidence") or [])[-5:] if internal else [],
        "allowed_actions": _card_allowed_actions(user=user, record=record),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    return sanitize_outbox_payload(payload)


def _links_for_record(record: TaskRoutingRecord) -> dict[str, Any]:
    metadata = dict(record.metadata_json or {})
    links = dict(metadata.get("links") or {})
    task_lifecycle = record.task_lifecycle
    run_id = str(task_lifecycle.run_id) if task_lifecycle is not None else ""
    if not run_id and record.operation_id:
        run_id = str(record.operation_id)
    direct = {
        "communication_message_id": str(record.communication_message_id)
        if record.communication_message_id
        else "",
        "run_id": run_id,
        "task_lifecycle_id": str(record.task_lifecycle_id) if record.task_lifecycle_id else "",
        "approval_task_id": str(record.approval_task_id) if record.approval_task_id else "",
        "company_signal_id": str(record.company_signal_id) if record.company_signal_id else "",
    }
    for key in SAFE_LINK_KEYS:
        if direct.get(key):
            continue
        direct[key] = str(links.get(key) or metadata.get(key) or "")
    return {key: value for key, value in direct.items() if value}


def _customer_safe_links(links: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    visible = set(metadata.get("customer_visible_links") or [])
    return {key: value for key, value in links.items() if key in visible}


def _review_payload(
    record: TaskRoutingRecord, *, links: dict[str, Any], internal: bool
) -> dict[str, Any] | None:
    if _board_status(record.status) != "ready_for_review":
        return None

    approval_task_id = str(links.get("approval_task_id") or "")
    if (
        approval_task_id
        and record.approval_task_id
        and approval_task_id == str(record.approval_task_id)
    ):
        decision = _approval_decision(record)
        satisfied = _human_approval_satisfied(record, decision=decision)
        payload = {
            "kind": "human_approval",
            "label": "Human approval required" if not satisfied else "Human approval satisfied",
            "satisfied": satisfied,
            "approval_task_id": approval_task_id,
            "approval_status": _approval_status(record),
        }
        decision_record_id = str(decision.id) if decision else ""
        if internal or (decision_record_id and links.get("decision_record_id") == decision_record_id):
            payload["decision_record_id"] = decision_record_id
        return payload

    evaluation_run_id = str(links.get("evaluation_run_id") or "")
    evaluation = _evaluation_for_link(record, evaluation_run_id)
    if evaluation is not None:
        scorecard = EvaluationScorecard.objects.filter(
            organization=record.organization,
            company=record.company,
            evaluation=evaluation,
        ).first()
        satisfied = evaluation.status in AUTOMATED_GATE_SATISFIED_STATUSES
        payload = {
            "kind": "automated_gate",
            "label": "Automated evaluation required"
            if not satisfied
            else "Automated evaluation satisfied",
            "satisfied": satisfied,
            "evaluation_run_id": str(evaluation.id),
            "evaluation_status": evaluation.status,
        }
        scorecard_id = str(scorecard.id) if scorecard else ""
        if internal or (scorecard_id and links.get("scorecard_id") == scorecard_id):
            payload["scorecard_id"] = scorecard_id
        return payload

    return {
        "kind": "department",
        "label": "Department review required",
        "satisfied": False,
        "department_id": str(record.to_department_id),
        "department_slug": record.to_department.slug,
        "department_name": record.to_department.name,
    }


def _lanes_payload(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for card in cards:
        department_id = str(card["department_id"])
        lane = lanes.setdefault(
            department_id,
            {
                "department_id": department_id,
                "department_slug": card["department_slug"],
                "department_name": card["department_name"],
                "cards": [],
            },
        )
        lane["cards"].append(card)
    return sorted(lanes.values(), key=lambda lane: str(lane["department_name"]).lower())


def _board_departments(company: Graph) -> QuerySet[DepartmentRegistry]:
    return DepartmentRegistry.objects.filter(
        organization=company.organization, active=True
    ).order_by("name", "slug")


def _department_payload(department: DepartmentRegistry) -> dict[str, Any]:
    return {
        "department_id": str(department.id),
        "department_slug": department.slug,
        "department_name": department.name,
        "department_type": department.department_type,
        "active": department.active,
        "is_routing_department": _is_routing_department(department),
    }


def _risk_blocker_summary(*, whiteboard: WorkWhiteboard, blocked: list[TaskRoutingRecord]) -> str:
    if blocked:
        return f"{len(blocked)} blocked card{'s' if len(blocked) != 1 else ''} need attention."
    missing = list(whiteboard.work_missing_fields_json or whiteboard.missing_fields_json or [])
    if missing:
        return f"{len(missing)} required context field{'s' if len(missing) != 1 else ''} still missing."
    return "No active blockers recorded."


def _summary_from_mapping(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    entries = []
    for key, item in value.items():
        if item in (None, "", [], {}):
            continue
        entries.append(f"{str(key).replace('_', ' ')}: {item}")
        if len(entries) >= 3:
            break
    return _bounded_text("; ".join(entries), 1000)


def _department_for_board(
    *, whiteboard: WorkWhiteboard, department_id: UUID | str
) -> DepartmentRegistry:
    department = DepartmentRegistry.objects.filter(
        organization=whiteboard.organization,
        id=department_id,
    ).first()
    if department is None:
        raise WhiteboardBoardError("department_not_found", "Department was not found.")
    if not department.active:
        raise WhiteboardBoardError(
            "department_inactive", "Inactive departments cannot own board cards."
        )
    return department


def _assigned_user_for_board(
    *,
    company: Graph,
    department: DepartmentRegistry,
    assigned_user_id: UUID | str | None,
) -> User | None:
    if not assigned_user_id:
        return None
    assigned_user = User.objects.filter(id=assigned_user_id).first()
    if assigned_user is None:
        raise WhiteboardBoardError("assigned_user_not_found", "Assigned user was not found.")
    if not has_company_access(assigned_user, company, "viewer"):
        raise WhiteboardBoardError(
            "assigned_user_company_access_required", "Assigned user must have company access."
        )
    if active_department_membership(user=assigned_user, department=department) is None:
        raise WhiteboardBoardError(
            "assigned_user_department_member_required",
            "Assigned user must belong to the target department.",
        )
    return assigned_user


def _card_for_update(*, whiteboard: WorkWhiteboard, card_id: UUID | str) -> TaskRoutingRecord:
    record = (
        TaskRoutingRecord.objects.select_for_update(of=("self",))
        .filter(
            id=card_id,
            organization=whiteboard.organization,
            company=whiteboard.company,
            metadata_json__whiteboard_id=str(whiteboard.id),
        )
        .first()
    )
    if record is None:
        raise WhiteboardBoardError("card_not_found", "Board card was not found.")
    return record


def _can_view_internal(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _can_modify_board_structure(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None or not has_company_access(user, whiteboard.company, "member"):
        return False
    if has_min_role(user, "admin", str(whiteboard.organization_id)):
        return True
    routing_departments = [
        department
        for department in DepartmentRegistry.objects.filter(
            organization=whiteboard.organization,
            active=True,
        )
        if _is_routing_department(department)
    ]
    return any(
        has_department_role(user, department, "member") for department in routing_departments
    )


def _can_update_card_progress(*, user: User | None, record: TaskRoutingRecord) -> bool:
    if user is None or not has_company_access(user, record.company, "member"):
        return False
    return has_department_role(user, record.to_department, "member")


def _can_update_any_assigned_card(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return any(
        _can_update_card_progress(user=user, record=record)
        for record in _routing_records_for_whiteboard(whiteboard)
    )


def _card_allowed_actions(*, user: User | None, record: TaskRoutingRecord) -> list[str]:
    if user is None:
        return []
    can_structure = _can_modify_board_structure(
        user=user, whiteboard=_whiteboard_for_record(record)
    )
    can_progress = _can_update_card_progress(user=user, record=record)
    actions: list[str] = []
    if can_progress or can_structure:
        if record.status in {"queued", "assigned", "claimed", "blocked", "ready_for_review"}:
            actions.append("start")
        if record.status in {"queued", "assigned", "claimed", "in_progress", "ready_for_review"}:
            actions.append("block")
        if record.status in {"in_progress", "blocked"}:
            actions.append("ready_for_review")
        if record.status in {
            "in_progress",
            "ready_for_review",
        } and not _has_unsatisfied_human_approval(record):
            actions.append("complete")
        actions.append("evidence")
    if can_structure:
        actions.extend(
            ["reassign", "priority", "due_date", "close", "reopen", "customer_visibility"]
        )
    return sorted(set(actions))


def _whiteboard_for_record(record: TaskRoutingRecord) -> WorkWhiteboard:
    whiteboard_id = str((record.metadata_json or {}).get("whiteboard_id") or "")
    return WorkWhiteboard.objects.select_related("organization", "company").get(id=whiteboard_id)


def _is_routing_department(department: DepartmentRegistry) -> bool:
    tags = {str(item).lower() for item in (department.service_tags_json or [])}
    return department.active and (
        str(department.slug).lower() in ROUTING_DEPARTMENT_MARKERS
        or str(department.department_type).lower() in ROUTING_DEPARTMENT_MARKERS
        or bool(tags.intersection(ROUTING_DEPARTMENT_MARKERS))
    )


def _is_customer_visible(record: TaskRoutingRecord) -> bool:
    return bool((record.metadata_json or {}).get("customer_visible"))


def _board_status(status: str) -> str:
    if status == "claimed":
        return "in_progress"
    return status if status in BOARD_STATUS_CONTRACT else "queued"


def _normalize_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in BOARD_STATUSES:
        raise WhiteboardBoardError("invalid_status", "Board card status is invalid.")
    return status


def _normalize_priority(value: str) -> str:
    priority = str(value or "").strip().lower() or "normal"
    if priority not in BOARD_PRIORITIES:
        raise WhiteboardBoardError("invalid_priority", "Board card priority is invalid.")
    return priority


def _has_unsatisfied_human_approval(record: TaskRoutingRecord) -> bool:
    return record.approval_task_id is not None and not _human_approval_satisfied(record)


def _approval_status(record: TaskRoutingRecord) -> str:
    if record.approval_task is None:
        return ""
    return record.approval_task.status


def _human_approval_satisfied(
    record: TaskRoutingRecord,
    *,
    decision: DecisionRecord | None = None,
) -> bool:
    if record.approval_task_id is None:
        return True
    if record.approval_task is None:
        return False
    if record.approval_task.status == "approved":
        return True
    approval_decision = decision or _approval_decision(record)
    return bool(
        approval_decision
        and approval_decision.status in HUMAN_APPROVAL_SATISFIED_STATUSES
        and approval_decision.decision_type == "human_approval"
    )


def _approval_decision(record: TaskRoutingRecord) -> DecisionRecord | None:
    if record.approval_task_id is None:
        return None
    return (
        DecisionRecord.objects.filter(
            organization=record.organization,
            source_approval_task_id=record.approval_task_id,
            decision_type="human_approval",
        )
        .order_by("-resolved_at", "-updated_at", "-created_at")
        .first()
    )


def _evaluation_for_link(record: TaskRoutingRecord, evaluation_run_id: str) -> EvaluationRun | None:
    candidate = str(evaluation_run_id or "").strip()
    if not candidate:
        return None
    try:
        evaluation_id = UUID(candidate)
    except ValueError:
        return None
    return EvaluationRun.objects.filter(
        id=evaluation_id,
        organization=record.organization,
        company=record.company,
    ).first()


def _validate_department_transition(previous: str, new: str) -> None:
    if previous == new:
        return
    if previous in {"completed", "cancelled"}:
        raise WhiteboardBoardError(
            "invalid_status_transition", "Completed or cancelled cards require routing to reopen."
        )
    allowed = DEPARTMENT_PROGRESS_TRANSITIONS.get(previous, set())
    if new not in allowed:
        raise WhiteboardBoardError(
            "invalid_status_transition", "Assigned departments cannot make that board transition."
        )


def _apply_status_resolution(
    *,
    resolution: dict[str, Any],
    status: str,
    blocker_reason: str,
    actor: User,
) -> None:
    if status == "blocked":
        resolution["blocker_reason"] = _bounded_text(
            blocker_reason or str(resolution.get("blocker_reason") or ""), 600
        )
        resolution["blocked_by_id"] = str(actor.id)
        resolution["blocked_at"] = timezone.now().isoformat()
    elif status in {"in_progress", "ready_for_review", "completed"}:
        resolution.pop("blocker_reason", None)
        if status == "completed":
            resolution["completed_by_id"] = str(actor.id)
            resolution["completed_at"] = timezone.now().isoformat()


def _status_event_type(previous: str, new: str) -> str:
    if new == "blocked":
        return "whiteboard.card.blocked"
    if previous == "blocked" and new != "blocked":
        return "whiteboard.card.unblocked"
    if new == "completed":
        return "whiteboard.card.completed"
    return "whiteboard.card.status_changed"


def _reject_stale_update(record: TaskRoutingRecord, expected_updated_at: str) -> None:
    expected = str(expected_updated_at or "").strip()
    if not expected:
        return
    if expected != record.updated_at.isoformat():
        raise WhiteboardBoardError(
            "stale_card_version", "Board card was updated by another writer."
        )


def _already_applied(
    record: TaskRoutingRecord,
    idempotency_key: str,
    *,
    fingerprint: str = "",
) -> bool:
    key = str(idempotency_key or "").strip()
    if not key:
        return False
    applied = dict((record.metadata_json or {}).get("board_idempotency") or {})
    if key not in applied:
        return False
    previous = applied.get(key)
    if (
        isinstance(previous, dict)
        and fingerprint
        and previous.get("fingerprint") not in {"", fingerprint}
    ):
        raise WhiteboardBoardError(
            "idempotency_conflict",
            "Idempotency key was already used for a different board mutation.",
        )
    return True


def _mark_applied(
    metadata: dict[str, Any],
    idempotency_key: str,
    *,
    action: str,
    fingerprint: str = "",
) -> None:
    key = str(idempotency_key or "").strip()[:255]
    if not key:
        return
    applied = dict(metadata.get("board_idempotency") or {})
    applied[key] = {
        "action": action,
        "fingerprint": fingerprint,
        "applied_at": timezone.now().isoformat(),
    }
    metadata["board_idempotency"] = dict(list(applied.items())[-50:])


def _set_idempotency_status(
    record: TaskRoutingRecord,
    status: str,
    idempotency_key: str,
) -> None:
    if idempotency_key:
        setattr(record, "_whiteboard_board_idempotency_status", status)
        setattr(record, "_whiteboard_board_idempotency_key", idempotency_key)


def _mutation_fingerprint(value: dict[str, Any]) -> str:
    safe = sanitize_outbox_payload(value)
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))[:512]


def _mutation_key(*, whiteboard: WorkWhiteboard, action: str, idempotency_key: str) -> str:
    key = str(idempotency_key or "").strip()
    if not key:
        return ""
    return f"whiteboard-board:{whiteboard.id}:{action}:{key}"[:255]


def _event_idempotency_key(
    *,
    whiteboard: WorkWhiteboard,
    record: TaskRoutingRecord,
    event_type: str,
    explicit: str,
) -> str:
    if explicit:
        return f"whiteboard-board-event:{whiteboard.id}:{record.id}:{event_type}:{explicit}"[:255]
    return f"whiteboard-board-event:{whiteboard.id}:{record.id}:{event_type}:{record.updated_at.isoformat()}"[
        :255
    ]


def _safe_links(value: dict[str, Any]) -> dict[str, str]:
    links: dict[str, str] = {}
    for key in SAFE_LINK_KEYS:
        raw = value.get(key)
        if raw:
            links[key] = str(raw)[:128]
    return links


def _bounded_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _sla_state(record: TaskRoutingRecord) -> str:
    now = timezone.now()
    if record.sla_breached_at or (
        record.due_at and record.due_at < now and record.status not in {"completed", "cancelled"}
    ):
        return "breached"
    if record.due_at and record.due_at <= now + timedelta(hours=24):
        return "due_soon"
    return "ok"


def _refresh_after_commit(whiteboard_id: UUID | str) -> None:
    transaction.on_commit(lambda: refresh_whiteboard_board_redis_snapshot(whiteboard_id))


def _use_cache_snapshot_store() -> bool:
    default_cache = settings.CACHES.get("default", {})
    backend = str(default_cache.get("BACKEND", "")).lower()
    return "locmem" in backend
