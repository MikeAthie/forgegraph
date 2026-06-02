from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status as drf_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.projections.dispatcher import PROJECTION_NAMES
from application.services.idempotency import record_idempotency_observation
from application.services.operator_actions import record_operator_action, resolve_dead_letter_record
from application.services.ops_permissions import (
    OPS_DEAD_LETTER_READ,
    OPS_DEAD_LETTER_REPLAY,
    OPS_PROJECTION_READ,
    has_ops_permission,
)
from application.services.os_projections import projection_metadata
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.redaction import redact_payload
from application.services.runtime_transport_observability import (
    get_runtime_transport_observability_snapshot,
)
from application.services.runtime_write_intents import (
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
    build_runtime_intent_redis_client,
    decode_runtime_intent_message,
)
from application.services.whiteboard_board_kafka import (
    whiteboard_board_kafka_transport_evidence,
)
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    AuditLog,
    DomainEvent,
    EventDeadLetterRecord,
    OperatorActionLog,
    Organization,
    OrganizationStateFeedEvent,
    ProcessedProjectionEvent,
    ProjectionCursor,
    Run,
    RuntimeIntentOutcome,
    TaskDeadLetterRecord,
    User,
)

ACTIVE_EVENT_DEAD_LETTER_STATUSES = {"active", "replay_requested"}
ACTIVE_TASK_DEAD_LETTER_STATUSES = {"active"}


def _user(request: Request) -> User | None:
    user = request.user
    return user if isinstance(user, User) else None


def _organization_for_request(request: Request) -> Organization | None:
    user = _user(request)
    if user is None or user.default_organization_id is None:
        return None
    return Organization.objects.filter(id=user.default_organization_id).first()


def _permission_denied() -> Response:
    return error_response(
        "FORBIDDEN",
        "You don't have permission to use operator recovery controls.",
        status=drf_status.HTTP_403_FORBIDDEN,
    )


def _require_ops_permission(
    request: Request, permission: str
) -> tuple[User, Organization] | Response:
    user = _user(request)
    organization = _organization_for_request(request)
    if user is None or organization is None:
        return _permission_denied()
    if not has_ops_permission(user, permission, organization_id=str(organization.id)):
        return _permission_denied()
    return user, organization


def _reason(request: Request) -> str:
    return str(request.data.get("reason") or "").strip()[:1000]


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        "IDEMPOTENCY_CONFLICT",
        str(exc),
        status=drf_status.HTTP_409_CONFLICT,
        details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
    )


def _action_context(
    *,
    request: Request,
    organization: Organization,
    action: str,
    require_key: bool,
) -> tuple[Any, Response | None]:
    key = idempotency_key_from_request(request)
    if require_key and not key:
        return None, error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for operator recovery actions.",
            status=drf_status.HTTP_400_BAD_REQUEST,
        )
    return (
        build_idempotency_context(
            request=request,
            organization=organization,
            action=action,
            request_payload=request.data,
        ),
        None,
    )


def _parse_dead_letter_key(dead_letter_key: str) -> tuple[str, UUID] | Response:
    prefix, separator, value = str(dead_letter_key or "").partition(":")
    if not separator or prefix not in {"task", "event", "runtime_intent"}:
        return error_response("NOT_FOUND", "Dead letter not found.", status=404)
    try:
        return prefix, UUID(value)
    except ValueError:
        return error_response("NOT_FOUND", "Dead letter not found.", status=404)


def _task_queryset(organization: Organization) -> models.QuerySet[TaskDeadLetterRecord]:
    return (
        TaskDeadLetterRecord.objects.filter(lifecycle_task__organization=organization)
        .select_related("lifecycle_task", "run", "runtime_intent_outcome", "acknowledged_by")
        .order_by("-created_at")
    )


def _event_queryset(organization: Organization) -> models.QuerySet[EventDeadLetterRecord]:
    return (
        EventDeadLetterRecord.objects.filter(organization=organization)
        .select_related("organization", "run", "acknowledged_by", "replay_requested_by")
        .order_by("-last_seen_at")
    )


