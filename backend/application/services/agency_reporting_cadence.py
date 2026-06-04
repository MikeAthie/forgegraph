"""Backend-owned recurring reporting cadence read model."""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from application.services.atlas_launch_attempts import launch_attempt_payload
from application.services.audit_log import record_audit_log
from application.services.domain_events import record_domain_event
from application.services.redaction import redact_payload
from application.services.service_engagements import service_deliverable_payload
from infrastructure.orm.models import (
    AtlasLaunchAttempt,
    AtlasReportingCadencePlan,
    AtlasReportingCadenceRun,
    Graph,
    ReportRun,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)


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
PROOF_REPORT_TEMPLATE_PREFIX = "atlas.proof_of_value"
_OMIT = object()
_SECRET_KEY_TOKENS = (
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "confidential",
    "cookie",
    "credential",
    "internal",
    "password",
    "private",
    "secret",
    "session",
    "token",
)
_SECRET_TEXT_TOKENS = (
    "access_token",
    "api-key",
    "api_key",
    "apikey",
    "authorization:",
    "authorization=",
    "bearer ",
    "cookie:",
    "cookie=",
    "credential=",
    "operator-only",
    "password=",
    "private",
    "secret",
    "secret=",
    "session:",
    "session=",
    "sk_live",
    "token=",
)


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


def reporting_cadence_due_status(
    plan: AtlasReportingCadencePlan | None,
    *,
    today: date | None = None,
) -> str:
    """Return due state from backend-owned plan dates."""

    if plan is None:
        return "not_configured"
    if plan.status != "active":
        return plan.status
    current = today or timezone.now().date()
    if plan.next_due_on < current:
        return "overdue"
    if plan.next_due_on == current:
        return "due"
    return "upcoming"


