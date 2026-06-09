"""Virtual Atlas agency onboarding checklist assembly."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from application.services.agency_account_catalog import list_onboarding_item_definitions
from application.services.agency_connector_readiness import build_connector_readiness
from infrastructure.orm.models import (
    Graph,
    PeriodicReviewDefinition,
    ReportRun,
    ServiceDeliverable,
    ServiceEngagement,
    WorkWhiteboard,
)

STALE_APPROVAL_DAYS = 7
RECENT_REPORT_DAYS = 45


def build_virtual_onboarding_checklist(
    company: Graph,
    *,
    connector_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = connector_readiness or build_connector_readiness(company)
    items = [
        _item_payload(definition, company=company, connector_readiness=readiness)
        for definition in list_onboarding_item_definitions()
    ]
    return {"summary": _summary(items), "items": items}


def has_recent_report(company: Graph) -> bool:
    threshold = timezone.now().date() - timedelta(days=RECENT_REPORT_DAYS)
    return ReportRun.objects.filter(company=company, period_end__gte=threshold).exists()


def has_reporting_cadence(company: Graph) -> bool:
    return PeriodicReviewDefinition.objects.filter(company=company, enabled=True).exists()


def stale_approval_count(company: Graph) -> int:
    threshold = timezone.now() - timedelta(days=STALE_APPROVAL_DAYS)
    return ServiceDeliverable.objects.filter(
        company=company,
        status="in_review",
        updated_at__lt=threshold,
    ).count()


def in_review_deliverable_count(company: Graph) -> int:
    return ServiceDeliverable.objects.filter(company=company, status="in_review").count()


def _item_payload(
    definition: Any, *, company: Graph, connector_readiness: dict[str, Any]
) -> dict[str, Any]:
    status, message = _item_status(definition.slug, company, connector_readiness)
    return {
        "slug": definition.slug,
        "label": definition.label,
        "status": status,
        "owner_department_slug": definition.owner_department_slug,
        "message": message,
    }


def _item_status(
    slug: str,
    company: Graph,
    connector_readiness: dict[str, Any],
) -> tuple[str, str]:
    handlers = {
        "client_profile": _client_profile_status,
        "brand_context": _brand_context_status,
        "service_engagement": _service_engagement_status,
        "connector_setup": lambda scoped_company: _connector_setup_status(connector_readiness),
        "approval_workflow": _approval_workflow_status,
        "reporting_cadence": _reporting_cadence_status,
    }
    handler = handlers.get(slug)
    if handler is None:
        return "not_started", "No onboarding evidence is available."
    return handler(company)


def _client_profile_status(company: Graph) -> tuple[str, str]:
    if company.description.strip() or _latest_whiteboard(company) is not None:
        return "completed", "Client profile context is available."
    return "not_started", "Client profile context has not been recorded."


def _brand_context_status(company: Graph) -> tuple[str, str]:
    whiteboard = _latest_whiteboard(company)
    if whiteboard is not None and bool(whiteboard.brand_context_json):
        return "completed", "Brand context is available."
    return "not_started", "Brand context has not been recorded."


def _service_engagement_status(company: Graph) -> tuple[str, str]:
    active_statuses = {"intake", "in_progress", "waiting_on_customer", "in_review", "delivered"}
    if ServiceEngagement.objects.filter(company=company, status__in=active_statuses).exists():
        return "completed", "An active service engagement is in place."
    return "not_started", "No active service engagement is in place."


def _connector_setup_status(readiness: dict[str, Any]) -> tuple[str, str]:
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    if int(summary.get("missing") or 0):
        return "blocked", "Required connectors are missing."
    if int(summary.get("degraded") or 0) or int(summary.get("disabled") or 0):
        return "in_progress", "Connectors need readiness review."
    return "completed", "Required connectors are ready."


def _approval_workflow_status(company: Graph) -> tuple[str, str]:
    stale_count = stale_approval_count(company)
    if stale_count:
        return "blocked", "Client approvals are stale."
    if in_review_deliverable_count(company):
        return "in_progress", "Client approvals are in review."
    return "not_started", "No client approval workflow is active."


def _reporting_cadence_status(company: Graph) -> tuple[str, str]:
    if has_recent_report(company):
        return "completed", "A recent report is available."
    if has_reporting_cadence(company):
        return "in_progress", "A reporting cadence is configured."
    return "not_started", "No reporting cadence is configured."


def _latest_whiteboard(company: Graph) -> WorkWhiteboard | None:
    return WorkWhiteboard.objects.filter(company=company).order_by("-updated_at").first()


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "completed": sum(1 for item in items if item["status"] == "completed"),
        "in_progress": sum(1 for item in items if item["status"] == "in_progress"),
        "blocked": sum(1 for item in items if item["status"] == "blocked"),
        "not_started": sum(1 for item in items if item["status"] == "not_started"),
    }