def _runtime_queryset(organization: Organization) -> models.QuerySet[RuntimeIntentOutcome]:
    return (
        RuntimeIntentOutcome.objects.filter(
            run__organization=organization,
            outcome="dead_lettered",
            acknowledged_at__isnull=True,
        )
        .select_related("run", "acknowledged_by")
        .order_by("-processed_at")
    )


def _fetch_dead_letter(
    *,
    organization: Organization,
    dead_letter_key: str,
) -> tuple[str, TaskDeadLetterRecord | EventDeadLetterRecord | RuntimeIntentOutcome] | Response:
    parsed = _parse_dead_letter_key(dead_letter_key)
    if isinstance(parsed, Response):
        return parsed
    kind, native_id = parsed
    item: TaskDeadLetterRecord | EventDeadLetterRecord | RuntimeIntentOutcome | None
    if kind == "task":
        item = _task_queryset(organization).filter(id=native_id).first()
    elif kind == "event":
        item = _event_queryset(organization).filter(id=native_id).first()
    else:
        item = _runtime_queryset(organization).filter(intent_id=native_id).first()
    if item is None:
        return error_response("NOT_FOUND", "Dead letter not found.", status=404)
    return kind, item


def _dead_letter_key(kind: str, native_id: Any) -> str:
    return f"{kind}:{native_id}"


def _task_dead_letter_summary(item: TaskDeadLetterRecord) -> dict[str, Any]:
    return {
        "id": _dead_letter_key("task", item.id),
        "native_id": str(item.id),
        "kind": "task",
        "organization_id": str(item.lifecycle_task.organization_id),
        "run_id": str(item.run_id),
        "status": item.status,
        "title": item.lifecycle_task.title or item.lifecycle_task.source_node_id,
        "source": "task_lifecycle",
        "event_type": "task.dead_lettered",
        "intent_id": str(item.intent_id) if item.intent_id else None,
        "reason": item.reason,
        "last_error": item.last_error,
        "retry_count": 0,
        "attempt_count": item.attempt_count,
        "created_at": item.created_at.isoformat(),
        "last_seen_at": item.updated_at.isoformat(),
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "recovery_options": item.recovery_options,
        "actions": _actions_for_task_dead_letter(item),
    }


def _event_dead_letter_summary(item: EventDeadLetterRecord) -> dict[str, Any]:
    return {
        "id": _dead_letter_key("event", item.id),
        "native_id": str(item.id),
        "kind": "event",
        "organization_id": str(item.organization_id) if item.organization_id else None,
        "run_id": str(item.run_id) if item.run_id else None,
        "status": item.status,
        "title": item.event_type or item.source,
        "source": item.source,
        "event_type": item.event_type,
        "event_id": item.event_id,
        "idempotency_key": item.idempotency_key,
        "reason": item.reason,
        "last_error": item.error_class,
        "retry_count": item.retry_count,
        "attempt_count": item.retry_count,
        "created_at": item.first_seen_at.isoformat(),
        "last_seen_at": item.last_seen_at.isoformat(),
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "recovery_options": _actions_for_event_dead_letter(item),
        "actions": _actions_for_event_dead_letter(item),
    }


def _runtime_intent_summary(item: RuntimeIntentOutcome) -> dict[str, Any]:
    run = item.run if item.run_id else None
    return {
        "id": _dead_letter_key("runtime_intent", item.intent_id),
        "native_id": str(item.intent_id),
        "kind": "runtime_intent",
        "organization_id": str(run.organization_id) if run is not None else None,
        "run_id": str(item.run_id) if item.run_id else None,
        "status": item.outcome,
        "title": item.intent_type or "runtime intent",
        "source": "runtime_intent_transport",
        "event_type": item.intent_type,
        "intent_id": str(item.intent_id),
        "reason": item.reason,
        "last_error": item.error_class,
        "retry_count": 0,
        "attempt_count": 0,
        "created_at": item.processed_at.isoformat(),
        "last_seen_at": item.updated_at.isoformat(),
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "recovery_options": ["replay", "resolve"],
        "actions": ["replay", "resolve"],
    }


