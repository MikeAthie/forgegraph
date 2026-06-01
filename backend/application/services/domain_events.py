from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone

from application.services.domain_event_outbox import (
    enqueue_domain_event_outbox,
    sanitize_outbox_payload,
)
from infrastructure.orm.models import (
    ApprovalTask,
    AuditLog,
    DomainEvent,
    Graph,
    GraphVersion,
    LLMUsage,
    MemoryObservation,
    MemoryUsage,
    NodeRun,
    Organization,
    OrganizationDomainEventSequence,
    Run,
    RunEvent,
    TaskLifecycleEvent,
)


@dataclass(frozen=True, slots=True)
class DomainEventResult:
    event: DomainEvent
    created: bool


_DEADLOCK_RETRY_ATTEMPTS = 3
_DOMAIN_EVENT_SIGNALS_SUPPRESSED: ContextVar[bool] = ContextVar(
    "domain_event_signals_suppressed",
    default=False,
)


@contextmanager
def suppress_domain_event_signals() -> Any:
    token = _DOMAIN_EVENT_SIGNALS_SUPPRESSED.set(True)
    try:
        yield
    finally:
        _DOMAIN_EVENT_SIGNALS_SUPPRESSED.reset(token)


def domain_event_signals_suppressed() -> bool:
    return bool(_DOMAIN_EVENT_SIGNALS_SUPPRESSED.get())


def record_domain_event(
    *,
    organization: Organization,
    aggregate_type: str,
    aggregate_id: UUID | str,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    tenant_id: UUID | str | None = None,
    event_version: int = 1,
    occurred_at: Any = None,
    outbox_topic: str | None = None,
    outbox_schema_version: str = "domain_event_v1",
    outbox_payload: dict[str, Any] | None = None,
    outbox_visibility: str = "",
    outbox_company: Graph | None = None,
) -> DomainEventResult:
    """Record a backend-authored projection event in the caller's transaction."""

    for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
        try:
            return _record_domain_event_once(
                organization=organization,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                idempotency_key=idempotency_key,
                payload=payload,
                tenant_id=tenant_id,
                event_version=event_version,
                occurred_at=occurred_at,
                outbox_topic=outbox_topic,
                outbox_schema_version=outbox_schema_version,
                outbox_payload=outbox_payload,
                outbox_visibility=outbox_visibility,
                outbox_company=outbox_company,
            )
        except OperationalError as exc:
            if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("unreachable domain event retry state")


def _record_domain_event_once(
    *,
    organization: Organization,
    aggregate_type: str,
    aggregate_id: UUID | str,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    tenant_id: UUID | str | None = None,
    event_version: int = 1,
    occurred_at: Any = None,
    outbox_topic: str | None = None,
    outbox_schema_version: str = "domain_event_v1",
    outbox_payload: dict[str, Any] | None = None,
    outbox_visibility: str = "",
    outbox_company: Graph | None = None,
) -> DomainEventResult:
    key = _compact_key(idempotency_key)
    if not key:
        raise ValueError("Domain events require an idempotency key.")

    aggregate_uuid = UUID(str(aggregate_id))
    organization_id = organization.id
    existing = DomainEvent.objects.filter(idempotency_key=key).first()
    if existing is not None:
        _maybe_enqueue_outbox(
            existing,
            topic=outbox_topic,
            schema_version=outbox_schema_version,
            payload_json=outbox_payload,
            visibility=outbox_visibility,
            company=outbox_company,
        )
        return DomainEventResult(event=existing, created=False)

    with transaction.atomic():
        existing = DomainEvent.objects.filter(idempotency_key=key).first()
        if existing is not None:
            _maybe_enqueue_outbox(
                existing,
                topic=outbox_topic,
                schema_version=outbox_schema_version,
                payload_json=outbox_payload,
                visibility=outbox_visibility,
                company=outbox_company,
            )
            return DomainEventResult(event=existing, created=False)

        sequence = _allocate_sequence(organization_id)
        try:
            event = DomainEvent.objects.create(
                tenant_id=UUID(str(tenant_id or organization.id)),
                organization_id=organization_id,
                aggregate_type=str(aggregate_type or "").strip()[:64],
                aggregate_id=aggregate_uuid,
                event_type=str(event_type or "").strip()[:128],
                event_version=max(int(event_version or 1), 1),
                sequence=sequence,
                idempotency_key=key,
                payload=_domain_event_payload(payload or {}),
                occurred_at=occurred_at or timezone.now(),
            )
            _maybe_enqueue_outbox(
                event,
                topic=outbox_topic,
                schema_version=outbox_schema_version,
                payload_json=outbox_payload,
                visibility=outbox_visibility,
                company=outbox_company,
            )
        except IntegrityError:
            duplicate = DomainEvent.objects.get(idempotency_key=key)
            _maybe_enqueue_outbox(
                duplicate,
                topic=outbox_topic,
                schema_version=outbox_schema_version,
                payload_json=outbox_payload,
                visibility=outbox_visibility,
                company=outbox_company,
            )
            return DomainEventResult(event=duplicate, created=False)
        return DomainEventResult(event=event, created=True)


