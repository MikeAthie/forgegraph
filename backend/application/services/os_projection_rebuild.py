from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from application.projections.dispatcher import PROJECTION_NAMES
from application.services.domain_events import backfill_domain_events_for_organization
from application.services.metrics import record_service_metric_sample
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    AgentRegistryEntry,
    CostAggregate,
    CostLedgerEntry,
    DecisionRecord,
    DomainEvent,
    Organization,
    ProcessedProjectionEvent,
    ProjectionCursor,
    TaskRecord,
)


@dataclass(frozen=True, slots=True)
class ProjectionRebuildResult:
    organization_id: str
    backfilled_events: int
    replayed_events: int
    read_model_counts: dict[str, int]
    duration_seconds: float


def rebuild_os_projections_for_organization(
    organization: Organization,
    *,
    batch_size: int = 100,
) -> ProjectionRebuildResult:
    started_at = timezone.now()
    backfilled = backfill_domain_events_for_organization(organization)

    with transaction.atomic():
        _mark_rebuilding(organization)
        _truncate_read_models(organization)
        ProcessedProjectionEvent.objects.filter(event__organization=organization).delete()
        ProjectionCursor.objects.filter(organization=organization).update(
            last_sequence=0,
            last_event_id=None,
            status="rebuilding",
            last_error="",
        )

    replayed = _replay_all_events(organization=organization, batch_size=batch_size)
    counts = _read_model_counts(organization)
    duration_seconds = max(0.0, (timezone.now() - started_at).total_seconds())
    if DomainEvent.objects.filter(organization=organization).count() == 0:
        _mark_fresh_empty(organization)

    record_service_metric_sample(
        metric_name="os_projection_rebuild_duration_seconds",
        source="rebuild_os_projections",
        value=duration_seconds,
        unit="seconds",
        organization_id=organization.id,
        dimensions={
            "organization_id": str(organization.id),
            "backfilled_events": backfilled,
            "replayed_events": replayed,
        },
    )
    return ProjectionRebuildResult(
        organization_id=str(organization.id),
        backfilled_events=backfilled,
        replayed_events=replayed,
        read_model_counts=counts,
        duration_seconds=duration_seconds,
    )


def _mark_rebuilding(organization: Organization) -> None:
    for projection_name in PROJECTION_NAMES:
        ProjectionCursor.objects.update_or_create(
            organization=organization,
            projection_name=projection_name,
            defaults={
                "last_sequence": 0,
                "last_event_id": None,
                "status": "rebuilding",
                "last_error": "",
            },
        )


def _truncate_read_models(organization: Organization) -> None:
    CostAggregate.objects.filter(organization=organization).delete()
    CostLedgerEntry.objects.filter(organization=organization).delete()
    DecisionRecord.objects.filter(organization=organization).delete()
    TaskRecord.objects.filter(organization=organization).delete()
    AgentRegistryEntry.objects.filter(organization=organization).delete()


def _replay_all_events(*, organization: Organization, batch_size: int) -> int:
    total_processed = 0
    event_count = DomainEvent.objects.filter(organization=organization).count()
    max_passes = max(event_count + 2, 2)
    for _ in range(max_passes):
        result = process_pending_projection_events(
            organization_id=organization.id,
            batch_size=batch_size,
        )
        total_processed += result.processed
        if result.processed == 0 and result.deadlettered == 0:
            break
    return total_processed


def _mark_fresh_empty(organization: Organization) -> None:
    ProjectionCursor.objects.filter(organization=organization).update(
        last_sequence=0,
        last_event_id=None,
        status="fresh",
        last_error="",
    )


def _read_model_counts(organization: Organization) -> dict[str, int]:
    return {
        "agents": AgentRegistryEntry.objects.filter(organization=organization).count(),
        "tasks": TaskRecord.objects.filter(organization=organization).count(),
        "decisions": DecisionRecord.objects.filter(organization=organization).count(),
        "ledger": CostLedgerEntry.objects.filter(organization=organization).count(),
        "cost_aggregates": CostAggregate.objects.filter(organization=organization).count(),
    }