def _actions_for_task_dead_letter(item: TaskDeadLetterRecord) -> list[str]:
    actions = ["resolve"]
    if item.status == "active" and item.intent_id and "replay_intent" in item.recovery_options:
        actions.insert(0, "replay")
    return actions


def _actions_for_event_dead_letter(item: EventDeadLetterRecord) -> list[str]:
    actions = ["resolve"]
    if item.status in ACTIVE_EVENT_DEAD_LETTER_STATUSES and item.source == "os_projection_worker":
        actions.insert(0, "replay")
    return actions


def _dead_letter_detail(
    organization: Organization,
    kind: str,
    item: TaskDeadLetterRecord | EventDeadLetterRecord | RuntimeIntentOutcome,
) -> dict[str, Any]:
    if kind == "task":
        summary = _task_dead_letter_summary(cast(TaskDeadLetterRecord, item))
        payload: dict[str, Any] = {}
        target_type = "task"
        target_id = str(cast(TaskDeadLetterRecord, item).id)
    elif kind == "event":
        event_item = cast(EventDeadLetterRecord, item)
        summary = _event_dead_letter_summary(event_item)
        payload = redact_payload(event_item.payload)
        target_type = "event"
        target_id = str(event_item.id)
    else:
        runtime_item = cast(RuntimeIntentOutcome, item)
        summary = _runtime_intent_summary(runtime_item)
        payload = {
            "intent_id": str(runtime_item.intent_id),
            "intent_type": runtime_item.intent_type,
            "attempt_id": runtime_item.attempt_id,
            "stream_message_id": runtime_item.stream_message_id,
        }
        target_type = "runtime_intent"
        target_id = str(runtime_item.intent_id)
    return {
        **summary,
        "payload": payload,
        "operator_actions": _operator_action_history(organization, target_type, target_id),
        "audit_history": _audit_history(organization, target_type, target_id),
    }


def _operator_action_history(
    organization: Organization,
    target_type: str,
    target_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(action.id),
            "action": action.action,
            "status": action.status,
            "reason": action.reason,
            "actor_id": str(action.actor_id) if action.actor_id else None,
            "idempotency_key": action.idempotency_key,
            "metadata": redact_payload(action.metadata),
            "created_at": action.created_at.isoformat(),
        }
        for action in OperatorActionLog.objects.filter(
            organization=organization,
            target_type=target_type,
            target_id=target_id,
        ).order_by("-created_at")[:25]
    ]


def _audit_history(
    organization: Organization, target_type: str, target_id: str
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "metadata": redact_payload(row.metadata),
            "created_at": row.created_at.isoformat(),
        }
        for row in AuditLog.objects.filter(
            tenant_id=organization.id,
            resource_type=target_type,
            resource_id=target_id,
        ).order_by("-created_at")[:25]
    ]


class OpsDeadLetterListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        allowed = _require_ops_permission(request, OPS_DEAD_LETTER_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed
        task_items = [
            _task_dead_letter_summary(item) for item in _task_queryset(organization)[:100]
        ]
        event_items = [
            _event_dead_letter_summary(item) for item in _event_queryset(organization)[:100]
        ]
        runtime_items = [
            _runtime_intent_summary(item) for item in _runtime_queryset(organization)[:100]
        ]
        items = sorted(
            [*task_items, *event_items, *runtime_items],
            key=lambda item: str(item.get("last_seen_at") or item.get("created_at") or ""),
            reverse=True,
        )
        active_count = sum(
            1
            for item in items
            if item.get("status") in {"active", "replay_requested", "dead_lettered"}
        )
        return success_response(
            {
                "organization_id": str(organization.id),
                "items": items[:200],
                "counts": {
                    "total": len(items),
                    "active": active_count,
                    "task": len(task_items),
                    "event": len(event_items),
                    "runtime_intent": len(runtime_items),
                },
            }
        )


class OpsDeadLetterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, dead_letter_key: str) -> Response:
        allowed = _require_ops_permission(request, OPS_DEAD_LETTER_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed
        fetched = _fetch_dead_letter(organization=organization, dead_letter_key=dead_letter_key)
        if isinstance(fetched, Response):
            return fetched
        kind, item = fetched
        return success_response(_dead_letter_detail(organization, kind, item))


class OpsDeadLetterReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, dead_letter_key: str) -> Response:
        allowed = _require_ops_permission(request, OPS_DEAD_LETTER_REPLAY)
        if isinstance(allowed, Response):
            return allowed
        user, organization = allowed
        reason = _reason(request)
        if not reason:
            return error_response("VALIDATION_ERROR", "A reason is required.", status=400)
        context, context_error = _action_context(
            request=request,
            organization=organization,
            action=f"ops.dead_letter.replay:{dead_letter_key}",
            require_key=True,
        )
        if context_error is not None:
            return context_error
        try:
            replayed_response = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replayed_response is not None:
            return replayed_response
        fetched = _fetch_dead_letter(organization=organization, dead_letter_key=dead_letter_key)
        if isinstance(fetched, Response):
            return fetched
        kind, item = fetched
        if kind == "runtime_intent":
            response = _replay_runtime_intent(
                user=user,
                organization=organization,
                outcome=cast(RuntimeIntentOutcome, item),
                reason=reason,
                dead_letter_key=dead_letter_key,
                idempotency_key=idempotency_key_from_request(request),
            )
        elif kind == "task":
            response = _replay_task_dead_letter(
                user=user,
                organization=organization,
                dead_letter=cast(TaskDeadLetterRecord, item),
                reason=reason,
                dead_letter_key=dead_letter_key,
                idempotency_key=idempotency_key_from_request(request),
            )
        else:
            response = _replay_event_dead_letter(
                user=user,
                organization=organization,
                dead_letter=cast(EventDeadLetterRecord, item),
                reason=reason,
                dead_letter_key=dead_letter_key,
                idempotency_key=idempotency_key_from_request(request),
            )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="dead_letter",
            resource_id=dead_letter_key,
        )


class OpsDeadLetterResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, dead_letter_key: str) -> Response:
        allowed = _require_ops_permission(request, OPS_DEAD_LETTER_REPLAY)
        if isinstance(allowed, Response):
            return allowed
        user, organization = allowed
        reason = _reason(request)
        if not reason:
            return error_response("VALIDATION_ERROR", "A reason is required.", status=400)
        context, _ = _action_context(
            request=request,
            organization=organization,
            action=f"ops.dead_letter.resolve:{dead_letter_key}",
            require_key=False,
        )
        try:
            replayed_response = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replayed_response is not None:
            return replayed_response
        fetched = _fetch_dead_letter(organization=organization, dead_letter_key=dead_letter_key)
        if isinstance(fetched, Response):
            return fetched
        kind, item = fetched
        response = _resolve_dead_letter(
            user=user,
            organization=organization,
            kind=kind,
            item=item,
            reason=reason,
            dead_letter_key=dead_letter_key,
            idempotency_key=idempotency_key_from_request(request),
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="dead_letter",
            resource_id=dead_letter_key,
        )


class OpsProjectionLagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        allowed = _require_ops_permission(request, OPS_PROJECTION_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed
        metadata = projection_metadata(organization)
        latest_event = (
            DomainEvent.objects.filter(organization=organization).order_by("-sequence").first()
        )
        cursors = ProjectionCursor.objects.filter(organization=organization).order_by(
            "projection_name"
        )
        active_dead_letters = EventDeadLetterRecord.objects.filter(
            organization=organization,
            source="os_projection_worker",
            status__in=ACTIVE_EVENT_DEAD_LETTER_STATUSES,
        ).order_by("-last_seen_at")[:25]
        return success_response(
            {
                "organization_id": str(organization.id),
                "projection": metadata,
                "latest_domain_event": _domain_event_metadata(latest_event)
                if latest_event
                else None,
                "cursors": [
                    {
                        "projection_name": cursor.projection_name,
                        "last_sequence": int(cursor.last_sequence),
                        "last_event_id": str(cursor.last_event_id or ""),
                        "status": cursor.status,
                        "last_error": cursor.last_error,
                        "updated_at": cursor.updated_at.isoformat(),
                    }
                    for cursor in cursors
                ],
                "active_dead_letters": [
                    _event_dead_letter_summary(item) for item in active_dead_letters
                ],
            }
        )


class OpsTransportEvidenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        allowed = _require_ops_permission(request, OPS_PROJECTION_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed

        transport = str(request.query_params.get("transport") or "").strip()
        if transport != "whiteboard_board_kafka":
            return error_response(
                "UNSUPPORTED_TRANSPORT",
                "Only whiteboard_board_kafka transport evidence is available.",
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        whiteboard_id = str(request.query_params.get("whiteboard_id") or "").strip()
        if whiteboard_id:
            try:
                UUID(whiteboard_id)
            except ValueError:
                return error_response(
                    "INVALID_WHITEBOARD_ID",
                    "whiteboard_id must be a UUID.",
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )
        company_id = str(request.query_params.get("company_id") or "").strip()
        if company_id:
            try:
                UUID(company_id)
            except ValueError:
                return error_response(
                    "INVALID_COMPANY_ID",
                    "company_id must be a UUID.",
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )

        return success_response(
            {
                "transport_evidence": whiteboard_board_kafka_transport_evidence(
                    organization=organization,
                    whiteboard_id=whiteboard_id,
                    company_id=company_id,
                )
            }
        )


class OpsEventSpoolView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        allowed = _require_ops_permission(request, OPS_PROJECTION_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed
        domain_events = DomainEvent.objects.filter(organization=organization)
        state_feed_events = OrganizationStateFeedEvent.objects.filter(organization=organization)
        return success_response(
            {
                "organization_id": str(organization.id),
                "domain_events": {
                    "count": domain_events.count(),
                    "latest_sequence": domain_events.order_by("-sequence")
                    .values_list("sequence", flat=True)
                    .first()
                    or 0,
                    "recent": [
                        _domain_event_metadata(event)
                        for event in domain_events.order_by("-sequence")[:25]
                    ],
                },
                "state_feed_events": {
                    "count": state_feed_events.count(),
                    "latest_state_version": state_feed_events.order_by("-state_version")
                    .values_list(
                        "state_version",
                        flat=True,
                    )
                    .first()
                    or 0,
                    "recent": [
                        _state_feed_event_metadata(event)
                        for event in state_feed_events.order_by("-state_version")[:25]
                    ],
                },
                "dead_letters": {
                    "active_count": EventDeadLetterRecord.objects.filter(
                        organization=organization,
                        status__in=ACTIVE_EVENT_DEAD_LETTER_STATUSES,
                    ).count(),
                    "recent": [
                        _event_dead_letter_summary(item)
                        for item in EventDeadLetterRecord.objects.filter(
                            organization=organization
                        ).order_by("-last_seen_at")[:25]
                    ],
                },
                "generated_at": timezone.now().isoformat(),
            }
        )


class OpsRuntimeIntentLagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        allowed = _require_ops_permission(request, OPS_PROJECTION_READ)
        if isinstance(allowed, Response):
            return allowed
        _, organization = allowed
        snapshot = get_runtime_transport_observability_snapshot()
        recent_dead_letters: list[dict[str, Any]] = []
        redis_error = snapshot.error
        try:
            redis_client = build_runtime_intent_redis_client()
            messages = cast(
                list[tuple[Any, dict[str, Any]]],
                redis_client.xrevrange(
                    RUNTIME_INTENT_DEAD_LETTER_STREAM, max="+", min="-", count=25
                ),
            )
            recent_dead_letters = [
                _dead_letter_stream_payload(message_id, fields)
                for message_id, fields in messages
                if _dead_letter_stream_visible_to_org(organization, fields)
            ]
        except Exception as exc:
            redis_error = str(exc)
        db_dead_letters = _runtime_queryset(organization)[:25]
        return success_response(
            {
                "organization_id": str(organization.id),
                "stream": RUNTIME_INTENT_STREAM,
                "dead_letter_stream": RUNTIME_INTENT_DEAD_LETTER_STREAM,
                "stream_length": snapshot.stream_length,
                "pending": snapshot.pending,
                "lag": snapshot.lag,
                "backlog": snapshot.backlog,
                "consumer_idle_ms": snapshot.consumer_idle_ms,
                "oldest_pending_idle_ms": snapshot.oldest_pending_idle_ms,
                "dead_letter_count": snapshot.dead_letter_count,
                "source": snapshot.source,
                "error": redis_error,
                "recent_dead_letters": recent_dead_letters,
                "recent_runtime_outcomes": [
                    _runtime_intent_summary(item) for item in db_dead_letters
                ],
                "generated_at": snapshot.generated_at,
            }
        )


def _replay_runtime_intent(
    *,
    user: User,
    organization: Organization,
    outcome: RuntimeIntentOutcome,
    reason: str,
    dead_letter_key: str,
    idempotency_key: str,
) -> Response:
    if outcome.outcome != "dead_lettered":
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="runtime_intent",
            target_id=str(outcome.intent_id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="Only dead-lettered runtime intents can be replayed.",
        )
    try:
        redis_client = build_runtime_intent_redis_client()
        replay_fields = _find_dead_letter_stream_fields(redis_client, outcome.intent_id)
        if replay_fields is None:
            return _replay_unavailable(
                user=user,
                organization=organization,
                target_type="runtime_intent",
                target_id=str(outcome.intent_id),
                reason=reason,
                idempotency_key=idempotency_key,
                message="Dead-letter payload is no longer available in Redis.",
            )
        intent = decode_runtime_intent_message({"intent": str(replay_fields.get("intent") or "")})
        if (
            outcome.run is not None
            and outcome.run.active_attempt_id
            and intent.attempt_id != outcome.run.active_attempt_id
        ):
            return _replay_unavailable(
                user=user,
                organization=organization,
                target_type="runtime_intent",
                target_id=str(outcome.intent_id),
                reason=reason,
                idempotency_key=idempotency_key,
                message="Cannot replay an intent for a stale attempt.",
                code="STALE_ATTEMPT",
            )
        replay_message_id = redis_client.xadd(
            RUNTIME_INTENT_STREAM,
            {"intent": str(replay_fields.get("intent") or "")},
        )
    except Exception as exc:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="runtime_intent",
            target_id=str(outcome.intent_id),
            reason=reason,
            idempotency_key=idempotency_key,
            message=str(exc),
            code="INTENT_REPLAY_FAILED",
        )
    record_operator_action(
        actor=user,
        organization=organization,
        action="ops.dead_letter.replay",
        target_type="runtime_intent",
        target_id=str(outcome.intent_id),
        reason=reason,
        status="replay_requested",
        idempotency_key=idempotency_key,
        metadata={
            "dead_letter_key": dead_letter_key,
            "replay_message_id": str(replay_message_id),
        },
    )
    return success_response(
        {
            "status": "replay_requested",
            "dead_letter": _runtime_intent_summary(outcome),
            "intent_id": str(outcome.intent_id),
            "replay_message_id": str(replay_message_id),
        }
    )


def _replay_task_dead_letter(
    *,
    user: User,
    organization: Organization,
    dead_letter: TaskDeadLetterRecord,
    reason: str,
    dead_letter_key: str,
    idempotency_key: str,
) -> Response:
    if not dead_letter.intent_id or "replay_intent" not in dead_letter.recovery_options:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="task",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="This task dead letter does not have a replayable runtime intent.",
            metadata={"available_actions": _actions_for_task_dead_letter(dead_letter)},
        )
    outcome = _runtime_queryset(organization).filter(intent_id=dead_letter.intent_id).first()
    if outcome is None:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="task",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="Linked runtime intent dead letter was not found.",
            metadata={"intent_id": str(dead_letter.intent_id)},
        )
    response = _replay_runtime_intent(
        user=user,
        organization=organization,
        outcome=outcome,
        reason=reason,
        dead_letter_key=dead_letter_key,
        idempotency_key=idempotency_key,
    )
    if response.status_code < 400:
        record_operator_action(
            actor=user,
            organization=organization,
            action="ops.dead_letter.replay",
            target_type="task",
            target_id=str(dead_letter.id),
            reason=reason,
            status="replay_requested",
            idempotency_key=idempotency_key,
            metadata={"dead_letter_key": dead_letter_key, "intent_id": str(dead_letter.intent_id)},
        )
    return response


def _replay_event_dead_letter(
    *,
    user: User,
    organization: Organization,
    dead_letter: EventDeadLetterRecord,
    reason: str,
    dead_letter_key: str,
    idempotency_key: str,
) -> Response:
    if dead_letter.source != "os_projection_worker" or not dead_letter.event_id:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="event",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="Only projection dead letters with a retained DomainEvent can be replayed.",
        )
    try:
        event_id = UUID(str(dead_letter.event_id))
    except ValueError:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="event",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="The recorded event id is not a replayable DomainEvent id.",
        )
    domain_event = DomainEvent.objects.filter(organization=organization, id=event_id).first()
    if domain_event is None:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="event",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="The DomainEvent for this projection dead letter is no longer available.",
        )
    projection_names = _replayable_projection_names(organization, domain_event)
    if not projection_names:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="event",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="No degraded projection cursor is available for replay.",
        )
    with transaction.atomic():
        ProcessedProjectionEvent.objects.filter(
            event=domain_event,
            projection_name__in=projection_names,
        ).delete()
        ProjectionCursor.objects.filter(
            organization=organization,
            projection_name__in=projection_names,
        ).update(
            last_sequence=max(int(domain_event.sequence) - 1, 0),
            status="rebuilding",
            last_error="",
        )
        EventDeadLetterRecord.objects.filter(id=dead_letter.id).update(
            status="replay_requested",
            replay_requested_at=timezone.now(),
            replay_requested_by=user,
            last_replay_action=reason,
        )
    result = process_pending_projection_events(
        organization_id=organization.id,
        batch_size=100,
        projection_names=projection_names,
    )
    if result.deadlettered > 0 or result.processed == 0:
        return _replay_unavailable(
            user=user,
            organization=organization,
            target_type="event",
            target_id=str(dead_letter.id),
            reason=reason,
            idempotency_key=idempotency_key,
            message="Projection replay did not complete successfully.",
            metadata={"processed": result.processed, "deadlettered": result.deadlettered},
            code="REPLAY_FAILED",
        )
    now = timezone.now()
    EventDeadLetterRecord.objects.filter(id=dead_letter.id).update(
        status="resolved",
        acknowledged_at=now,
        acknowledged_by=user,
        acknowledgement_reason=reason,
    )
    dead_letter.refresh_from_db()
    record_operator_action(
        actor=user,
        organization=organization,
        action="ops.dead_letter.replay",
        target_type="event",
        target_id=str(dead_letter.id),
        reason=reason,
        status="replayed",
        idempotency_key=idempotency_key,
        metadata={
            "dead_letter_key": dead_letter_key,
            "domain_event_id": str(domain_event.id),
            "projection_names": list(projection_names),
            "processed": result.processed,
        },
    )
    record_idempotency_observation(
        boundary="operator_dead_letter_replay",
        status="applied",
        idempotency_key=idempotency_key,
        resource_type="event_dead_letter",
        organization_id=organization.id,
    )
    return success_response(
        {
            "status": "replayed",
            "dead_letter": _event_dead_letter_summary(dead_letter),
            "projection_names": list(projection_names),
            "processed": result.processed,
        }
    )