def record_run_domain_event(run: Run, *, created: bool) -> DomainEventResult | None:
    organization = organization_for_run(run)
    if organization is None:
        return None
    event_time = run.ended_at or run.started_at or timezone.now()
    return record_domain_event(
        organization=organization,
        aggregate_type="run",
        aggregate_id=run.id,
        event_type="run.created" if created else "run.updated",
        idempotency_key=(
            f"run:{run.id}:{'created' if created else run.status}:"
            f"{_timestamp_key(run.ended_at or run.started_at)}"
        ),
        payload={
            "run_id": str(run.id),
            "status": run.status,
            "error_message": run.error_message,
            "started_at": _iso_or_none(run.started_at),
            "ended_at": _iso_or_none(run.ended_at),
            "graph_version_id": str(run.graph_version_id),
        },
        occurred_at=event_time,
    )


def record_run_event_domain_event(run_event: RunEvent) -> DomainEventResult | None:
    run = Run.objects.select_related("organization", "owner__default_organization").get(
        id=run_event.run_id
    )
    organization = organization_for_run(run)
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="run",
        aggregate_id=run.id,
        event_type=f"run_event.{run_event.event_type}",
        idempotency_key=f"run-event:{run_event.id}",
        payload={
            "run_event_id": str(run_event.id),
            "run_id": str(run.id),
            "source_event_type": run_event.event_type,
            "external_id": run_event.external_id,
            "trace_id": run_event.trace_id,
            "payload": run_event.payload if isinstance(run_event.payload, dict) else {},
        },
        occurred_at=run_event.created_at,
    )


def record_node_run_domain_event(node_run: NodeRun, *, created: bool) -> DomainEventResult | None:
    run = Run.objects.select_related("organization", "owner__default_organization").get(
        id=node_run.run_id
    )
    organization = organization_for_run(run)
    if organization is None:
        return None
    event_time = node_run.ended_at or node_run.started_at or timezone.now()
    return record_domain_event(
        organization=organization,
        aggregate_type="node_run",
        aggregate_id=node_run.id,
        event_type="node_run.created" if created else "node_run.updated",
        idempotency_key=(
            f"node-run:{node_run.id}:{node_run.status}:{node_run.attempt}:"
            f"{_timestamp_key(node_run.ended_at or node_run.started_at)}"
        ),
        payload=_node_run_payload(node_run),
        occurred_at=event_time,
    )


def record_task_lifecycle_domain_event(
    task_event: TaskLifecycleEvent,
) -> DomainEventResult | None:
    organization = task_event.organization
    return record_domain_event(
        organization=organization,
        aggregate_type="task",
        aggregate_id=task_event.lifecycle_task_id,
        event_type="task.lifecycle_transitioned",
        idempotency_key=f"task-lifecycle-event:{task_event.id}",
        payload={
            "task_lifecycle_event_id": str(task_event.id),
            "task_lifecycle_id": str(task_event.lifecycle_task_id),
            "run_id": str(task_event.run_id),
            "event_type": task_event.event_type,
            "source": task_event.source,
            "from_status": task_event.from_status,
            "to_status": task_event.to_status,
            "attempt_number": task_event.attempt_number,
            "outcome": task_event.outcome,
            "reason": task_event.reason,
            "payload": task_event.payload if isinstance(task_event.payload, dict) else {},
        },
        occurred_at=task_event.occurred_at,
    )


def record_approval_domain_event(
    approval: ApprovalTask,
    *,
    created: bool,
) -> DomainEventResult | None:
    run = Run.objects.select_related("organization", "owner__default_organization").get(
        id=approval.run_id
    )
    organization = organization_for_run(run)
    if organization is None:
        return None
    status_token = "created" if created else approval.status
    if approval.resolved_at is not None:
        status_token = f"{approval.status}:{approval.resolved_at.isoformat()}"
    return record_domain_event(
        organization=organization,
        aggregate_type="approval",
        aggregate_id=approval.id,
        event_type="decision.approval_created" if created else "decision.approval_updated",
        idempotency_key=f"approval-task:{approval.id}:{status_token}",
        payload={
            "approval_task_id": str(approval.id),
            "run_id": str(approval.run_id),
            "task_lifecycle_id": str(approval.task_lifecycle_id)
            if approval.task_lifecycle_id
            else None,
            "node_id": approval.node_id,
            "status": approval.status,
            "payload": approval.payload if isinstance(approval.payload, dict) else {},
            "result": approval.result if isinstance(approval.result, dict) else {},
            "created_at": approval.created_at.isoformat(),
            "resolved_at": _iso_or_none(approval.resolved_at),
        },
        occurred_at=approval.resolved_at or approval.created_at,
    )


