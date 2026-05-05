from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from application.projections.dispatcher import PROJECTION_NAMES, apply_projection_event
from application.services.event_dead_letters import record_event_dead_letter
from application.services.idempotency import record_idempotency_observation
from application.services.metrics import record_service_metric_sample
from application.services.organization_state_feed import publish_organization_state_feed_event
from application.services.state_feed import record_state_feed_event
from infrastructure.orm.models import (
    DomainEvent,
    EventDeadLetterRecord,
    Organization,
    OrganizationStateFeedEvent,
    ProcessedProjectionEvent,
    ProjectionCursor,
    Run,
)


@dataclass(frozen=True, slots=True)
class ProjectionWorkerResult:
    processed: int = 0
    skipped: int = 0
    deadlettered: int = 0


def process_pending_projection_events(
    *,
    organization_id: UUID | str | None = None,
    batch_size: int = 100,
    projection_names: Iterable[str] = PROJECTION_NAMES,
) -> ProjectionWorkerResult:
    names = tuple(projection_names)
    processed = 0
    skipped = 0
    deadlettered = 0
    organizations = _organizations_with_events(organization_id=organization_id)
    for organization in organizations:
        events = _pending_events_for_organization(
            organization=organization,
            projection_names=names,
            batch_size=batch_size,
        )
        for event in events:
            event_processed = False
            event_deadlettered = False
            for projection_name in names:
                outcome = _process_event_for_projection(
                    event_id=event.id,
                    projection_name=projection_name,
                )
                if outcome == "processed":
                    processed += 1
                    event_processed = True
                elif outcome == "deadlettered":
                    deadlettered += 1
                    event_processed = True
                    event_deadlettered = True
                else:
                    skipped += 1
            if event_processed:
                _record_projection_update(event)
            if event_deadlettered:
                break
    return ProjectionWorkerResult(processed=processed, skipped=skipped, deadlettered=deadlettered)


def _process_event_for_projection(*, event_id: UUID, projection_name: str) -> str:
    with transaction.atomic():
        event = (
            DomainEvent.objects.select_for_update().select_related("organization").get(id=event_id)
        )
        cursor, _ = ProjectionCursor.objects.select_for_update().get_or_create(
            projection_name=projection_name,
            organization=event.organization,
            defaults={"last_sequence": 0, "status": "fresh"},
        )
        if event.sequence <= cursor.last_sequence:
            return "skipped"

        _, created = ProcessedProjectionEvent.objects.get_or_create(
            projection_name=projection_name,
            event=event,
        )
        if not created:
            record_idempotency_observation(
                boundary="projection_event",
                status="already_applied",
                idempotency_key=f"{projection_name}:{event.id}",
                resource_type="projection",
                organization_id=event.organization_id,
            )
            _advance_cursor(cursor, event, status="fresh", last_error="")
            return "skipped"

        try:
            apply_projection_event(projection_name, event)
        except Exception as exc:  # pragma: no cover - exercised by integration tests.
            record_event_dead_letter(
                source="os_projection_worker",
                reason=str(exc),
                payload=event.payload if isinstance(event.payload, dict) else {},
                organization=event.organization,
                run=_run_for_event(event),
                event_id=str(event.id),
                idempotency_key=event.idempotency_key,
                event_type=event.event_type,
                error_class=exc.__class__.__name__,
            )
            _advance_cursor(
                cursor,
                event,
                status="degraded",
                last_error=f"{exc.__class__.__name__}: {exc}"[:1000],
            )
            _record_metric(
                "os_projection_events_deadlettered_total",
                event=event,
                projection_name=projection_name,
                value=1,
                unit="count",
            )
            _record_organization_projection_notifications(
                event,
                projection_name=projection_name,
                deadlettered=True,
            )
            return "deadlettered"

        _advance_cursor(cursor, event, status="fresh", last_error="")
        _record_metric(
            "os_projection_events_processed_total",
            event=event,
            projection_name=projection_name,
            value=1,
            unit="count",
        )
        record_idempotency_observation(
            boundary="projection_event",
            status="applied",
            idempotency_key=f"{projection_name}:{event.id}",
            resource_type="projection",
            organization_id=event.organization_id,
        )
        lag_seconds = max(0.0, (timezone.now() - event.occurred_at).total_seconds())
        _record_metric(
            "os_projection_lag_seconds",
            event=event,
            projection_name=projection_name,
            value=lag_seconds,
            unit="seconds",
        )
        _record_organization_projection_notifications(
            event,
            projection_name=projection_name,
            deadlettered=False,
        )
        return "processed"