def _replayable_projection_names(organization: Organization, event: DomainEvent) -> tuple[str, ...]:
    cursors = ProjectionCursor.objects.filter(
        organization=organization,
        last_event_id=event.id,
        status__in={"degraded", "rebuilding", "stale"},
    ).values_list("projection_name", flat=True)
    names = tuple(str(name) for name in cursors if str(name) in PROJECTION_NAMES)
    if names:
        return names
    if EventDeadLetterRecord.objects.filter(
        organization=organization,
        source="os_projection_worker",
        event_id=str(event.id),
        status__in=ACTIVE_EVENT_DEAD_LETTER_STATUSES,
    ).exists():
        return tuple(PROJECTION_NAMES)
    return ()


def _resolve_dead_letter(
    *,
    user: User,
    organization: Organization,
    kind: str,
    item: TaskDeadLetterRecord | EventDeadLetterRecord | RuntimeIntentOutcome,
    reason: str,
    dead_letter_key: str,
    idempotency_key: str,
) -> Response:
    resolution = resolve_dead_letter_record(
        actor=user,
        organization=organization,
        kind=kind,
        item=item,
        reason=reason,
        dead_letter_key=dead_letter_key,
        idempotency_key=idempotency_key,
    )
    if resolution.kind == "task":
        payload = _task_dead_letter_summary(cast(TaskDeadLetterRecord, resolution.item))
    elif resolution.kind == "event":
        payload = _event_dead_letter_summary(cast(EventDeadLetterRecord, resolution.item))
    else:
        payload = _runtime_intent_summary(cast(RuntimeIntentOutcome, resolution.item))
    return success_response({"status": "resolved", "dead_letter": payload})