def reporting_cadence_plan_payload(plan: AtlasReportingCadencePlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "organization_id": str(plan.organization_id),
        "company_id": str(plan.company_id),
        "engagement_id": str(plan.engagement_id) if plan.engagement_id else None,
        "cadence_type": plan.cadence_type,
        "status": plan.status,
        "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
        "next_due_on": plan.next_due_on.isoformat(),
        "due_status": reporting_cadence_due_status(plan),
        "last_run_id": str(plan.last_run_id) if plan.last_run_id else None,
        "proof_template_id": plan.proof_template_id,
        "metadata": cast(dict[str, Any], _client_safe_payload(plan.metadata_json or {})),
        "created_by_id": str(plan.created_by_id) if plan.created_by_id else None,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


def reporting_cadence_run_payload(
    run: AtlasReportingCadenceRun,
    *,
    include_snapshot: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(run.id),
        "organization_id": str(run.organization_id),
        "company_id": str(run.company_id),
        "plan_id": str(run.plan_id),
        "report_run_id": str(run.report_run_id) if run.report_run_id else None,
        "cadence_type": run.cadence_type,
        "status": run.status,
        "idempotency_key": run.idempotency_key,
        "source_key": run.source_key,
        "due_on": run.due_on.isoformat(),
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "source_refs": list(run.source_refs_json or []),
        "created_by_id": str(run.created_by_id) if run.created_by_id else None,
        "created_at": run.created_at.isoformat(),
    }
    if include_snapshot:
        payload["proof_snapshot"] = cast(
            dict[str, Any],
            _client_safe_payload(run.proof_snapshot_json or {}),
        )
    return payload


def upsert_reporting_cadence_plan(
    *,
    company: Graph,
    cadence_type: str,
    actor: User | None,
    next_due_on: date | None = None,
    engagement: ServiceEngagement | None = None,
    status: str = "active",
    anchor_date: date | None = None,
    metadata: dict[str, Any] | None = None,
) -> AtlasReportingCadencePlan:
    """Create or update the backend-owned plan for one company cadence."""

    definition = _cadence_definition(cadence_type)
    organization = _organization_for_company(company)
    if engagement is not None and engagement.company_id != company.id:
        msg = "Reporting cadence engagement must belong to the company."
        raise ValueError(msg)
    if status not in {"active", "paused", "archived"}:
        msg = "Reporting cadence status is not supported."
        raise ValueError(msg)

    due_on = next_due_on or timezone.now().date()
    safe_metadata = cast(dict[str, Any], _client_safe_payload(metadata or {}))
    with transaction.atomic():
        plan, created = AtlasReportingCadencePlan.objects.select_for_update().get_or_create(
            company=company,
            cadence_type=definition.slug,
            defaults={
                "organization": organization,
                "engagement": engagement,
                "status": status,
                "anchor_date": anchor_date,
                "next_due_on": due_on,
                "metadata_json": safe_metadata,
                "created_by": actor,
            },
        )
        if not created:
            plan.organization = organization
            plan.engagement = engagement if engagement is not None else plan.engagement
            plan.status = status
            plan.next_due_on = due_on
            if anchor_date is not None:
                plan.anchor_date = anchor_date
            if metadata is not None:
                plan.metadata_json = safe_metadata
            plan.save(
                update_fields=[
                    "organization",
                    "engagement",
                    "status",
                    "anchor_date",
                    "next_due_on",
                    "metadata_json",
                    "updated_at",
                ]
            )
        _record_plan_audit(plan=plan, actor=actor, created=created)
        _record_plan_domain_event(plan=plan, created=created)
    return plan


def generate_reporting_cadence_run(
    *,
    plan: AtlasReportingCadencePlan,
    actor: User | None,
    idempotency_key: str,
    period_start: date | None = None,
    period_end: date | None = None,
) -> AtlasReportingCadenceRun:
    """Generate one durable client-safe proof-of-value snapshot for a cadence plan."""

    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        msg = "idempotency_key is required to generate a reporting cadence run."
        raise ValueError(msg)

    with transaction.atomic():
        locked_plan = (
            AtlasReportingCadencePlan.objects.select_for_update()
            .select_related("company", "organization")
            .get(id=plan.id)
        )
        existing = AtlasReportingCadenceRun.objects.filter(
            plan=locked_plan,
            idempotency_key=normalized_key,
        ).first()
        if existing is not None:
            return existing

        due_on = locked_plan.next_due_on
        existing_due_run = AtlasReportingCadenceRun.objects.filter(
            plan=locked_plan,
            due_on=due_on,
        ).first()
        if existing_due_run is not None:
            return existing_due_run

        start, end = _period_bounds(
            cadence_type=locked_plan.cadence_type,
            due_on=due_on,
            period_start=period_start,
            period_end=period_end,
        )
        snapshot = build_proof_of_value_snapshot(
            company=locked_plan.company,
            plan=locked_plan,
            due_on=due_on,
            period_start=start,
            period_end=end,
        )
        source_refs = _source_refs_from_snapshot(snapshot)
        report = ReportRun.objects.create(
            organization=locked_plan.organization,
            company=locked_plan.company,
            report_template_id=f"{PROOF_REPORT_TEMPLATE_PREFIX}.{locked_plan.cadence_type}",
            period_start=start,
            period_end=end,
            generated_sections_json={"proof_of_value": snapshot},
            source_refs_json=source_refs,
            created_by=actor,
        )
        run = AtlasReportingCadenceRun.objects.create(
            organization=locked_plan.organization,
            company=locked_plan.company,
            plan=locked_plan,
            report_run=report,
            cadence_type=locked_plan.cadence_type,
            status="generated",
            idempotency_key=normalized_key,
            source_key=f"atlas-reporting:{locked_plan.id}:{due_on.isoformat()}",
            due_on=due_on,
            period_start=start,
            period_end=end,
            proof_snapshot_json=snapshot,
            source_refs_json=source_refs,
            created_by=actor,
        )
        locked_plan.last_run = run
        locked_plan.next_due_on = _advance_due_on(
            locked_plan.next_due_on,
            locked_plan.cadence_type,
        )
        locked_plan.save(update_fields=["last_run", "next_due_on", "updated_at"])
        _record_run_audit(run=run, actor=actor)
        _record_run_domain_event(run)
    return run


def build_proof_of_value_snapshot(
    *,
    company: Graph,
    plan: AtlasReportingCadencePlan,
    due_on: date,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    """Build the backend-owned, client-safe proof-of-value report payload."""

    from application.services.agency_account_health import build_agency_account_health_snapshot
    from application.services.agency_growth_signals import build_agency_growth_signals

    latest_deliverables = _latest_customer_deliverables(company)
    latest_reports = _latest_reports(company)
    latest_launch_attempt = _latest_launch_attempt(company)
    account_health = build_agency_account_health_snapshot(company)
    growth_signals = build_agency_growth_signals(company)
    snapshot = {
        "schema_version": "atlas_proof_of_value_report_v1",
        "company": {
            "id": str(company.id),
            "name": company.name,
        },
        "cadence": {
            "plan_id": str(plan.id),
            "type": plan.cadence_type,
            "label": _cadence_definition(plan.cadence_type).label,
            "due_on": due_on.isoformat(),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "due_status": reporting_cadence_due_status(plan),
        },
        "inputs_present": {
            "deliverables": bool(latest_deliverables),
            "reports": bool(latest_reports),
            "health": True,
            "launch": latest_launch_attempt is not None,
            "growth_signals": True,
        },
        "summary": {
            "health_status": account_health.get("health", {}).get("status"),
            "health_score": account_health.get("health", {}).get("score"),
            "latest_report_count": len(latest_reports),
            "latest_deliverable_count": len(latest_deliverables),
        },
        "proof_points": _proof_points(
            latest_deliverables=latest_deliverables,
            latest_reports=latest_reports,
            launch_attempt=latest_launch_attempt,
            growth_signals=growth_signals,
        ),
        "account_health": account_health,
        "recurring_reporting": build_recurring_reporting_status(company),
        "growth_signals": growth_signals,
        "latest_deliverables": latest_deliverables,
        "latest_reports": latest_reports,
        "launch": {
            "latest_attempt": launch_attempt_payload(latest_launch_attempt)
            if latest_launch_attempt is not None
            else None
        },
        "generated_at": timezone.now().isoformat(),
    }
    return cast(dict[str, Any], _client_safe_payload(snapshot))


def _cadence_payload(
    *,
    company: Graph,
    definition: CadenceDefinition,
    configured_slugs: set[str],
    today: date,
) -> dict[str, Any]:
    plan = _latest_plan(company, definition)
    configured = definition.slug in configured_slugs or plan is not None
    report = _latest_report(company, definition)
    deliverable = _latest_deliverable(company, definition)
    last_report = _last_report_payload(report, today=today)
    latest_deliverable = _deliverable_payload(deliverable)
    due_status = reporting_cadence_due_status(plan, today=today) if plan else "not_configured"
    status = _cadence_status(
        configured=configured,
        expected_frequency_days=definition.expected_frequency_days,
        last_report=last_report,
        latest_deliverable=latest_deliverable,
        due_status=due_status,
    )
    return {
        "slug": definition.slug,
        "label": definition.label,
        "configured": configured,
        "status": status,
        "plan_id": str(plan.id) if plan else None,
        "next_due_on": plan.next_due_on.isoformat() if plan else None,
        "due_status": due_status,
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
    configured: set[str] = set(
        AtlasReportingCadencePlan.objects.filter(company=company)
        .exclude(status="archived")
        .values_list("cadence_type", flat=True)
    )
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
        slugs: set[str] = set()
        for key, item in value.items():
            if key in {"cadence", "cadences", "frequency", "frequencies"}:
                slugs.update(_cadence_slugs_from_value(item))
            elif _truthy(item):
                slug = _slug_for_value(key)
                if slug is not None:
                    slugs.add(slug)
        return slugs
    if isinstance(value, (list, tuple, set)):
        slugs: set[str] = set()
        for item in value:
            slugs.update(_cadence_slugs_from_value(item))
        return slugs
    return set()


def _latest_report(company: Graph, definition: CadenceDefinition) -> ReportRun | None:
    return (
        ReportRun.objects.filter(company=company)
        .filter(_report_hint_query(definition))
        .order_by("-period_end", "-created_at")
        .first()
    )


def _latest_plan(
    company: Graph,
    definition: CadenceDefinition,
) -> AtlasReportingCadencePlan | None:
    return (
        AtlasReportingCadencePlan.objects.filter(
            company=company,
            cadence_type=definition.slug,
        )
        .exclude(status="archived")
        .order_by("-updated_at")
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
    due_status: str,
) -> str:
    days_since = last_report.get("days_since_period_end")
    delivered_report = latest_deliverable.get("status") in {"delivered", "accepted"}
    recent_report = isinstance(days_since, int) and days_since <= expected_frequency_days
    if configured and (recent_report or delivered_report):
        return "healthy"
    if due_status in {"paused", "archived"}:
        return due_status
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


def _cadence_definition(cadence_type: str) -> CadenceDefinition:
    slug = _slug_for_value(cadence_type)
    for definition in CADENCE_DEFINITIONS:
        if definition.slug == slug:
            return definition
    msg = "Reporting cadence type is not supported."
    raise ValueError(msg)


def _organization_for_company(company: Graph) -> Any:
    if company.organization_id is None or company.organization is None:
        msg = "Reporting cadence plans require a company organization."
        raise ValueError(msg)
    return company.organization


def _period_bounds(
    *,
    cadence_type: str,
    due_on: date,
    period_start: date | None,
    period_end: date | None,
) -> tuple[date, date]:
    end = period_end or due_on
    if period_start is not None:
        return period_start, end
    if cadence_type == "weekly":
        return end - timedelta(days=6), end
    if cadence_type == "monthly":
        previous = _add_months(end, -1)
        return previous + timedelta(days=1), end
    if cadence_type == "qbr":
        previous = _add_months(end, -3)
        return previous + timedelta(days=1), end
    return end, end


def _advance_due_on(current: date, cadence_type: str) -> date:
    if cadence_type == "weekly":
        return current + timedelta(days=7)
    if cadence_type == "monthly":
        return _add_months(current, 1)
    if cadence_type == "qbr":
        return _add_months(current, 3)
    return current


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _latest_customer_deliverables(company: Graph) -> list[dict[str, Any]]:
    deliverables = (
        ServiceDeliverable.objects.filter(company=company, visibility="customer")
        .exclude(status__in={"draft", "archived"})
        .select_related("artifact", "report_run", "engagement", "engagement__catalog_item")
        .order_by("-delivered_at", "-updated_at")[:5]
    )
    payloads: list[dict[str, Any]] = []
    for deliverable in deliverables:
        payload = service_deliverable_payload(deliverable)
        payloads.append(
            {
                "deliverable_id": payload["id"],
                "title": payload["title"],
                "deliverable_type": payload["deliverable_type"],
                "status": payload["status"],
                "client_visible_status": payload["client_visible_status"],
                "report_run_id": payload["report_run_id"],
                "summary": payload["summary"],
                "delivered_at": payload["delivered_at"],
                "metadata": payload["metadata"],
            }
        )
    return cast(list[dict[str, Any]], _client_safe_payload(payloads))


def _latest_reports(company: Graph) -> list[dict[str, Any]]:
    reports = ReportRun.objects.filter(company=company).order_by("-period_end", "-created_at")[:5]
    payloads = [
        {
            "report_run_id": str(report.id),
            "report_template_id": report.report_template_id,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "section_keys": sorted(str(key) for key in (report.generated_sections_json or {})),
            "created_at": report.created_at.isoformat(),
        }
        for report in reports
    ]
    return cast(list[dict[str, Any]], _client_safe_payload(payloads))


def _latest_launch_attempt(company: Graph) -> AtlasLaunchAttempt | None:
    return (
        AtlasLaunchAttempt.objects.filter(company=company)
        .select_related("whiteboard", "receipt_deliverable")
        .order_by("-last_checkpoint_at", "-updated_at", "-created_at")
        .first()
    )


def _proof_points(
    *,
    latest_deliverables: list[dict[str, Any]],
    latest_reports: list[dict[str, Any]],
    launch_attempt: AtlasLaunchAttempt | None,
    growth_signals: dict[str, Any],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    if latest_deliverables:
        points.append(
            {
                "slug": "client_visible_delivery",
                "label": "Client-visible delivery",
                "summary": f"{len(latest_deliverables)} recent customer-facing deliverable(s).",
            }
        )
    if latest_reports:
        points.append(
            {
                "slug": "recent_reporting_evidence",
                "label": "Recent reporting evidence",
                "summary": f"{len(latest_reports)} recent backend report run(s).",
            }
        )
    if launch_attempt is not None:
        points.append(
            {
                "slug": "launch_readiness",
                "label": "Launch readiness",
                "summary": f"Latest Atlas launch attempt is {launch_attempt.status}.",
            }
        )
    profit = growth_signals.get("profit")
    if isinstance(profit, dict):
        points.append(
            {
                "slug": "profit_signal",
                "label": "Profit signal",
                "summary": str(profit.get("summary") or "Profit signal captured."),
            }
        )
    return cast(list[dict[str, Any]], _client_safe_payload(points))


def _source_refs_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for deliverable in snapshot.get("latest_deliverables", []):
        if isinstance(deliverable, dict) and deliverable.get("deliverable_id"):
            refs.append(
                {
                    "type": "service_deliverable",
                    "id": str(deliverable["deliverable_id"]),
                }
            )
    for report in snapshot.get("latest_reports", []):
        if isinstance(report, dict) and report.get("report_run_id"):
            refs.append({"type": "report_run", "id": str(report["report_run_id"])})
    launch = snapshot.get("launch")
    latest_attempt = launch.get("latest_attempt") if isinstance(launch, dict) else None
    if isinstance(latest_attempt, dict) and latest_attempt.get("id"):
        refs.append({"type": "atlas_launch_attempt", "id": str(latest_attempt["id"])})
    return refs


def _record_plan_audit(
    *,
    plan: AtlasReportingCadencePlan,
    actor: User | None,
    created: bool,
) -> None:
    record_audit_log(
        actor=actor,
        tenant_id=str(plan.organization_id),
        action="atlas_reporting_cadence.plan_upserted",
        resource_type="atlas_reporting_cadence_plan",
        resource_id=str(plan.id),
        metadata={
            "company_id": str(plan.company_id),
            "cadence_type": plan.cadence_type,
            "next_due_on": plan.next_due_on.isoformat(),
            "created": created,
        },
    )


def _record_plan_domain_event(
    *,
    plan: AtlasReportingCadencePlan,
    created: bool,
) -> None:
    payload = reporting_cadence_plan_payload(plan)
    payload["created"] = created
    record_domain_event(
        organization=plan.organization,
        aggregate_type="atlas_reporting_cadence_plan",
        aggregate_id=plan.id,
        event_type="atlas.reporting_cadence_plan.upserted",
        idempotency_key=f"atlas-reporting-cadence-plan:{plan.id}:{plan.updated_at.isoformat()}",
        payload=payload,
        outbox_topic="forgegraph.domain.events.v1",
        outbox_payload=payload,
        outbox_visibility="organization",
        outbox_company=plan.company,
    )


def _record_run_audit(*, run: AtlasReportingCadenceRun, actor: User | None) -> None:
    record_audit_log(
        actor=actor,
        tenant_id=str(run.organization_id),
        action="atlas_reporting_cadence.run_generated",
        resource_type="atlas_reporting_cadence_run",
        resource_id=str(run.id),
        metadata={
            "company_id": str(run.company_id),
            "plan_id": str(run.plan_id),
            "cadence_type": run.cadence_type,
            "report_run_id": str(run.report_run_id) if run.report_run_id else None,
            "period_start": run.period_start.isoformat(),
            "period_end": run.period_end.isoformat(),
        },
    )


def _record_run_domain_event(run: AtlasReportingCadenceRun) -> None:
    payload = reporting_cadence_run_payload(run, include_snapshot=False)
    record_domain_event(
        organization=run.organization,
        aggregate_type="atlas_reporting_cadence_run",
        aggregate_id=run.id,
        event_type="atlas.reporting_cadence_run.generated",
        idempotency_key=f"atlas-reporting-cadence-run:{run.id}",
        payload=payload,
        outbox_topic="forgegraph.domain.events.v1",
        outbox_payload=payload,
        outbox_visibility="customer",
        outbox_company=run.company,
    )


def _client_safe_payload(value: Any) -> Any:
    redacted = redact_payload(value)
    cleaned = _drop_sensitive(redacted)
    if cleaned is _OMIT:
        return {}
    return json.loads(json.dumps(cleaned, cls=DjangoJSONEncoder))


def _drop_sensitive(value: Any, *, field_name: str = "") -> Any:
    if _is_sensitive_key(field_name):
        return _OMIT
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                continue
            cleaned = _drop_sensitive(item, field_name=key_text)
            if cleaned is not _OMIT:
                result[key_text] = cleaned
        return result
    if isinstance(value, list):
        cleaned_items = [_drop_sensitive(item, field_name=field_name) for item in value]
        return [item for item in cleaned_items if item is not _OMIT]
    if isinstance(value, tuple):
        cleaned_items = [_drop_sensitive(item, field_name=field_name) for item in value]
        return [item for item in cleaned_items if item is not _OMIT]
    if isinstance(value, str) and _is_sensitive_text(value):
        return _OMIT
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(token in normalized for token in _SECRET_KEY_TOKENS)


def _is_sensitive_text(value: str) -> bool:
    normalized = value.lower()
    return any(token in normalized for token in _SECRET_TEXT_TOKENS)