def record_llm_usage_domain_event(llm_usage: LLMUsage) -> DomainEventResult | None:
    organization = Organization.objects.filter(id=llm_usage.tenant_id).first()
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="llm_usage",
        aggregate_id=llm_usage.id,
        event_type="accounting.llm_usage_recorded",
        idempotency_key=f"llm-usage:{llm_usage.id}",
        payload={
            "llm_usage_id": str(llm_usage.id),
            "run_id": str(llm_usage.run_id),
            "node_id": llm_usage.node_id,
            "provider": llm_usage.provider,
            "model": llm_usage.model,
            "total_tokens": llm_usage.total_tokens,
            "cost_usd": str(llm_usage.cost_usd),
            "external_key": llm_usage.external_key,
        },
        occurred_at=llm_usage.created_at,
    )


def record_memory_usage_domain_event(memory_usage: MemoryUsage) -> DomainEventResult | None:
    organization = Organization.objects.filter(id=memory_usage.tenant_id).first()
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="memory_usage",
        aggregate_id=memory_usage.id,
        event_type="accounting.memory_usage_recorded",
        idempotency_key=f"memory-usage:{memory_usage.id}:{memory_usage.updated_at.isoformat()}",
        payload={
            "memory_usage_id": str(memory_usage.id),
            "usage_date": memory_usage.usage_date.isoformat(),
            "total_tokens": memory_usage.summarization_total_tokens,
            "cost_usd": str(memory_usage.summarization_cost_usd),
        },
        occurred_at=memory_usage.updated_at,
    )


def record_memory_observation_domain_event(
    observation: MemoryObservation,
    *,
    created: bool,
) -> DomainEventResult | None:
    organization = Organization.objects.filter(id=observation.tenant_id).first()
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="memory_observation",
        aggregate_id=observation.id,
        event_type="memory.observation_created" if created else "memory.observation_updated",
        idempotency_key=f"memory-observation:{observation.id}:{observation.updated_at.isoformat()}",
        payload={
            "memory_observation_id": str(observation.id),
            "graph_id": str(observation.graph_id) if observation.graph_id else None,
            "run_id": str(observation.run_id) if observation.run_id else None,
            "agent_id": str(observation.agent_id) if observation.agent_id else None,
            "type": observation.type,
            "topic_key": observation.topic_key,
            "scope": observation.scope,
            "deleted_at": _iso_or_none(observation.deleted_at),
        },
        occurred_at=observation.updated_at,
    )


def record_graph_version_domain_event(graph_version: GraphVersion) -> DomainEventResult | None:
    organization = (
        graph_version.graph.organization or graph_version.graph.owner.default_organization
    )
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="graph_version",
        aggregate_id=graph_version.id,
        event_type="agent.registry_source_updated",
        idempotency_key=f"graph-version:{graph_version.id}",
        payload={
            "graph_version_id": str(graph_version.id),
            "graph_id": str(graph_version.graph_id),
            "version": graph_version.version,
        },
        occurred_at=graph_version.created_at,
    )


def record_audit_review_domain_event(audit_log: AuditLog) -> DomainEventResult | None:
    if "review" not in audit_log.action.lower():
        return None
    organization = Organization.objects.filter(id=audit_log.tenant_id).first()
    if organization is None:
        return None
    return record_domain_event(
        organization=organization,
        aggregate_type="audit_log",
        aggregate_id=audit_log.id,
        event_type="decision.audit_review_recorded",
        idempotency_key=f"audit-review:{audit_log.id}",
        payload={
            "audit_log_id": str(audit_log.id),
            "action": audit_log.action,
            "resource_type": audit_log.resource_type,
            "resource_id": audit_log.resource_id,
            "metadata": audit_log.metadata if isinstance(audit_log.metadata, dict) else {},
        },
        occurred_at=audit_log.created_at,
    )


def backfill_domain_events_for_organization(organization: Organization) -> int:
    """Create missing baseline projection events from backend canonical tables."""

    before = DomainEvent.objects.filter(organization=organization).count()
    _backfill_graph_version_domain_events(organization)
    run_ids = _backfill_run_domain_events(organization)
    _backfill_run_child_domain_events(run_ids)
    _backfill_organization_domain_events(organization, run_ids)
    after = DomainEvent.objects.filter(organization=organization).count()
    return max(after - before, 0)


