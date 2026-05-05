from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import models

from infrastructure.orm.models import (
    AgentRegistryEntry,
    CostAggregate,
    CostLedgerEntry,
    DomainEvent,
    LLMUsage,
    MemoryUsage,
    ProcessedAccountingEvent,
    TaskRecord,
)

DECIMAL_ZERO = Decimal("0")


def apply(event: DomainEvent) -> None:
    llm_usage_id = str(event.payload.get("llm_usage_id") or "").strip()
    memory_usage_id = str(event.payload.get("memory_usage_id") or "").strip()
    if llm_usage_id:
        llm_usage = (
            LLMUsage.objects.select_related("run__graph_version").filter(id=llm_usage_id).first()
        )
        if llm_usage is not None:
            entry = _project_llm_usage(llm_usage)
            _refresh_buckets(entry)
    if memory_usage_id:
        memory_usage = MemoryUsage.objects.filter(id=memory_usage_id).first()
        if memory_usage is not None:
            entry = _project_memory_usage(memory_usage)
            _refresh_buckets(entry)


def _project_llm_usage(usage: LLMUsage) -> CostLedgerEntry:
    organization_id = usage.tenant_id
    task = TaskRecord.objects.filter(
        organization_id=organization_id,
        execution=usage.run,
        source_node_id=usage.node_id,
    ).first()
    agent = task.agent if task else _agent_for_usage(usage)
    unit_cost = usage.cost_usd / usage.total_tokens if usage.total_tokens else DECIMAL_ZERO
    ledger, _ = CostLedgerEntry.objects.update_or_create(
        organization_id=organization_id,
        external_key=f"llm:{usage.id}",
        defaults={
            "execution": usage.run,
            "task": task,
            "agent": agent,
            "workflow_revision": usage.run.graph_version,
            "provider": usage.provider,
            "model": usage.model,
            "cost_type": "llm",
            "quantity": Decimal(usage.total_tokens),
            "unit_cost_usd": unit_cost,
            "total_cost_usd": usage.cost_usd,
            "occurred_at": usage.created_at,
        },
    )
    ProcessedAccountingEvent.objects.update_or_create(
        organization_id=organization_id,
        event_key=usage.external_key or f"llm:{usage.id}",
        defaults={
            "event_type": "llm_usage",
            "request_hash": "",
            "llm_usage": usage,
            "cost_ledger_entry": ledger,
            "status": "applied",
        },
    )
    return ledger


def _project_memory_usage(usage: MemoryUsage) -> CostLedgerEntry:
    occurred_at = datetime.combine(usage.usage_date, datetime.min.time(), tzinfo=UTC)
    quantity = Decimal(usage.summarization_total_tokens)
    unit_cost = usage.summarization_cost_usd / quantity if quantity > 0 else DECIMAL_ZERO
    ledger, _ = CostLedgerEntry.objects.update_or_create(
        organization_id=usage.tenant_id,
        external_key=f"memory:{usage.id}",
        defaults={
            "execution": None,
            "task": None,
            "agent": None,
            "workflow_revision": None,
            "provider": "forgegraph",
            "model": "memory-summarization",
            "cost_type": "memory_summarization",
            "quantity": quantity,
            "unit_cost_usd": unit_cost,
            "total_cost_usd": usage.summarization_cost_usd,
            "occurred_at": occurred_at,
        },
    )
    ProcessedAccountingEvent.objects.update_or_create(
        organization_id=usage.tenant_id,
        event_key=f"memory:{usage.id}",
        defaults={
            "event_type": "memory_usage",
            "request_hash": "",
            "memory_usage": usage,
            "cost_ledger_entry": ledger,
            "status": "applied",
        },
    )
    return ledger


def _refresh_buckets(entry: CostLedgerEntry) -> None:
    for grain in ("hourly", "daily"):
        period_start = _period_start(entry.occurred_at, grain)
        period_end = period_start + (timedelta(hours=1) if grain == "hourly" else timedelta(days=1))
        queryset = CostLedgerEntry.objects.filter(
            organization=entry.organization,
            agent=entry.agent,
            provider=entry.provider,
            model=entry.model,
            cost_type=entry.cost_type,
            occurred_at__gte=period_start,
            occurred_at__lt=period_end,
        )
        totals = queryset.aggregate(
            total_cost=models.Sum("total_cost_usd"),
            total_quantity=models.Sum("quantity"),
            entry_count=models.Count("id"),
        )
        total_cost = totals["total_cost"] or DECIMAL_ZERO
        total_quantity = totals["total_quantity"] or DECIMAL_ZERO
        entry_count = int(totals["entry_count"] or 0)
        workflow_revision_id = (
            queryset.exclude(workflow_revision__isnull=True)
            .values_list("workflow_revision_id", flat=True)
            .first()
        )
        CostAggregate.objects.update_or_create(
            organization=entry.organization,
            external_key=(
                f"{grain}:{entry.agent_id or ''}:{entry.provider}:{entry.model}:"
                f"{entry.cost_type}:{period_start.isoformat()}"
            ),
            defaults={
                "agent": entry.agent,
                "task": None,
                "workflow_revision_id": workflow_revision_id,
                "grain": grain,
                "period_start": period_start,
                "period_end": period_end,
                "provider": entry.provider,
                "model": entry.model,
                "cost_type": entry.cost_type,
                "total_cost_usd": total_cost,
                "total_quantity": total_quantity,
                "entry_count": entry_count,
            },
        )


def _period_start(value: datetime, grain: str) -> datetime:
    occurred_at = value.astimezone(UTC)
    period_start = occurred_at.replace(minute=0, second=0, microsecond=0)
    if grain == "daily":
        period_start = period_start.replace(hour=0)
    return period_start


def _agent_for_usage(usage: LLMUsage) -> AgentRegistryEntry | None:
    return AgentRegistryEntry.objects.filter(
        organization_id=usage.tenant_id,
        source_workflow=usage.run.graph_version.graph,
        source_node_id=usage.node_id,
    ).first()
