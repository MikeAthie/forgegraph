"""Backend-owned Atlas agency account health snapshots."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from application.services.agency_account_catalog import (
    get_health_dimension_definition,
    list_health_dimension_definitions,
)
from application.services.agency_connector_readiness import build_connector_readiness
from application.services.agency_growth_signals import build_agency_growth_signals
from application.services.agency_onboarding import (
    build_virtual_onboarding_checklist,
    has_recent_report,
    has_reporting_cadence,
    in_review_deliverable_count,
    stale_approval_count,
)
from application.services.agency_reporting_cadence import build_recurring_reporting_status
from infrastructure.orm.models import (
    Graph,
    ReportRun,
    ServiceDeliverable,
    ServiceEngagement,
    WorkWhiteboard,
)


def build_agency_account_health_snapshot(
    company: Graph,
    *,
    include_growth_signals: bool = True,
) -> dict[str, Any]:
    connector_readiness = build_connector_readiness(company)
    recurring_reporting = build_recurring_reporting_status(company)
    growth_signals = (
        build_agency_growth_signals(company)
        if include_growth_signals
        else _empty_growth_signals()
    )
    onboarding = build_virtual_onboarding_checklist(
        company,
        connector_readiness=connector_readiness,
    )
    risks = _risks(
        company,
        connector_readiness,
        recurring_reporting=recurring_reporting,
        growth_signals=growth_signals,
    )
    opportunities = _opportunities(company, growth_signals=growth_signals)
    next_actions = _next_actions(connector_readiness, risks, onboarding["items"])
    dimensions = _health_dimensions(
        company,
        connector_readiness,
        onboarding,
        risks,
        recurring_reporting=recurring_reporting,
        growth_signals=growth_signals,
    )
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "profile": _profile(company, commercial=growth_signals["commercial"]),
        "health": {
            "score": _overall_score(dimensions),
            "status": _status_for_score(_overall_score(dimensions)),
            "dimensions": dimensions,
        },
        "onboarding_items": onboarding["items"],
        "connector_readiness": connector_readiness,
        "recurring_reporting": recurring_reporting,
        "growth_signals": growth_signals,
        "risks": risks,
        "opportunities": opportunities,
        "next_actions": next_actions,
    }


def _empty_growth_signals() -> dict[str, Any]:
    return {
        "commercial": {"status": "unknown"},
        "scope": {"status": "unknown", "warnings": []},
        "retention": {"status": "unknown", "factors": []},
        "expansion": {"status": "unknown", "opportunities": []},
    }


def _profile(company: Graph, *, commercial: dict[str, Any]) -> dict[str, Any]:
    latest_engagement = _latest_engagement(company)
    latest_whiteboard = _latest_whiteboard(company)
    return {
        "company_id": str(company.id),
        "name": company.name,
        "description": company.description,
        "client_stage": _client_stage(latest_engagement, latest_whiteboard),
        "active_service_engagement": _engagement_profile(latest_engagement),
        "commercial": commercial,
    }


def _health_dimensions(
    company: Graph,
    connector_readiness: dict[str, Any],
    onboarding: dict[str, Any],
    risks: list[dict[str, Any]],
    recurring_reporting: dict[str, Any],
    growth_signals: dict[str, Any],
) -> list[dict[str, Any]]:
    scores = {
        "onboarding": _onboarding_score(onboarding["summary"]),
        "connector_readiness": _connector_score(connector_readiness["summary"]),
        "delivery": _delivery_score(company),
        "reporting": _reporting_score(company, recurring_reporting),
        "approvals": _approval_score(company),
        "commercial": _commercial_score(growth_signals),
    }
    risk_slugs = {item["slug"] for item in risks}
    return [
        _dimension_payload(definition.slug, scores[definition.slug], risk_slugs)
        for definition in list_health_dimension_definitions()
    ]


def _dimension_payload(slug: str, score: int, risk_slugs: set[str]) -> dict[str, Any]:
    definition = get_health_dimension_definition(slug)
    if definition is None:
        raise ValueError(f"Unknown health dimension: {slug}")
    status = "unknown" if slug == "commercial" and score == 50 else _status_for_score(score)
    return {
        "slug": definition.slug,
        "label": definition.label,
        "score": score,
        "status": status,
        "weight": definition.weight,
        "owner_department_slug": definition.owner_department_slug,
        "summary": _dimension_summary(slug, score, risk_slugs),
    }


def _risks(
    company: Graph,
    connector_readiness: dict[str, Any],
    *,
    recurring_reporting: dict[str, Any],
    growth_signals: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    missing = _missing_required_connectors(connector_readiness)
    if missing:
        risks.append(
            {
                "slug": "missing_required_connectors",
                "label": "Required connectors missing",
                "severity": "high",
                "owner_department_slug": "channel_execution",
                "summary": f"{len(missing)} required connector(s) are not ready.",
            }
        )
    if stale_approval_count(company):
        risks.append(
            {
                "slug": "stale_client_approval",
                "label": "Stale client approval",
                "severity": "high",
                "owner_department_slug": "client_approval_ops",
                "summary": "A customer-facing deliverable has been in review for more than seven days.",
            }
        )
    reporting_summary = recurring_reporting.get("summary")
    configured_cadences = (
        int(reporting_summary.get("cadences_configured") or 0)
        if isinstance(reporting_summary, dict)
        else 0
    )
    if (
        not has_recent_report(company)
        and not has_reporting_cadence(company)
        and not configured_cadences
    ):
        risks.append(
            {
                "slug": "reporting_cadence_missing",
                "label": "Reporting cadence missing",
                "severity": "medium",
                "owner_department_slug": "analytics_performance",
                "summary": "No recent report or reporting cadence is configured.",
            }
        )
    risks.extend(_recurring_reporting_risks(recurring_reporting))
    risks.extend(_growth_signal_risks(growth_signals))
    return _dedupe_by_slug(risks)


def _opportunities(company: Graph, *, growth_signals: dict[str, Any]) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    latest_report = _latest_report(company)
    if latest_report is not None:
        opportunities.append(
            {
                "slug": "recent_performance_report",
                "label": "Recent performance report",
                "priority": "medium",
                "owner_department_slug": "analytics_performance",
                "summary": "Use the recent report as client-facing proof of value.",
            }
        )
    for opportunity in growth_signals.get("expansion", {}).get("opportunities", [])[:3]:
        opportunities.append(
            {
                "slug": f"expansion_{opportunity['opportunity_id']}",
                "label": opportunity["title"],
                "priority": "medium",
                "owner_department_slug": "strategy_research",
                "summary": opportunity["summary"] or "Review qualified expansion opportunity.",
            }
        )
    return opportunities


def _next_actions(
    connector_readiness: dict[str, Any],
    risks: list[dict[str, Any]],
    onboarding_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = [_connector_action(item) for item in _missing_required_connectors(connector_readiness)]
    if any(risk["slug"] == "stale_client_approval" for risk in risks):
        actions.append(
            {
                "slug": "resolve_stale_client_approval",
                "label": "Resolve stale client approval",
                "priority": "high",
                "owner_department_slug": "client_approval_ops",
                "reason": "Customer-facing approval is blocking delivery health.",
            }
        )
    for item in onboarding_items:
        if item["status"] in {"blocked", "not_started"} and item["slug"] != "connector_setup":
            actions.append(_onboarding_action(item))
    return _dedupe_actions(actions)


def _missing_required_connectors(connector_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    connectors = connector_readiness.get("connectors")
    if not isinstance(connectors, list):
        return []
    return [
        item
        for item in connectors
        if isinstance(item, dict) and item.get("required") and item.get("status") != "ready"
    ]


def _connector_action(connector: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": f"configure_{connector['slug']}",
        "label": f"Configure {connector['label']}",
        "priority": "high",
        "owner_department_slug": connector["owner_department_slug"],
        "reason": connector["message"],
    }


def _onboarding_action(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": f"complete_{item['slug']}",
        "label": f"Complete {item['label']}",
        "priority": "medium" if item["status"] == "not_started" else "high",
        "owner_department_slug": item["owner_department_slug"],
        "reason": item["message"],
    }


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for action in actions:
        deduped.setdefault(str(action["slug"]), action)
    return list(deduped.values())


def _onboarding_score(summary: dict[str, int]) -> int:
    total = max(int(summary.get("total") or 0), 1)
    completed = int(summary.get("completed") or 0)
    in_progress = int(summary.get("in_progress") or 0)
    blocked = int(summary.get("blocked") or 0)
    return max(0, min(100, round(((completed + (in_progress * 0.5)) / total * 100) - (blocked * 10))))


def _connector_score(summary: dict[str, int]) -> int:
    required = max(int(summary.get("required") or 0), 1)
    ready = int(summary.get("ready") or 0)
    degraded = int(summary.get("degraded") or 0)
    disabled = int(summary.get("disabled") or 0)
    return max(0, min(100, round((ready / required * 100) - ((degraded + disabled) * 15))))


def _delivery_score(company: Graph) -> int:
    if ServiceDeliverable.objects.filter(company=company, status__in={"ready", "delivered", "accepted"}).exists():
        return 80
    if ServiceEngagement.objects.filter(company=company, status__in={"in_progress", "in_review", "delivered"}).exists():
        return 60
    if WorkWhiteboard.objects.filter(company=company).exists():
        return 55
    return 35


def _reporting_score(company: Graph, recurring_reporting: dict[str, Any]) -> int:
    if has_recent_report(company):
        return 85
    summary = recurring_reporting.get("summary")
    status = summary.get("status") if isinstance(summary, dict) else None
    if status == "healthy":
        return 85
    if status == "monitor":
        return 60
    if status == "attention":
        return 45
    if has_reporting_cadence(company):
        return 60
    return 30


def _commercial_score(growth_signals: dict[str, Any]) -> int:
    scope = growth_signals.get("scope")
    retention = growth_signals.get("retention")
    expansion = growth_signals.get("expansion")
    if isinstance(scope, dict) and scope.get("status") == "warning":
        return 45
    if isinstance(retention, dict) and retention.get("status") == "risk":
        return 45
    if isinstance(expansion, dict) and expansion.get("status") == "opportunity":
        return 65
    return 50


def _approval_score(company: Graph) -> int:
    if stale_approval_count(company):
        return 30
    if in_review_deliverable_count(company):
        return 60
    return 75


def _overall_score(dimensions: list[dict[str, Any]]) -> int:
    total_weight = sum(int(item["weight"]) for item in dimensions) or 1
    weighted = sum(int(item["score"]) * int(item["weight"]) for item in dimensions)
    return round(weighted / total_weight)


def _status_for_score(score: int) -> str:
    if score >= 80:
        return "healthy"
    if score >= 60:
        return "monitor"
    if score >= 40:
        return "attention"
    return "blocked"


def _dimension_summary(slug: str, score: int, risk_slugs: set[str]) -> str:
    if slug == "connector_readiness" and "missing_required_connectors" in risk_slugs:
        return "Required connector gaps are lowering account health."
    if slug == "approvals" and "stale_client_approval" in risk_slugs:
        return "Client approval latency is blocking delivery."
    if slug == "reporting" and score >= 80:
        return "Recent reporting evidence is available."
    if slug == "commercial":
        return "Commercial values are unknown until explicit package economics are recorded."
    return "Dimension is derived from backend-owned account state."


def _latest_engagement(company: Graph) -> ServiceEngagement | None:
    return ServiceEngagement.objects.filter(company=company).order_by("-updated_at").first()


def _latest_whiteboard(company: Graph) -> WorkWhiteboard | None:
    return WorkWhiteboard.objects.filter(company=company).order_by("-updated_at").first()


def _latest_report(company: Graph) -> ReportRun | None:
    return ReportRun.objects.filter(company=company).order_by("-period_end", "-created_at").first()


def _client_stage(
    engagement: ServiceEngagement | None,
    whiteboard: WorkWhiteboard | None,
) -> str:
    if engagement is not None:
        return engagement.customer_status or engagement.status
    if whiteboard is not None:
        return whiteboard.status
    return "unknown"


def _engagement_profile(engagement: ServiceEngagement | None) -> dict[str, Any] | None:
    if engagement is None:
        return None
    return {
        "service_slug": engagement.catalog_item.slug,
        "service_title": engagement.catalog_item.title,
        "status": engagement.status,
        "customer_status": engagement.customer_status,
    }


def _recurring_reporting_risks(recurring_reporting: dict[str, Any]) -> list[dict[str, Any]]:
    risks = recurring_reporting.get("risks")
    return [risk for risk in risks if isinstance(risk, dict)] if isinstance(risks, list) else []


def _growth_signal_risks(growth_signals: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    scope = growth_signals.get("scope")
    if isinstance(scope, dict):
        warnings = scope.get("warnings")
        if isinstance(warnings, list):
            for warning in warnings:
                if isinstance(warning, dict):
                    risks.append(
                        {
                            "slug": warning["slug"],
                            "label": "Scope creep warning",
                            "severity": warning["severity"],
                            "owner_department_slug": "strategy_research",
                            "summary": warning["summary"],
                        }
                    )
    retention = growth_signals.get("retention")
    if isinstance(retention, dict) and retention.get("status") == "risk":
        risks.append(
            {
                "slug": "retention_risk_signal",
                "label": "Retention risk signal",
                "severity": "medium",
                "owner_department_slug": "strategy_research",
                "summary": "A backend-owned company signal indicates retention risk.",
            }
        )
    return risks


def _dedupe_by_slug(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        deduped.setdefault(str(item["slug"]), item)
    return list(deduped.values())