def _backfill_graph_version_domain_events(organization: Organization) -> None:
    for graph_version in GraphVersion.objects.filter(
        graph__organization=organization,
    ).select_related("graph", "graph__owner__default_organization"):
        record_graph_version_domain_event(graph_version)
    for graph_version in GraphVersion.objects.filter(
        graph__organization__isnull=True,
        graph__owner__default_organization=organization,
    ).select_related("graph", "graph__owner__default_organization"):
        record_graph_version_domain_event(graph_version)


def _backfill_run_domain_events(organization: Organization) -> list[UUID]:
    for run in Run.objects.filter(organization=organization).select_related(
        "organization", "owner__default_organization"
    ):
        record_run_domain_event(run, created=True)
    for run in Run.objects.filter(
        organization__isnull=True,
        owner__default_organization=organization,
    ).select_related("organization", "owner__default_organization"):
        record_run_domain_event(run, created=True)
    run_ids = list(
        Run.objects.filter(organization=organization).values_list("id", flat=True)
    ) + list(
        Run.objects.filter(
            organization__isnull=True,
            owner__default_organization=organization,
        ).values_list("id", flat=True)
    )
    return run_ids


def _backfill_run_child_domain_events(run_ids: list[UUID]) -> None:
    for run_event in RunEvent.objects.filter(run_id__in=run_ids).select_related("run"):
        record_run_event_domain_event(run_event)
    for node_run in NodeRun.objects.filter(run_id__in=run_ids).select_related("run"):
        record_node_run_domain_event(node_run, created=True)


def _backfill_organization_domain_events(organization: Organization, run_ids: list[UUID]) -> None:
    for task_event in TaskLifecycleEvent.objects.filter(organization=organization).select_related(
        "organization"
    ):
        record_task_lifecycle_domain_event(task_event)
    for approval in ApprovalTask.objects.filter(run_id__in=run_ids).select_related("run"):
        record_approval_domain_event(approval, created=True)
    for llm_usage in LLMUsage.objects.filter(tenant_id=organization.id):
        record_llm_usage_domain_event(llm_usage)
    for memory_usage in MemoryUsage.objects.filter(tenant_id=organization.id):
        record_memory_usage_domain_event(memory_usage)
    for observation in MemoryObservation.objects.filter(tenant_id=organization.id):
        record_memory_observation_domain_event(observation, created=True)
    for audit_log in AuditLog.objects.filter(tenant_id=organization.id, action__icontains="review"):
        record_audit_review_domain_event(audit_log)


def organization_for_run(run: Run) -> Organization | None:
    if run.organization_id:
        return run.organization
    graph_org = run.graph_version.graph.organization
    if graph_org is not None:
        return graph_org
    return run.owner.default_organization


def _allocate_sequence(organization_id: UUID) -> int:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('domain_event_global_sequence')")
            return int(cursor.fetchone()[0])

    row, _ = OrganizationDomainEventSequence.objects.select_for_update().get_or_create(
        organization_id=organization_id,
        defaults={"next_sequence": 1},
    )
    sequence = int(row.next_sequence)
    row.next_sequence = sequence + 1
    row.save(update_fields=["next_sequence", "updated_at"])
    return sequence


def _json_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(payload, cls=DjangoJSONEncoder)))


def _domain_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _json_safe_payload(sanitize_outbox_payload(payload))


def _maybe_enqueue_outbox(
    event: DomainEvent,
    *,
    topic: str | None,
    schema_version: str,
    payload_json: dict[str, Any] | None,
    visibility: str,
    company: Graph | None,
) -> None:
    if not topic:
        return
    enqueue_domain_event_outbox(
        domain_event=event,
        topic=topic,
        schema_version=schema_version,
        payload_json=payload_json,
        visibility=visibility,
        company=company,
        idempotency_key=f"domain-event-outbox:{event.id}",
    )


def _node_run_payload(node_run: NodeRun) -> dict[str, Any]:
    return {
        "node_run_id": str(node_run.id),
        "run_id": str(node_run.run_id),
        "node_id": node_run.node_id,
        "node_type": node_run.node_type,
        "status": node_run.status,
        "attempt": node_run.attempt,
        "started_at": _iso_or_none(node_run.started_at),
        "ended_at": _iso_or_none(node_run.ended_at),
    }


def _compact_key(value: str) -> str:
    return str(value or "").strip()[:255]


def _timestamp_key(value: Any) -> str:
    if value is None:
        return "none"
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()