def _pending_events_for_organization(
    *,
    organization: Organization,
    projection_names: tuple[str, ...],
    batch_size: int,
) -> list[DomainEvent]:
    cursors = ProjectionCursor.objects.filter(
        organization=organization,
        projection_name__in=projection_names,
    )
    cursor_by_name = {cursor.projection_name: int(cursor.last_sequence) for cursor in cursors}
    min_sequence = min((cursor_by_name.get(name, 0) for name in projection_names), default=0)
    return list(
        DomainEvent.objects.filter(organization=organization, sequence__gt=min_sequence)
        .order_by("sequence")
        .select_related("organization")[: max(int(batch_size or 1), 1)]
    )


def _organizations_with_events(*, organization_id: UUID | str | None) -> list[Organization]:
    queryset = Organization.objects.filter(domain_events__isnull=False).distinct().order_by("id")
    if organization_id:
        queryset = queryset.filter(id=UUID(str(organization_id)))
    return list(queryset)


def _advance_cursor(
    cursor: ProjectionCursor,
    event: DomainEvent,
    *,
    status: str,
    last_error: str,
) -> None:
    cursor.last_sequence = int(event.sequence)
    cursor.last_event_id = event.id
    cursor.status = status
    cursor.last_error = last_error
    cursor.save(
        update_fields=[
            "last_sequence",
            "last_event_id",
            "status",
            "last_error",
            "updated_at",
        ]
    )


def _record_projection_update(event: DomainEvent) -> None:
    run = _run_for_event(event)
    if run is None:
        return
    try:
        record_state_feed_event(
            run=run,
            message={
                "type": "projection.updated",
                "timestamp": timezone.now().isoformat(),
                "trace_id": run.trace_id,
                "run_id": str(run.id),
                "event_id": f"os-projection:{event.id}",
                "payload": {
                    "organization_id": str(event.organization_id),
                    "state_version": event.sequence,
                    "event_type": event.event_type,
                },
            },
            requires_refetch=True,
        )
    except Exception:
        return


def _record_organization_projection_notifications(
    event: DomainEvent,
    *,
    projection_name: str,
    deadlettered: bool,
) -> None:
    if deadlettered:
        _publish_organization_feed_event(
            event,
            projection_name=projection_name,
            event_type="dead_letter.created",
            resource_type="dead_letter",
            resource_id=str(event.id),
            event_id=f"os-projection:{event.id}:dead-letter:{projection_name}",
            payload={"error": "projection_event_deadlettered"},
        )
        _publish_projection_stale(event, projection_name=projection_name)
        return

    for notification in _projection_notifications_for(event):
        _publish_organization_feed_event(
            event,
            projection_name=projection_name,
            event_type=notification["event_type"],
            resource_type=notification["resource_type"],
            resource_id=notification["resource_id"],
            event_id=notification["event_id"],
            payload=notification["payload"],
        )
    _publish_projection_recovered_if_needed(event, projection_name=projection_name)


def _projection_notifications_for(event: DomainEvent) -> list[dict[str, object]]:
    event_type = event.event_type
    payload = event.payload if isinstance(event.payload, dict) else {}
    resource_type = "overview"
    resource_id = str(event.organization_id)
    public_type = "overview.updated"

    if event_type == "node_run.created":
        public_type = "task.created"
        resource_type = "task"
        resource_id = str(payload.get("node_run_id") or payload.get("run_id") or event.aggregate_id)
    elif event_type in {"node_run.updated", "task.lifecycle_transitioned"}:
        public_type = "task.updated"
        resource_type = "task"
        resource_id = str(
            payload.get("task_lifecycle_id")
            or payload.get("node_run_id")
            or payload.get("run_id")
            or event.aggregate_id
        )
    elif event_type == "decision.approval_created":
        public_type = "decision.created"
        resource_type = "decision"
        resource_id = str(payload.get("approval_id") or event.aggregate_id)
    elif event_type in {"decision.approval_updated", "decision.audit_review_recorded"}:
        public_type = "decision.updated"
        resource_type = "decision"
        resource_id = str(payload.get("approval_id") or event.aggregate_id)
    elif event_type.startswith("accounting."):
        public_type = "accounting.updated"
        resource_type = "accounting"
        resource_id = str(event.aggregate_id)
    elif event_type.startswith("memory."):
        public_type = "memory.created"
        resource_type = "memory"
        resource_id = str(payload.get("observation_id") or event.aggregate_id)
    elif event_type == "agent.registry_source_updated":
        public_type = "agent.updated"
        resource_type = "agent"
        resource_id = str(payload.get("graph_version_id") or event.aggregate_id)

    notifications: list[dict[str, object]] = [
        {
            "event_type": public_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "event_id": f"os-projection:{event.id}:{public_type}",
            "payload": {},
        }
    ]
    if public_type != "overview.updated":
        notifications.append(
            {
                "event_type": "overview.updated",
                "resource_type": "overview",
                "resource_id": str(event.organization_id),
                "event_id": f"os-projection:{event.id}:overview.updated",
                "payload": {"source_event_type": public_type},
            }
        )
    return notifications


