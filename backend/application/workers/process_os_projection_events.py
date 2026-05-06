from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from django.db import OperationalError, transaction
from django.db.models import F, Min, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from application.projections.dispatcher import (
    PROJECTION_NAMES,
    apply_projection_event,
    projection_names_for_event,
)
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectionWorkerResult:
    processed: int = 0
    skipped: int = 0
    noop: int = 0
    deadlettered: int = 0
    organizations: int = 0
    events_selected: int = 0
    duration_seconds: float = 0.0
    projection_durations: dict[str, float] | None = None


_DEADLOCK_RETRY_ATTEMPTS = 3


def process_pending_projection_events(
    *,
    organization_id: UUID | str | None = None,
    batch_size: int = 100,
    projection_names: Iterable[str] = PROJECTION_NAMES,
) -> ProjectionWorkerResult:
    started_at = time.perf_counter()
    names = tuple(projection_names)
    processed = 0
    skipped = 0
    noop = 0
    deadlettered = 0
    events_selected = 0
    projection_durations = dict.fromkeys(names, 0.0)
    projection_counts = dict.fromkeys(names, 0)
    organizations = _organizations_with_pending_events(
        organization_id=organization_id,
        projection_names=names,
    )
    remaining_batch = max(int(batch_size or 1), 1)
    max_lag_seconds = 0.0
    projection_recovery_cache: dict[UUID, bool] = {}
    run_cache: dict[str, Run | None] = {}
    for organization in organizations:
        if remaining_batch <= 0:
            break
        events = _pending_events_for_organization(
            organization=organization,
            projection_names=names,
            batch_size=remaining_batch,
        )
        remaining_batch -= len(events)
        events_selected += len(events)
        if events:
            _ensure_projection_cursors(organization=organization, projection_names=names)
        noop_cursor_targets: dict[str, DomainEvent] = {}
        for event in events:
            event_processed = False
            event_deadlettered = False
            relevant_projection_names = tuple(
                name for name in projection_names_for_event(event) if name in names
            )
            noop_projection_names = tuple(
                name for name in names if name not in relevant_projection_names
            )
            notification_required = bool(_projection_notifications_for(event))
            for projection_name in relevant_projection_names:
                projection_started_at = time.perf_counter()
                outcome = _process_event_for_projection(
                    event_id=event.id,
                    projection_name=projection_name,
                )
                projection_durations[projection_name] += time.perf_counter() - projection_started_at
                projection_counts[projection_name] += 1
                if outcome == "processed":
                    processed += 1
                    event_processed = True
                    max_lag_seconds = max(
                        max_lag_seconds,
                        max(0.0, (timezone.now() - event.occurred_at).total_seconds()),
                    )
                elif outcome == "deadlettered":
                    deadlettered += 1
                    event_processed = True
                    event_deadlettered = True
                else:
                    skipped += 1
            if noop_projection_names:
                noop += len(noop_projection_names)
                for projection_name in noop_projection_names:
                    noop_cursor_targets[projection_name] = event
            if event_processed:
                _record_projection_update(event, run_cache=run_cache)
            if (event_processed or notification_required) and not event_deadlettered:
                _record_organization_projection_notifications(
                    event,
                    recovery_cache=projection_recovery_cache,
                )
            if event_deadlettered:
                break
        if noop_cursor_targets:
            _advance_noop_cursors(
                organization=organization,
                cursor_targets=noop_cursor_targets,
            )
    duration_seconds = time.perf_counter() - started_at
    result = ProjectionWorkerResult(
        processed=processed,
        skipped=skipped,
        noop=noop,
        deadlettered=deadlettered,
        organizations=len(organizations),
        events_selected=events_selected,
        duration_seconds=duration_seconds,
        projection_durations=projection_durations,
    )
    if processed or skipped or noop or deadlettered:
        logger.info(
            "os_projection_worker_pass_completed",
            extra={
                "organizations": len(organizations),
                "events_selected": events_selected,
                "processed": processed,
                "skipped": skipped,
                "noop": noop,
                "deadlettered": deadlettered,
                "duration_seconds": round(duration_seconds, 6),
                "projection_durations": {
                    name: round(value, 6) for name, value in projection_durations.items()
                },
                "projection_counts": projection_counts,
            },
        )
        _record_pass_metrics(
            duration_seconds=duration_seconds,
            events_selected=events_selected,
            processed=processed,
            skipped=skipped,
            noop=noop,
            deadlettered=deadlettered,
            projection_durations=projection_durations,
            max_lag_seconds=max_lag_seconds,
        )
    return result