def _replay_unavailable(
    *,
    user: User,
    organization: Organization,
    target_type: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    code: str = "REPLAY_UNAVAILABLE",
) -> Response:
    record_operator_action(
        actor=user,
        organization=organization,
        action="ops.dead_letter.replay",
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        status="rejected",
        idempotency_key=idempotency_key,
        metadata=metadata or {"reason": message},
    )
    record_idempotency_observation(
        boundary="operator_dead_letter_replay",
        status="rejected",
        idempotency_key=idempotency_key,
        resource_type=f"{target_type}_dead_letter",
        organization_id=organization.id,
    )
    return error_response(code, message, status=drf_status.HTTP_409_CONFLICT)


def _find_dead_letter_stream_fields(redis_client: Any, intent_id: UUID) -> dict[str, Any] | None:
    messages = cast(
        list[tuple[Any, dict[str, Any]]],
        redis_client.xrevrange(RUNTIME_INTENT_DEAD_LETTER_STREAM, max="+", min="-", count=500),
    )
    for _, fields in messages:
        if str(fields.get("intent_id") or "") == str(intent_id):
            return fields
        raw_intent = str(fields.get("intent") or "")
        try:
            payload = json.loads(raw_intent)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("intent_id") or "") == str(intent_id):
            return fields
    return None


