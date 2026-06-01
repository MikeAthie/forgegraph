"""Computed portfolio read models for company-scoped operations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from application.services.company_access import accessible_company_queryset
from application.services.credential_state import is_credential_revoked
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    CompanySignal,
    DecisionRecord,
    Graph,
    MetricSnapshot,
    PeriodicReviewDefinition,
    ReportRun,
    Run,
    TaskRecord,
    User,
)

ACTIVE_RUN_STATUSES = {"pending", "running", "paused", "resume_requested"}
ACTIVE_TASK_STATUSES = {
    "created",
    "queued",
    "claimed",
    "running",
    "paused",
    "waiting",
    "waiting_for_decision",
    "retry_scheduled",
}


def portfolio_health_payload(user: User) -> dict[str, Any]:
    companies = list(_accessible_companies(user))
    company_ids = [company.id for company in companies]
    primary_by_company, pack_counts_by_company = _pack_maps(company_ids)
    review_counts = _count_by_company(
        PeriodicReviewDefinition.objects.filter(company_id__in=company_ids, enabled=True),
        "company_id",
    )
    report_counts = _count_by_company(
        ReportRun.objects.filter(company_id__in=company_ids),
        "company_id",
    )
    metric_gaps = _metric_gap_count_by_company(company_ids)
    pending_approvals = _count_by_company(
        _approval_queryset(user, company_ids), "run__graph_version__graph_id"
    )
    pending_decisions = _decision_count_by_company(user, company_ids)
    pending_tasks = _count_by_company(
        _task_queryset(user, company_ids), "execution__graph_version__graph_id"
    )
    active_runs = _count_by_company(
        Run.objects.filter(
            graph_version__graph_id__in=company_ids,
            status__in=ACTIVE_RUN_STATUSES,
        ),
        "graph_version__graph_id",
    )
    failed_runs = _count_by_company(
        Run.objects.filter(graph_version__graph_id__in=company_ids, status="failed"),
        "graph_version__graph_id",
    )
    signal_counts = _signal_summary_by_company(company_ids)
    latest_reports = _latest_report_by_company(company_ids)
    credential_health = _credential_health_by_company(user, company_ids)

    rows: list[dict[str, Any]] = []
    summary = {
        "total_companies": len(companies),
        "healthy": 0,
        "attention": 0,
        "blocked": 0,
        "active_operations": 0,
        "pending_approvals": 0,
        "metric_gaps": 0,
        "credential_blockers": 0,
    }
    for company in companies:
        company_id = company.id
        blockers = int(metric_gaps[company_id]) + int(pending_approvals[company_id])
        attention = (
            int(pending_tasks[company_id])
            + int(pending_decisions[company_id])
            + int(failed_runs[company_id])
        )
        credential_status = credential_health[str(company_id)]["status"]
        if credential_status in {"missing", "expired", "revoked"}:
            blockers += 1
            summary["credential_blockers"] += 1
        health_status = "blocked" if blockers else "attention" if attention else "healthy"
        summary[health_status] += 1
        summary["active_operations"] += int(active_runs[company_id])
        summary["pending_approvals"] += int(pending_approvals[company_id])
        summary["metric_gaps"] += int(metric_gaps[company_id])
        rows.append(
            {
                "company_id": str(company_id),
                "company_name": company.name,
                "company_description": company.description,
                "health_status": health_status,
                "health_score": _health_score(blockers=blockers, attention=attention),
                "primary_pack": primary_by_company.get(company_id),
                "pack_counts": pack_counts_by_company[company_id],
                "active_operations_count": active_runs[company_id],
                "failed_operations_count": failed_runs[company_id],
                "pending_approval_count": pending_approvals[company_id],
                "pending_decision_count": pending_decisions[company_id],
                "pending_task_count": pending_tasks[company_id],
                "enabled_review_count": review_counts[company_id],
                "report_run_count": report_counts[company_id],
                "metric_gap_count": metric_gaps[company_id],
                "signal_summary": signal_counts[company_id],
                "credential_health": credential_health[str(company_id)],
                "latest_report": latest_reports.get(company_id),
                "updated_at": company.updated_at.isoformat(),
            }
        )
    return {
        "organization_id": str(user.default_organization_id or ""),
        "source": "computed",
        "generated_at": timezone.now().isoformat(),
        "summary": summary,
        "companies": rows,
    }


def portfolios_payload(user: User) -> dict[str, Any]:
    return {
        "portfolios": [
            {
                "id": "default",
                "name": "Portfolio",
                "source": "computed",
                "organization_id": str(user.default_organization_id or ""),
            }
        ]
    }


def portfolio_views_payload(user: User) -> dict[str, Any]:
    health = portfolio_health_payload(user)
    return {
        "views": [
            {
                "id": "default",
                "name": "Portfolio Home",
                "source": "computed",
                "filters": {},
                "summary": health["summary"],
                "rows": health["companies"],
            }
        ]
    }


def cross_company_queues_payload(user: User, queue_type: str = "all") -> dict[str, Any]:
    companies = list(_accessible_companies(user))
    company_ids = [company.id for company in companies]
    company_names = {company.id: company.name for company in companies}
    queues = {
        "reviews": _review_queue(company_ids, company_names),
        "approvals": _approval_queue(user, company_ids, company_names),
        "metric_gaps": _metric_gap_queue(company_ids, company_names),
        "credentials": _credential_queue(user, company_ids, company_names),
        "tasks": _task_queue(user, company_ids, company_names),
    }
    if queue_type != "all":
        queues = {queue_type: queues.get(queue_type, [])}
    return {
        "type": queue_type,
        "source": "computed",
        "generated_at": timezone.now().isoformat(),
        "counts": {key: len(value) for key, value in queues.items()},
        "queues": queues,
    }


def credential_health_payload(user: User) -> dict[str, Any]:
    companies = list(_accessible_companies(user))
    company_ids = [company.id for company in companies]
    health_by_company = _credential_health_by_company(user, company_ids)
    return {
        "source": "computed",
        "generated_at": timezone.now().isoformat(),
        "scope": "organization_fallback",
        "companies": list(health_by_company.values()),
    }


def company_assignment_payload(assignment: CompanyAssignment) -> dict[str, Any]:
    return {
        "id": str(assignment.id),
        "organization_id": str(assignment.organization_id),
        "company_id": str(assignment.company_id),
        "company_name": assignment.company.name,
        "user_id": str(assignment.user_id),
        "email": assignment.user.email,
        "role": assignment.role,
        "status": assignment.status,
        "expires_at": assignment.expires_at.isoformat() if assignment.expires_at else None,
        "created_at": assignment.created_at.isoformat(),
        "updated_at": assignment.updated_at.isoformat(),
    }


def accessible_company_ids(user: User, *, minimum_role: str = "viewer") -> list[UUID]:
    return [company.id for company in _accessible_companies(user, minimum_role=minimum_role)]


def _accessible_companies(user: User, *, minimum_role: str = "viewer") -> QuerySet[Graph]:
    return accessible_company_queryset(user, minimum_role=minimum_role).order_by("name", "id")


def _pack_maps(
    company_ids: list[UUID],
) -> tuple[dict[UUID, dict[str, Any]], defaultdict[UUID, dict[str, int]]]:
    primary_by_company: dict[UUID, dict[str, Any]] = {}
    counts: defaultdict[UUID, dict[str, int]] = defaultdict(
        lambda: {"active": 0, "primary": 0, "addon": 0, "disabled": 0, "archived": 0}
    )
    installs = CompanyOperatingModelInstallation.objects.filter(company_id__in=company_ids)
    installs = installs.select_related("pack_release").order_by("company_id", "role", "pack_id")
    for install in installs:
        bucket = counts[install.company_id]
        if install.status == "active":
            bucket["active"] += 1
            if install.role in {"primary", "addon"}:
                bucket[install.role] += 1
        elif install.status in {"disabled", "archived"}:
            bucket[install.status] += 1
        if install.status == "active" and install.role == "primary":
            primary_by_company[install.company_id] = {
                "installation_id": str(install.id),
                "pack_id": install.pack_id,
                "namespace": install.namespace or install.pack_id,
                "release_version": install.pack_release.version,
            }
    return primary_by_company, counts


def _count_by_company(queryset: Any, field_name: str) -> defaultdict[UUID, int]:
    counts: defaultdict[UUID, int] = defaultdict(int)
    for row in queryset.values(field_name).order_by().annotate(count=Count("id", distinct=True)):
        company_id = row.get(field_name)
        if company_id:
            counts[company_id] = int(row["count"])
    return counts


def _decision_count_by_company(user: User, company_ids: list[UUID]) -> defaultdict[UUID, int]:
    counts: defaultdict[UUID, int] = defaultdict(int)
    for decision in _decision_queryset(user, company_ids).select_related(
        "execution__graph_version__graph",
        "source_approval_task__run__graph_version__graph",
    ):
        company_id = None
        if decision.execution_id and decision.execution is not None:
            company_id = decision.execution.graph_version.graph_id
        elif (
            decision.source_approval_task_id
            and decision.source_approval_task is not None
            and decision.source_approval_task.run is not None
        ):
            company_id = decision.source_approval_task.run.graph_version.graph_id
        if company_id:
            counts[company_id] += 1
    return counts


def _metric_gap_count_by_company(company_ids: list[UUID]) -> defaultdict[UUID, int]:
    counts: defaultdict[UUID, int] = defaultdict(int)
    reviews = PeriodicReviewDefinition.objects.filter(company_id__in=company_ids, enabled=True)
    review_ids = list(reviews.values_list("id", flat=True))
    snapshots = set(
        MetricSnapshot.objects.filter(review_definition_id__in=review_ids).values_list(
            "review_definition_id", flat=True
        )
    )
    for review in reviews.only("id", "company_id"):
        if review.id not in snapshots:
            counts[review.company_id] += 1
    return counts


def _signal_summary_by_company(company_ids: list[UUID]) -> defaultdict[UUID, dict[str, Any]]:
    summary: defaultdict[UUID, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "new": 0, "qualified": 0, "latest_at": None}
    )
    signals = CompanySignal.objects.filter(company_id__in=company_ids).order_by(
        "company_id", "-occurred_at"
    )
    for signal in signals.only("company_id", "status", "occurred_at"):
        bucket = summary[signal.company_id]
        bucket["total"] += 1
        if signal.status in {"new", "qualified"}:
            bucket[signal.status] += 1
        if bucket["latest_at"] is None:
            bucket["latest_at"] = signal.occurred_at.isoformat()
    return summary


def _latest_report_by_company(company_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    latest: dict[UUID, dict[str, Any]] = {}
    reports = ReportRun.objects.filter(company_id__in=company_ids).order_by(
        "company_id", "-created_at"
    )
    for report in reports.only(
        "id",
        "company_id",
        "report_template_id",
        "period_start",
        "period_end",
        "created_at",
    ):
        if report.company_id in latest:
            continue
        latest[report.company_id] = {
            "report_run_id": str(report.id),
            "report_template_id": report.report_template_id,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "created_at": report.created_at.isoformat(),
        }
    return latest


def _credential_health_by_company(user: User, company_ids: list[UUID]) -> dict[str, dict[str, Any]]:
    organization = user.default_organization
    credentials = list(APIKey.objects.filter(organization=organization)) if organization else []
    now = timezone.now()
    provider_counts: defaultdict[str, int] = defaultdict(int)
    healthy = 0
    expired = 0
    revoked = 0
    for credential in credentials:
        provider_counts[credential.provider] += 1
        if is_credential_revoked(credential.token_metadata):
            revoked += 1
        elif credential.token_expires_at and credential.token_expires_at <= now:
            expired += 1
        else:
            healthy += 1
    if not credentials:
        status = "missing"
    elif healthy:
        status = "healthy" if not expired and not revoked else "attention"
    elif expired:
        status = "expired"
    else:
        status = "revoked"
    base = {
        "status": status,
        "scope": "organization_fallback",
        "healthy_count": healthy,
        "expired_count": expired,
        "revoked_count": revoked,
        "provider_counts": dict(provider_counts),
    }
    return {str(company_id): {"company_id": str(company_id), **base} for company_id in company_ids}


def _review_queue(
    company_ids: list[UUID],
    company_names: dict[UUID, str],
) -> list[dict[str, Any]]:
    snapshot_review_ids = set(
        MetricSnapshot.objects.filter(company_id__in=company_ids).values_list(
            "review_definition_id", flat=True
        )
    )
    latest_reports = _latest_report_by_company(company_ids)
    rows = []
    reviews = PeriodicReviewDefinition.objects.filter(
        company_id__in=company_ids,
        enabled=True,
    ).order_by("company__name", "display_name")
    for review in reviews:
        rows.append(
            {
                "queue_type": "reviews",
                "review_id": str(review.id),
                "company_id": str(review.company_id),
                "company_name": company_names.get(review.company_id, ""),
                "display_name": review.display_name,
                "cadence": review.cadence,
                "pack_id": review.pack_id,
                "status": "blocked" if review.id not in snapshot_review_ids else "ready",
                "blocker": "missing_metric_snapshot"
                if review.id not in snapshot_review_ids
                else None,
                "latest_report": latest_reports.get(review.company_id),
            }
        )
    return rows


def _approval_queue(
    user: User,
    company_ids: list[UUID],
    company_names: dict[UUID, str],
) -> list[dict[str, Any]]:
    rows = []
    approvals = _approval_queryset(user, company_ids).select_related("run__graph_version__graph")
    for approval in approvals.order_by("-created_at")[:200]:
        company = approval.run.graph_version.graph
        rows.append(
            {
                "queue_type": "approvals",
                "approval_id": str(approval.id),
                "company_id": str(company.id),
                "company_name": company_names.get(company.id, company.name),
                "run_id": str(approval.run_id),
                "node_id": approval.node_id,
                "status": approval.status,
                "assignee_id": str(approval.assignee_id) if approval.assignee_id else None,
                "created_at": approval.created_at.isoformat(),
            }
        )
    return rows


def _metric_gap_queue(
    company_ids: list[UUID],
    company_names: dict[UUID, str],
) -> list[dict[str, Any]]:
    snapshot_review_ids = set(
        MetricSnapshot.objects.filter(company_id__in=company_ids).values_list(
            "review_definition_id", flat=True
        )
    )
    rows = []
    reviews = PeriodicReviewDefinition.objects.filter(
        company_id__in=company_ids,
        enabled=True,
    ).order_by("company__name", "display_name")
    for review in reviews:
        if review.id in snapshot_review_ids:
            continue
        rows.append(
            {
                "queue_type": "metric_gaps",
                "company_id": str(review.company_id),
                "company_name": company_names.get(review.company_id, ""),
                "review_id": str(review.id),
                "metric_source": "review_definition",
                "gap": "missing_metric_snapshot",
                "pack_id": review.pack_id,
                "cadence": review.cadence,
            }
        )
    return rows


def _credential_queue(
    user: User,
    company_ids: list[UUID],
    company_names: dict[UUID, str],
) -> list[dict[str, Any]]:
    health = _credential_health_by_company(user, company_ids)
    rows = []
    for company_id in company_ids:
        item = health[str(company_id)]
        if item["status"] == "healthy":
            continue
        rows.append(
            {
                "queue_type": "credentials",
                "company_id": str(company_id),
                "company_name": company_names.get(company_id, ""),
                "status": item["status"],
                "scope": item["scope"],
                "healthy_count": item["healthy_count"],
                "expired_count": item["expired_count"],
                "revoked_count": item["revoked_count"],
            }
        )
    return rows


def _task_queue(
    user: User,
    company_ids: list[UUID],
    company_names: dict[UUID, str],
) -> list[dict[str, Any]]:
    rows = []
    tasks = _task_queryset(user, company_ids).select_related("execution__graph_version__graph")
    for task in tasks.order_by("-updated_at", "-created_at")[:200]:
        company = task.execution.graph_version.graph
        rows.append(
            {
                "queue_type": "tasks",
                "task_id": str(task.id),
                "company_id": str(company.id),
                "company_name": company_names.get(company.id, company.name),
                "run_id": str(task.execution_id),
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "updated_at": task.updated_at.isoformat(),
            }
        )
    return rows


def _approval_queryset(user: User, company_ids: list[UUID]) -> QuerySet[ApprovalTask]:
    _ = user
    return ApprovalTask.objects.filter(
        run__graph_version__graph_id__in=company_ids,
        status="pending",
    )


def _decision_queryset(user: User, company_ids: list[UUID]) -> QuerySet[DecisionRecord]:
    return DecisionRecord.objects.filter(status="pending").filter(
        Q(execution__graph_version__graph_id__in=company_ids)
        | Q(source_approval_task__run__graph_version__graph_id__in=company_ids)
    )


def _task_queryset(user: User, company_ids: list[UUID]) -> QuerySet[TaskRecord]:
    _ = user
    return TaskRecord.objects.filter(
        execution__graph_version__graph_id__in=company_ids,
        status__in=ACTIVE_TASK_STATUSES,
    )


def _health_score(*, blockers: int, attention: int) -> int:
    return max(0, min(100, 100 - blockers * 20 - attention * 8))