def _process_event_for_projection(*, event_id: UUID, projection_name: str) -> str:
    for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
        try:
            return _process_event_for_projection_once(
                event_id=event_id,
                projection_name=projection_name,
            )
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("unreachable projection worker retry state")


def _process_event_for_projection_once(*, event_id: UUID, projection_name: str) -> str:
    with transaction.atomic():
        event = (
            DomainEvent.objects.select_for_update(of=("self",))
            .select_related("organization")
            .get(id=event_id)
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
            _record_organization_projection_deadletter_notification(
                event,
                projection_name=projection_name,
            )
            return "deadlettered"

        _advance_cursor(cursor, event, status="fresh", last_error="")
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
    if any(name not in cursor_by_name for name in projection_names):
        min_sequence = 0
    else:
        min_sequence = min((cursor_by_name.get(name, 0) for name in projection_names), default=0)
    return list(
        DomainEvent.objects.filter(organization=organization, sequence__gt=min_sequence)
        .exclude(event_type__startswith="run_event.")
        .order_by("sequence")
        .select_related("organization")[: max(int(batch_size or 1), 1)]
    )


def _ensure_projection_cursors(
    *,
    organization: Organization,
    projection_names: tuple[str, ...],
) -> None:
    existing_names = set(
        ProjectionCursor.objects.filter(
            organization=organization,
            projection_name__in=projection_names,
        ).values_list("projection_name", flat=True)
    )
    missing = [
        ProjectionCursor(
            organization=organization,
            projection_name=name,
            last_sequence=0,
            status="fresh",
        )
        for name in projection_names
        if name not in existing_names
    ]
    if missing:
        ProjectionCursor.objects.bulk_create(missing, ignore_conflicts=True)


def _advance_noop_cursors(
    *,
    organization: Organization,
    cursor_targets: dict[str, DomainEvent],
) -> int:
    if not cursor_targets:
        return 0
    projections_by_event: dict[tuple[UUID, int], list[str]] = {}
    for projection_name, event in cursor_targets.items():
        projections_by_event.setdefault((event.id, int(event.sequence)), []).append(projection_name)

    updated = 0
    now = timezone.now()
    for (event_id, sequence), projection_names in projections_by_event.items():
        updated += ProjectionCursor.objects.filter(
            organization=organization,
            projection_name__in=projection_names,
            last_sequence__lt=sequence,
        ).update(
            last_sequence=sequence,
            last_event_id=event_id,
            updated_at=now,
        )
    return updated


def _organizations_with_pending_events(
    *,
    organization_id: UUID | str | None,
    projection_names: tuple[str, ...],
) -> list[Organization]:
    if not projection_names:
        return []

    cursor_min_for_event_org = (
        ProjectionCursor.objects.filter(
            organization_id=OuterRef("organization_id"),
            projection_name__in=projection_names,
        )
        .values("organization_id")
        .annotate(min_sequence=Min("last_sequence"))
        .values("min_sequence")[:1]
    )
    pending_org_ids = (
        DomainEvent.objects.filter(organization_id=OuterRef("pk"))
        .exclude(event_type__startswith="run_event.")
        .annotate(cursor_min_sequence=Coalesce(Subquery(cursor_min_for_event_org), Value(0)))
        .filter(sequence__gt=F("cursor_min_sequence"))
        .values("organization_id")
        .distinct()
        .order_by("id")
    )
    queryset = Organization.objects.filter(id__in=Subquery(pending_org_ids)).order_by("id")
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


def _record_projection_update(event: DomainEvent, *, run_cache: dict[str, Run | None]) -> None:
    run = _run_for_event(event, run_cache=run_cache)
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


def _record_organization_projection_deadletter_notification(
    event: DomainEvent,
    *,
    projection_name: str,
) -> None:
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


def _record_organization_projection_notifications(
    event: DomainEvent,
    *,
    recovery_cache: dict[UUID, bool],
) -> None:
    for notification in _projection_notifications_for(event):
        _publish_organization_feed_event(
            event,
            projection_name="domain_event",
            event_type=notification["event_type"],
            resource_type=notification["resource_type"],
            resource_id=notification["resource_id"],
            event_id=notification["event_id"],
            payload=notification["payload"],
        )
    _publish_projection_recovered_if_needed(
        event,
        projection_name="domain_event",
        recovery_cache=recovery_cache,
    )


def _projection_notifications_for(event: DomainEvent) -> list[dict[str, object]]:
    event_type = event.event_type
    payload = event.payload if isinstance(event.payload, dict) else {}
    resource_type = "overview"
    resource_id = str(event.organization_id)
    public_type = "overview.updated"

    if event_type.startswith("run_event."):
        return []
    if event_type in {"run.created", "run.updated"}:
        public_type = "overview.updated"
        resource_type = "overview"
        resource_id = str(event.organization_id)
    elif event_type == "node_run.created":
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
    else:
        return []

    return [
        {
            "event_type": public_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "event_id": f"os-projection:{event.id}:{public_type}",
            "payload": {},
        }
    ]


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
    recovery_cache: dict[UUID, bool],
) -> None:
    cached_stale = recovery_cache.get(event.organization_id)
    if cached_stale is False:
        return
    latest = _latest_projection_state_event(event.organization)
    if latest is None or latest.type != "projection.stale":
        recovery_cache[event.organization_id] = False
        return
    if not _organization_projection_is_fresh(event.organization):
        recovery_cache[event.organization_id] = True
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
    recovery_cache[event.organization_id] = False


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
        async_broadcast=True,
    )