def _dead_letter_stream_payload(message_id: Any, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": str(message_id),
        "intent_id": str(fields.get("intent_id") or ""),
        "intent_type": str(fields.get("intent_type") or ""),
        "run_id": str(fields.get("run_id") or ""),
        "attempt_id": str(fields.get("attempt_id") or ""),
        "reason": str(fields.get("reason") or ""),
        "error_class": str(fields.get("error_class") or ""),
        "dead_lettered_at": str(fields.get("dead_lettered_at") or fields.get("timestamp") or ""),
    }


def _dead_letter_stream_visible_to_org(organization: Organization, fields: dict[str, Any]) -> bool:
    run_id = str(fields.get("run_id") or "").strip()
    if not run_id:
        return False
    try:
        UUID(run_id)
    except ValueError:
        return False
    return Run.objects.filter(id=run_id, organization=organization).exists()


def _domain_event_metadata(event: DomainEvent) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    return {
        "id": str(event.id),
        "organization_id": str(event.organization_id),
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "event_type": event.event_type,
        "event_version": event.event_version,
        "sequence": int(event.sequence),
        "idempotency_key": event.idempotency_key,
        "payload_keys": sorted(str(key) for key in payload.keys()),
        "occurred_at": event.occurred_at.isoformat(),
        "created_at": event.created_at.isoformat(),
    }


def _state_feed_event_metadata(event: OrganizationStateFeedEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "event_id": event.event_id,
        "organization_id": str(event.organization_id),
        "state_version": int(event.state_version),
        "type": event.type,
        "resource": {
            "type": event.resource_type,
            "id": event.resource_id,
        },
        "requires_refetch": event.requires_refetch,
        "occurred_at": event.occurred_at.isoformat(),
        "created_at": event.created_at.isoformat(),
    }
