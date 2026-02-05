from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from django.db.models import Model, QuerySet

from infrastructure.orm.models import (
    ApprovalTask,
    AuditLog,
    LLMUsage,
    MemoryUsage,
    NodeRun,
    Organization,
    Run,
    RunCheckpoint,
    RunEvent,
    TenantRetentionPolicy,
)

logger = logging.getLogger(__name__)


@dataclass
class RetentionCleanupResult:
    tenant_id: str
    dry_run: bool
    runs_deleted: int = 0
    run_events_deleted: int = 0
    node_runs_deleted: int = 0
    run_checkpoints_deleted: int = 0
    approval_tasks_deleted: int = 0
    audit_logs_deleted: int = 0
    llm_usage_deleted: int = 0
    memory_usage_deleted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_deleted(self) -> int:
        return (
            self.runs_deleted
            + self.run_events_deleted
            + self.node_runs_deleted
            + self.run_checkpoints_deleted
            + self.approval_tasks_deleted
            + self.audit_logs_deleted
            + self.llm_usage_deleted
            + self.memory_usage_deleted
        )

    @property
    def run_logs_deleted(self) -> int:
        return (
            self.run_events_deleted
            + self.node_runs_deleted
            + self.run_checkpoints_deleted
            + self.approval_tasks_deleted
        )

    def to_dict(self, retention_days: Mapping[str, int | None]) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "dry_run": self.dry_run,
            "retention_days": retention_days,
            "runs_deleted": self.runs_deleted,
            "run_logs_deleted": self.run_logs_deleted,
            "run_events_deleted": self.run_events_deleted,
            "node_runs_deleted": self.node_runs_deleted,
            "run_checkpoints_deleted": self.run_checkpoints_deleted,
            "approval_tasks_deleted": self.approval_tasks_deleted,
            "audit_logs_deleted": self.audit_logs_deleted,
            "llm_usage_deleted": self.llm_usage_deleted,
            "memory_usage_deleted": self.memory_usage_deleted,
            "total_deleted": self.total_deleted,
            "errors": self.errors,
        }