def _run_for_event(
    event: DomainEvent,
    *,
    run_cache: dict[str, Run | None] | None = None,
) -> Run | None:
    run_id = str(event.payload.get("run_id") or "").strip()
    if not run_id:
        return None
    if run_cache is not None and run_id in run_cache:
        return run_cache[run_id]
    run = Run.objects.filter(id=run_id).first()
    if run_cache is not None:
        run_cache[run_id] = run
    return run


def _record_pass_metrics(
    *,
    duration_seconds: float,
    events_selected: int,
    processed: int,
    skipped: int,
    noop: int,
    deadlettered: int,
    projection_durations: dict[str, float],
    max_lag_seconds: float,
) -> None:
    dimensions = {
        "events_selected": str(events_selected),
        "processed": str(processed),
        "skipped": str(skipped),
        "noop": str(noop),
        "deadlettered": str(deadlettered),
    }
    record_service_metric_sample(
        metric_name="os_projection_pass_duration_seconds",
        source="process_os_projection_events",
        value=duration_seconds,
        unit="seconds",
        dimensions=dimensions,
    )
    record_service_metric_sample(
        metric_name="os_projection_events_selected_total",
        source="process_os_projection_events",
        value=events_selected,
        unit="count",
        dimensions=dimensions,
    )
    record_service_metric_sample(
        metric_name="os_projection_events_processed_total",
        source="process_os_projection_events",
        value=processed,
        unit="count",
        dimensions=dimensions,
    )
    record_service_metric_sample(
        metric_name="os_projection_events_deadlettered_total",
        source="process_os_projection_events",
        value=deadlettered,
        unit="count",
        dimensions=dimensions,
    )
    record_service_metric_sample(
        metric_name="os_projection_lag_seconds",
        source="process_os_projection_events",
        value=max_lag_seconds,
        unit="seconds",
        dimensions=dimensions,
    )
    for projection_name, projection_duration in projection_durations.items():
        record_service_metric_sample(
            metric_name="os_projection_projection_duration_seconds",
            source="process_os_projection_events",
            value=projection_duration,
            unit="seconds",
            dimensions={
                **dimensions,
                "projection_name": projection_name,
            },
        )


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()