def _publish_projection_stale(event: DomainEvent, *, projection_name: str) -> None:
    latest = _latest_projection_state_event(event.organization)
    if latest is not None and latest.type == "projection.stale":
        return
    _publish_organization_feed_event(
        event,
        projection_name=projection_name,
        event_type="projection.stale",
        resource_type="projection",
        resource_id=str(event.organization_id),
        event_id=f"os-projection:{event.id}:projection.stale",
        payload={"reason": "projection_event_deadlettered"},
    )


def _publish_projection_recovered_if_needed(
    event: DomainEvent,
    *,
    projection_name: str,
) -> None:
    latest = _latest_projection_state_event(event.organization)
    if latest is None or latest.type != "projection.stale":
        return
    if not _organization_projection_is_fresh(event.organization):
        return
    _publish_organization_feed_event(
        event,
        projection_name=projection_name,
        event_type="projection.recovered",
        resource_type="projection",
        resource_id=str(event.organization_id),
        event_id=f"os-projection:{event.id}:projection.recovered",
        payload={"reason": "projection_cursor_recovered"},
    )


def _latest_projection_state_event(
    organization: Organization,
) -> OrganizationStateFeedEvent | None:
    return (
        OrganizationStateFeedEvent.objects.filter(
            organization=organization,
            type__in={"projection.stale", "projection.recovered"},
        )
        .order_by("-state_version")
        .first()
    )


def _organization_projection_is_fresh(organization: Organization) -> bool:
    active_dead_letters = EventDeadLetterRecord.objects.filter(
        organization=organization,
        source="os_projection_worker",
        status__in={"active", "replay_requested"},
    ).exists()
    if active_dead_letters:
        return False

    latest_event_sequence = (
        DomainEvent.objects.filter(organization=organization)
        .order_by("-sequence")
        .values_list(
            "sequence",
            flat=True,
        )
        .first()
        or 0
    )
    cursors = list(ProjectionCursor.objects.filter(organization=organization))
    if not cursors:
        return int(latest_event_sequence) == 0
    if any(cursor.status != "fresh" for cursor in cursors):
        return False
    return min(int(cursor.last_sequence) for cursor in cursors) >= int(latest_event_sequence)


def _publish_organization_feed_event(
    event: DomainEvent,
    *,
    projection_name: str,
    event_type: object,
    resource_type: object,
    resource_id: object,
    event_id: object,
    payload: object,
) -> None:
    payload_value = dict(payload) if isinstance(payload, dict) else {}
    publish_organization_state_feed_event(
        organization=event.organization,
        event_type=str(event_type),
        resource_type=str(resource_type),
        resource_id=str(resource_id),
        event_id=str(event_id),
        requires_refetch=True,
        occurred_at=timezone.now(),
        payload={
            **payload_value,
            "domain_event_id": str(event.id),
            "domain_event_type": event.event_type,
            "projection_name": projection_name,
            "projection_sequence": int(event.sequence),
        },
    )


def _run_for_event(event: DomainEvent) -> Run | None:
    run_id = str(event.payload.get("run_id") or "").strip()
    if not run_id:
        return None
    return Run.objects.filter(id=run_id).first()


def _record_metric(
    metric_name: str,
    *,
    event: DomainEvent,
    projection_name: str,
    value: float,
    unit: str,
) -> None:
    record_service_metric_sample(
        metric_name=metric_name,
        source="process_os_projection_events",
        value=value,
        unit=unit,
        organization_id=event.organization_id,
        dimensions={
            "organization_id": str(event.organization_id),
            "projection_name": projection_name,
            "event_type": event.event_type,
        },
    )