class DataRetentionService:
    """Cleanup service for tenant data retention policies."""

    def __init__(self, batch_size: int = 1000) -> None:
        self.batch_size = batch_size

    def cleanup_tenant(
        self,
        tenant_id: str,
        policy: TenantRetentionPolicy | None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        retention_days: dict[str, int | None] = {
            "runs": None,
            "run_logs": None,
            "audit_logs": None,
            "usage": None,
        }

        if policy:
            retention_days = {
                "runs": policy.runs_retention_days,
                "run_logs": policy.run_logs_retention_days,
                "audit_logs": policy.audit_logs_retention_days,
                "usage": policy.usage_retention_days,
            }

        result = RetentionCleanupResult(tenant_id=tenant_id, dry_run=dry_run)
        if policy is None:
            return result.to_dict(retention_days)

        now = datetime.now(UTC)
        tenant_uuid = UUID(tenant_id)
        run_cutoff = (
            now - timedelta(days=policy.runs_retention_days) if policy.runs_retention_days else None
        )
        log_cutoff = (
            now - timedelta(days=policy.run_logs_retention_days)
            if policy.run_logs_retention_days
            else None
        )
        audit_cutoff = (
            now - timedelta(days=policy.audit_logs_retention_days)
            if policy.audit_logs_retention_days
            else None
        )
        usage_cutoff = (
            now - timedelta(days=policy.usage_retention_days)
            if policy.usage_retention_days
            else None
        )

        if run_cutoff:
            runs_qs = Run.objects.filter(
                owner__default_organization_id=tenant_uuid,
                ended_at__isnull=False,
                ended_at__lt=run_cutoff,
            )
            run_ids_qs = runs_qs.values_list("id", flat=True)
            result.run_events_deleted += RunEvent.objects.filter(run_id__in=run_ids_qs).count()
            result.node_runs_deleted += NodeRun.objects.filter(run_id__in=run_ids_qs).count()
            result.run_checkpoints_deleted += RunCheckpoint.objects.filter(
                run_id__in=run_ids_qs
            ).count()
            result.approval_tasks_deleted += ApprovalTask.objects.filter(
                run_id__in=run_ids_qs
            ).count()
            result.llm_usage_deleted += LLMUsage.objects.filter(run_id__in=run_ids_qs).count()
            result.runs_deleted = self._delete_queryset(runs_qs, dry_run=dry_run)

        if log_cutoff:
            log_filters = {
                "run__owner__default_organization_id": tenant_uuid,
                "run__ended_at__isnull": False,
                "run__ended_at__lt": log_cutoff,
            }
            run_exclusion = {}
            if run_cutoff:
                run_exclusion = {"run__ended_at__lt": run_cutoff}

            run_events_qs = RunEvent.objects.filter(**log_filters)
            node_runs_qs = NodeRun.objects.filter(**log_filters)
            run_checkpoints_qs = RunCheckpoint.objects.filter(**log_filters)
            approval_tasks_qs = ApprovalTask.objects.filter(**log_filters)

            if run_exclusion:
                run_events_qs = run_events_qs.exclude(**run_exclusion)
                node_runs_qs = node_runs_qs.exclude(**run_exclusion)
                run_checkpoints_qs = run_checkpoints_qs.exclude(**run_exclusion)
                approval_tasks_qs = approval_tasks_qs.exclude(**run_exclusion)

            result.run_events_deleted += self._delete_queryset(run_events_qs, dry_run=dry_run)
            result.node_runs_deleted += self._delete_queryset(node_runs_qs, dry_run=dry_run)
            result.run_checkpoints_deleted += self._delete_queryset(
                run_checkpoints_qs, dry_run=dry_run
            )
            result.approval_tasks_deleted += self._delete_queryset(
                approval_tasks_qs, dry_run=dry_run
            )

        if audit_cutoff:
            audit_qs = AuditLog.objects.filter(tenant_id=tenant_uuid, created_at__lt=audit_cutoff)
            result.audit_logs_deleted += self._delete_queryset(audit_qs, dry_run=dry_run)

        if usage_cutoff:
            llm_usage_qs = LLMUsage.objects.filter(
                tenant_id=tenant_uuid, created_at__lt=usage_cutoff
            )
            if run_cutoff:
                llm_usage_qs = llm_usage_qs.exclude(run__ended_at__lt=run_cutoff)
            result.llm_usage_deleted += self._delete_queryset(llm_usage_qs, dry_run=dry_run)

            memory_usage_cutoff = usage_cutoff.date()
            memory_usage_qs = MemoryUsage.objects.filter(
                tenant_id=tenant_uuid, usage_date__lt=memory_usage_cutoff
            )
            result.memory_usage_deleted += self._delete_queryset(memory_usage_qs, dry_run=dry_run)

        return result.to_dict(retention_days)

    def cleanup_all(
        self,
        *,
        tenant_ids: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        policies = TenantRetentionPolicy.objects.all()
        if tenant_ids:
            policies = policies.filter(tenant_id__in=tenant_ids)

        results: list[dict[str, Any]] = []
        total_deleted = 0

        for policy in policies:
            result = self.cleanup_tenant(str(policy.tenant_id), policy, dry_run=dry_run)
            results.append(result)
            total_deleted += int(result.get("total_deleted", 0))

        if tenant_ids:
            policy_ids = {str(tid) for tid in policies.values_list("tenant_id", flat=True)}
            missing = {str(tid) for tid in tenant_ids} - policy_ids
            if missing:
                logger.warning(
                    "Retention cleanup skipped missing tenants",
                    extra={"tenant_ids": [str(tid) for tid in missing]},
                )

        return {
            "dry_run": dry_run,
            "tenants": results,
            "total_deleted": total_deleted,
        }

    def cleanup_orphaned_policies(self, dry_run: bool = False) -> dict[str, Any]:
        valid_ids = set(Organization.objects.values_list("id", flat=True))
        orphaned_qs = TenantRetentionPolicy.objects.exclude(tenant_id__in=valid_ids)
        deleted = self._delete_queryset(orphaned_qs, dry_run=dry_run)
        return {"dry_run": dry_run, "orphaned_policies_deleted": deleted}

    def _delete_queryset(self, qs: QuerySet[Model], *, dry_run: bool) -> int:
        count = qs.count()
        if dry_run or count == 0:
            return count

        deleted_total = 0
        while True:
            batch_ids = list(qs.values_list("pk", flat=True)[: self.batch_size])
            if not batch_ids:
                break
            qs.filter(pk__in=batch_ids).delete()
            deleted_total += len(batch_ids)

        return deleted_total
