"""Backend-owned recurring reporting cadence read model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import Q
from django.utils import timezone

from infrastructure.orm.models import Graph, ReportRun, ServiceDeliverable, ServiceEngagement


@dataclass(frozen=True, slots=True)
class CadenceDefinition:
    slug: str
    label: str
    expected_frequency_days: int
    aliases: tuple[str, ...]


CADENCE_DEFINITIONS: tuple[CadenceDefinition, ...] = (
    CadenceDefinition(
        slug="weekly",
        label="Weekly performance reporting",
        expected_frequency_days=7,
        aliases=("weekly", "week"),
    ),
    CadenceDefinition(
        slug="monthly",
        label="Monthly performance reporting",
        expected_frequency_days=31,
        aliases=("monthly", "month"),
    ),
    CadenceDefinition(
        slug="qbr",
        label="Quarterly business review",
        expected_frequency_days=92,
        aliases=("qbr", "quarterly", "quarter", "business_review"),
    ),
)

REPORT_DELIVERABLE_STATUSES = {"ready", "delivered", "accepted"}


def build_recurring_reporting_status(company: Graph) -> dict[str, Any]:
    """Return client-safe recurring reporting status derived from backend state."""

    today = timezone.now().date()
    configured_slugs = _configured_cadence_slugs(company)
    cadences = [
        _cadence_payload(
            company=company,
            definition=definition,
            configured_slugs=configured_slugs,
            today=today,
        )
        for definition in CADENCE_DEFINITIONS
    ]
    risks = _risks(cadences)
    return {
        "company_id": str(company.id),
        "summary": _summary(cadences),
        "cadences": cadences,
        "risks": risks,
    }


def _cadence_payload(
    *,
    company: Graph,
    definition: CadenceDefinition,
    configured_slugs: set[str],
    today: date,
) -> dict[str, Any]:
    configured = definition.slug in configured_slugs
    report = _latest_report(company, definition)
    deliverable = _latest_deliverable(company, definition)
    last_report = _last_report_payload(report, today=today)
    latest_deliverable = _deliverable_payload(deliverable)
    status = _cadence_status(
        configured=configured,
        expected_frequency_days=definition.expected_frequency_days,
        last_report=last_report,
        latest_deliverable=latest_deliverable,
    )
    return {
        "slug": definition.slug,
        "label": definition.label,
        "configured": configured,
        "status": status,
        "expected_frequency_days": definition.expected_frequency_days,
        "last_report": last_report,
        "latest_deliverable": latest_deliverable,
        "message": _message(
            status=status,
            configured=configured,
            expected_frequency_days=definition.expected_frequency_days,
        ),
    }


def _configured_cadence_slugs(company: Graph) -> set[str]:
    configured: set[str] = set()
    engagements = ServiceEngagement.objects.filter(company=company).exclude(
        status__in={"cancelled", "archived"}
    )
    for engagement in engagements:
        metadata = _mapping(engagement.metadata_json)
        configured.update(_cadence_slugs_from_metadata(metadata))
    return configured


def _cadence_slugs_from_metadata(metadata: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    reporting = _mapping(metadata.get("reporting"))
    if reporting:
        values.extend(
            [
                reporting.get("cadence"),
                reporting.get("cadences"),
                reporting.get("frequency"),
                reporting.get("frequencies"),
            ]
        )
        values.extend(
            key
            for key, value in reporting.items()
            if _truthy(value) and _slug_for_value(key) is not None
        )
    values.extend(
        [
            metadata.get("reporting_cadence"),
            metadata.get("reporting_cadences"),
            metadata.get("cadence"),
            metadata.get("cadences"),
        ]
    )

    slugs: set[str] = set()
    for value in values:
        slugs.update(_cadence_slugs_from_value(value))
    return slugs


def _cadence_slugs_from_value(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        slug = _slug_for_value(value)
        return {slug} if slug is not None else set()
    if isinstance(value, dict):
        mapping_slugs: set[str] = set()
        for key, item in value.items():
            if key in {"cadence", "cadences", "frequency", "frequencies"}:
                mapping_slugs.update(_cadence_slugs_from_value(item))
            elif _truthy(item):
                slug = _slug_for_value(key)
                if slug is not None:
                    mapping_slugs.add(slug)
        return mapping_slugs
    if isinstance(value, (list, tuple, set)):
        sequence_slugs: set[str] = set()
        for item in value:
            sequence_slugs.update(_cadence_slugs_from_value(item))
        return sequence_slugs
    return set()


def _latest_report(company: Graph, definition: CadenceDefinition) -> ReportRun | None:
    return (
        ReportRun.objects.filter(company=company)
        .filter(_report_hint_query(definition))
        .order_by("-period_end", "-created_at")
        .first()
    )


def _latest_deliverable(
    company: Graph,
    definition: CadenceDefinition,
) -> ServiceDeliverable | None:
    return (
        ServiceDeliverable.objects.filter(
            company=company,
            visibility="customer",
            status__in=REPORT_DELIVERABLE_STATUSES,
        )
        .filter(_deliverable_hint_query(definition))
        .select_related("report_run")
        .order_by("-delivered_at", "-updated_at")
        .first()
    )


def _report_hint_query(definition: CadenceDefinition) -> Q:
    query = Q()
    for alias in definition.aliases:
        query |= Q(report_template_id__icontains=alias)
    return query


def _deliverable_hint_query(definition: CadenceDefinition) -> Q:
    query = Q(deliverable_type__icontains="report") | Q(title__icontains="report")
    for alias in definition.aliases:
        query |= Q(deliverable_type__icontains=alias) | Q(title__icontains=alias)
    return query


def _last_report_payload(report: ReportRun | None, *, today: date) -> dict[str, Any]:
    if report is None:
        return {
            "status": "unknown",
            "report_run_id": None,
            "period_start": None,
            "period_end": None,
            "days_since_period_end": None,
        }
    return {
        "status": "known",
        "report_run_id": str(report.id),
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "days_since_period_end": max((today - report.period_end).days, 0),
    }


def _deliverable_payload(deliverable: ServiceDeliverable | None) -> dict[str, Any]:
    if deliverable is None:
        return {
            "status": "unknown",
            "deliverable_id": None,
            "deliverable_type": None,
            "delivered_at": None,
        }
    return {
        "status": deliverable.status,
        "deliverable_id": str(deliverable.id),
        "deliverable_type": deliverable.deliverable_type,
        "delivered_at": deliverable.delivered_at.isoformat()
        if deliverable.delivered_at is not None
        else None,
    }


def _cadence_status(
    *,
    configured: bool,
    expected_frequency_days: int,
    last_report: dict[str, Any],
    latest_deliverable: dict[str, Any],
) -> str:
    days_since = last_report.get("days_since_period_end")
    delivered_report = latest_deliverable.get("status") in {"delivered", "accepted"}
    recent_report = isinstance(days_since, int) and days_since <= expected_frequency_days
    if configured and (recent_report or delivered_report):
        return "healthy"
    if configured:
        return "at_risk"
    if recent_report or delivered_report:
        return "monitor"
    return "not_configured"


def _summary(cadences: list[dict[str, Any]]) -> dict[str, Any]:
    configured = [item for item in cadences if item["configured"]]
    at_risk = [item for item in cadences if item["status"] == "at_risk"]
    healthy = [item for item in cadences if item["status"] == "healthy"]
    observed = [item for item in cadences if item["status"] == "monitor"]
    if at_risk:
        status = "attention"
    elif healthy:
        status = "healthy"
    elif observed or configured:
        status = "monitor"
    else:
        status = "unknown"
    return {
        "status": status,
        "cadences_configured": len(configured),
        "healthy": len(healthy),
        "at_risk": len(at_risk),
        "observed": len(observed),
    }


def _risks(cadences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for cadence in cadences:
        if cadence["configured"] and cadence["status"] == "at_risk":
            risks.append(
                {
                    "slug": f"{cadence['slug']}_report_stale",
                    "label": f"{cadence['label']} stale",
                    "severity": "medium",
                    "owner_department_slug": "analytics_performance",
                    "summary": "Configured recurring reporting is past its expected cadence.",
                }
            )
    return risks


def _message(*, status: str, configured: bool, expected_frequency_days: int) -> str:
    if status == "healthy":
        return "Recent client-facing reporting evidence is available."
    if status == "at_risk":
        return f"No report evidence is current within {expected_frequency_days} days."
    if configured:
        return "A reporting cadence is configured but needs current evidence."
    if status == "monitor":
        return "Recent reporting evidence exists without an explicit cadence."
    return "No explicit recurring reporting cadence is recorded."


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "no", "off", "none", "null", "0"}
    return bool(value)


def _slug_for_value(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    for definition in CADENCE_DEFINITIONS:
        if normalized == definition.slug or normalized in definition.aliases:
            return definition.slug
    return None
