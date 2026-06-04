"""Backend-owned agency retention, expansion, scope, and profit signals."""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.utils import timezone

from application.services.agency_connector_readiness import build_connector_readiness
from application.services.agency_reporting_cadence import build_recurring_reporting_status
from application.services.service_engagement_snapshots import latest_business_snapshot_for_company
from infrastructure.orm.models import (
    AtlasLaunchAttempt,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    ServiceDeliverable,
    ServiceEngagement,
    ServiceEngagementBusinessSnapshot,
    TaskRoutingRecord,
)

OPEN_OPPORTUNITY_STATUSES = {"new", "qualified", "follow_up", "reserved"}
OPEN_SIGNAL_STATUSES = {"new", "qualified"}
STALE_APPROVAL_DAYS = 7
LOW_MARGIN_THRESHOLD = 0.20
HEALTHY_MARGIN_THRESHOLD = 0.35


def build_agency_growth_signals(company: Graph) -> dict[str, Any]:
    """Return client-safe commercial and growth signals from backend records."""

    snapshot = latest_business_snapshot_for_company(company)
    commercial = (
        _commercial_from_snapshot(snapshot)
        if snapshot is not None
        else _commercial_from_engagement_metadata(company)
    )
    profit = (
        _profit_from_snapshot(snapshot)
        if snapshot is not None
        else _profit_from_commercial(commercial)
    )
    expansion = _expansion(company)
    scope = _snapshot_scope(snapshot) if snapshot is not None else _scope(company)
    retention = _retention(company, profit=profit)
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "status": _summary_status(expansion=expansion, scope=scope, retention=retention),
            "open_expansion_opportunities": len(expansion["opportunities"]),
            "scope_warnings": len(scope["warnings"]),
            "retention_risks": len(retention["factors"]),
        },
        "commercial": commercial,
        "retention": retention,
        "expansion": expansion,
        "scope": scope,
        "profit": profit,
    }


def _unknown_commercial() -> dict[str, Any]:
    return {
        "monthly_retainer": _unknown_money(),
        "contract_value": _unknown_money(),
        "gross_margin": {"status": "unknown", "value": None},
    }


def _unknown_profit() -> dict[str, Any]:
    return {
        "status": "unknown",
        "gross_margin": {"status": "unknown", "value": None},
        "summary": "Profit cannot be derived until explicit margin inputs are recorded.",
    }


def _unknown_money() -> dict[str, Any]:
    return {"status": "unknown", "amount": None, "currency": None}


def _commercial_from_snapshot(snapshot: ServiceEngagementBusinessSnapshot) -> dict[str, Any]:
    snapshot_json = snapshot.snapshot_json if isinstance(snapshot.snapshot_json, dict) else {}
    economics = _mapping(snapshot_json.get("economics"))
    profitability = _mapping(snapshot_json.get("profitability"))
    revenue = _mapping(economics.get("revenue"))
    amount = revenue.get("amount") or str(snapshot.revenue_amount)
    currency = revenue.get("currency") or snapshot.currency
    gross_margin_percent = profitability.get("gross_margin_percent") or (
        str(snapshot.gross_margin_percent)
        if snapshot.gross_margin_percent is not None
        else None
    )
    if not amount:
        return _unknown_commercial()
    return {
        "monthly_retainer": {
            "status": "known",
            "amount": str(amount),
            "currency": str(currency),
        },
        "contract_value": {
            "status": "known",
            "amount": str(amount),
            "currency": str(currency),
        },
        "gross_margin": {
            "status": "known" if gross_margin_percent is not None else "unknown",
            "value": str(gross_margin_percent) if gross_margin_percent is not None else None,
            "band": snapshot.profitability_band,
        },
    }


def _profit_from_snapshot(snapshot: ServiceEngagementBusinessSnapshot) -> dict[str, Any]:
    snapshot_json = snapshot.snapshot_json if isinstance(snapshot.snapshot_json, dict) else {}
    profitability = _mapping(snapshot_json.get("profitability"))
    status = "known"
    if snapshot.profitability_band in {"thin", "break_even", "loss"}:
        status = "low_margin"
    return {
        "status": status,
        "profitability_band": snapshot.profitability_band,
        "gross_margin": {
            "amount": profitability.get("gross_margin_amount")
            or str(snapshot.gross_margin_amount),
            "percent": profitability.get("gross_margin_percent")
            or (
                str(snapshot.gross_margin_percent)
                if snapshot.gross_margin_percent is not None
                else None
            ),
        },
        "summary": "Profitability is derived from the latest backend-owned engagement snapshot.",
    }


def _snapshot_scope(snapshot: ServiceEngagementBusinessSnapshot) -> dict[str, Any]:
    snapshot_json = snapshot.snapshot_json if isinstance(snapshot.snapshot_json, dict) else {}
    scope = _mapping(snapshot_json.get("scope"))
    warnings: list[dict[str, Any]] = []
    if snapshot.scope_status in {"at_risk", "over_limit"}:
        warnings.append(
            {
                "slug": "scope_utilization_over_plan",
                "severity": "high" if snapshot.scope_status == "over_limit" else "medium",
                "requested_deliverables": snapshot.scope_used_units,
                "package_limit": snapshot.scope_included_units,
                "summary": "Scope utilization is at or above the recorded package limit.",
            }
        )
    return {
        "status": "warning"
        if snapshot.scope_status in {"at_risk", "over_limit"}
        else "ok"
        if snapshot.scope_status == "on_track"
        else "unknown",
        "warnings": warnings,
        "unit": snapshot.scope_unit,
        "included_units": snapshot.scope_included_units,
        "used_units": snapshot.scope_used_units,
        "overage_units": snapshot.scope_overage_units,
        "utilization_percent": scope.get("utilization_percent"),
        "source_snapshot_id": str(snapshot.id),
    }


def _commercial_from_engagement_metadata(company: Graph) -> dict[str, Any]:
    commercial = _unknown_commercial()
    engagements = ServiceEngagement.objects.filter(company=company).exclude(
        status__in={"cancelled", "archived"}
    )
    for engagement in engagements.order_by("-updated_at", "-created_at"):
        metadata = _mapping(engagement.metadata_json)
        economics = _commercial_metadata(metadata)
        if commercial["monthly_retainer"]["status"] == "unknown":
            commercial["monthly_retainer"] = _money_from_metadata(
                economics,
                "monthly_retainer",
                amount_keys=(
                    "monthly_retainer_amount",
                    "retainer_amount",
                    "monthly_fee_amount",
                ),
            )
        if commercial["contract_value"]["status"] == "unknown":
            commercial["contract_value"] = _money_from_metadata(
                economics,
                "contract_value",
                amount_keys=("contract_value_amount", "total_contract_value", "value_amount"),
            )
        if commercial["gross_margin"]["status"] == "unknown":
            margin = _margin_from_metadata(economics)
            if margin is not None:
                commercial["gross_margin"] = {"status": "known", "value": margin}
        if all(item["status"] == "known" for item in commercial.values()):
            break
    return commercial


def _commercial_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    for key in ("economics", "commercial", "profitability", "financials", "pricing"):
        nested = _mapping(metadata.get(key))
        if nested:
            return {**metadata, **nested}
    return metadata


def _money_from_metadata(
    metadata: dict[str, Any],
    nested_key: str,
    *,
    amount_keys: tuple[str, ...],
) -> dict[str, Any]:
    nested = _mapping(metadata.get(nested_key))
    currency = _currency(nested.get("currency") or metadata.get("currency"))
    amount = _decimal_or_none(
        nested.get("amount")
        or nested.get("value")
        or next((metadata.get(key) for key in amount_keys if metadata.get(key) is not None), None)
    )
    if amount is None:
        return _unknown_money()
    return {
        "status": "known",
        "amount": str(amount.quantize(Decimal("0.01"))),
        "currency": currency,
    }


def _margin_from_metadata(metadata: dict[str, Any]) -> float | None:
    for key in ("gross_margin", "gross_margin_percent", "margin", "margin_percent"):
        value = _ratio_or_none(metadata.get(key))
        if value is not None:
            return value
    revenue = _decimal_or_none(metadata.get("revenue_amount") or metadata.get("retainer_amount"))
    cost = _decimal_or_none(metadata.get("cost_amount") or metadata.get("delivery_cost_amount"))
    if revenue is None or revenue <= 0 or cost is None:
        return None
    return round(float((revenue - cost) / revenue), 4)


def _profit_from_commercial(commercial: dict[str, Any]) -> dict[str, Any]:
    gross_margin = commercial.get("gross_margin")
    if not isinstance(gross_margin, dict) or gross_margin.get("status") != "known":
        return _unknown_profit()
    value = _ratio_or_none(gross_margin.get("value"))
    if value is None:
        return _unknown_profit()
    if value < LOW_MARGIN_THRESHOLD:
        return {
            "status": "low_margin",
            "gross_margin": {"status": "known", "value": value},
            "summary": "Recorded gross margin is below the target operating range.",
        }
    if value < HEALTHY_MARGIN_THRESHOLD:
        return {
            "status": "watch",
            "gross_margin": {"status": "known", "value": value},
            "summary": "Recorded gross margin is usable but should be monitored.",
        }
    return {
        "status": "healthy",
        "gross_margin": {"status": "known", "value": value},
        "summary": "Recorded gross margin is within the target operating range.",
    }


def _expansion(company: Graph) -> dict[str, Any]:
    opportunities = list(
        CompanyOpportunity.objects.filter(company=company, status__in=OPEN_OPPORTUNITY_STATUSES)
        .select_related("signal")
        .order_by("-updated_at", "-created_at")[:10]
    )
    opportunity_signal_ids = {
        opportunity.signal_id for opportunity in opportunities if opportunity.signal_id is not None
    }
    signals = list(
        CompanySignal.objects.filter(company=company, status__in=OPEN_SIGNAL_STATUSES)
        .filter(Q(signal_kind="opportunity") | Q(signal_type__in={"lead", "demand"}))
        .order_by("-occurred_at", "-created_at")[:10]
    )
    recommendations = _expansion_recommendations(company)
    opportunity_score = min(
        100,
        len(opportunities) * 30
        + len(signals) * 20
        + sum(_factor_weight(item) for item in recommendations),
    )
    payload = {
        "status": "opportunity" if opportunities or signals or recommendations else "none",
        "opportunity_score": opportunity_score,
        "opportunities": [_opportunity_payload(opportunity) for opportunity in opportunities],
        "signals": [_signal_payload(signal) for signal in signals],
        "recommendations": recommendations,
    }
    if opportunity_signal_ids and not payload["signals"]:
        payload["signals"] = [
            _signal_payload(signal)
            for signal in CompanySignal.objects.filter(
                company=company, id__in=opportunity_signal_ids
            )
        ]
    return payload


def _expansion_recommendations(company: Graph) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    accepted_deliverables = ServiceDeliverable.objects.filter(
        company=company,
        visibility="customer",
        status__in={"accepted", "delivered"},
    ).count()
    if accepted_deliverables:
        recommendations.append(
            _insight(
                "accepted_deliverable_cross_sell",
                "medium",
                25,
                "Accepted customer-facing work creates a safe follow-on planning moment.",
            )
        )
    successful_launches = AtlasLaunchAttempt.objects.filter(
        company=company,
        status__in={"ready", "launched"},
    ).count()
    if successful_launches:
        recommendations.append(
            _insight(
                "successful_launch_follow_on",
                "medium",
                25,
                "A ready launch attempt can support a follow-on optimization discussion.",
            )
        )
    for service_name in _recommended_services(company)[:5]:
        recommendations.append(
            _insight(
                f"recommended_service_{_safe_slug(service_name)}",
                "low",
                15,
                f"Recorded engagement metadata recommends {service_name} as a follow-on service.",
            )
        )
    return _dedupe_insights(recommendations)


def _recommended_services(company: Graph) -> list[str]:
    names: list[str] = []
    engagements = ServiceEngagement.objects.filter(company=company).exclude(
        status__in={"cancelled", "archived"}
    )
    for engagement in engagements:
        metadata = _mapping(engagement.metadata_json)
        expansion = _mapping(metadata.get("expansion"))
        for value in (
            expansion.get("recommended_services"),
            expansion.get("services"),
            metadata.get("recommended_services"),
        ):
            names.extend(_safe_text_items(value, limit=80))
    return _dedupe_strings(names)


def _opportunity_payload(opportunity: CompanyOpportunity) -> dict[str, Any]:
    return {
        "opportunity_id": str(opportunity.id),
        "source_signal_id": str(opportunity.signal_id) if opportunity.signal_id else None,
        "title": opportunity.title,
        "summary": opportunity.summary,
        "status": opportunity.status,
        "estimated_value": {
            "amount": str(Decimal(opportunity.estimated_value_amount).quantize(Decimal("0.01"))),
            "currency": opportunity.currency,
        },
        "next_action": opportunity.next_action,
    }


def _signal_payload(signal: CompanySignal) -> dict[str, Any]:
    return {
        "signal_id": str(signal.id),
        "title": signal.title,
        "summary": signal.summary,
        "signal_kind": signal.signal_kind,
        "signal_type": signal.signal_type,
        "status": signal.status,
    }


def _scope(company: Graph) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    known = False
    engagements = ServiceEngagement.objects.filter(company=company).exclude(
        status__in={"cancelled", "archived"}
    )
    for engagement in engagements:
        scope_metadata = _scope_metadata(_mapping(engagement.metadata_json))
        requested = _requested_deliverables(scope_metadata)
        limit = _package_limit(scope_metadata)
        if requested is None or limit is None:
            continue
        known = True
        if requested > limit:
            warnings.append(
                {
                    "slug": "scope_requested_deliverables_over_package_limit",
                    "severity": "medium",
                    "requested_deliverables": requested,
                    "package_limit": limit,
                    "summary": "Requested deliverables exceed the recorded package limit.",
                }
            )
    return {
        "status": "warning" if warnings else "ok" if known else "unknown",
        "warnings": warnings,
    }


def _scope_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    scope = _mapping(metadata.get("scope"))
    if scope:
        return scope
    return metadata


def _requested_deliverables(metadata: dict[str, Any]) -> int | None:
    candidates = [
        metadata.get("requested_deliverables"),
        metadata.get("requested_deliverables_count"),
        metadata.get("requested_deliverable_count"),
    ]
    request_scope = _mapping(metadata.get("request_scope"))
    candidates.extend(
        [
            request_scope.get("deliverables"),
            request_scope.get("deliverables_count"),
        ]
    )
    for candidate in candidates:
        count = _count_value(candidate)
        if count is not None:
            return count
    return None


def _package_limit(metadata: dict[str, Any]) -> int | None:
    package_limit = _mapping(metadata.get("package_limit"))
    package_limits = _mapping(metadata.get("package_limits"))
    candidates = [
        metadata.get("deliverables_per_period"),
        metadata.get("deliverables_per_month"),
        package_limit.get("deliverables_per_period"),
        package_limit.get("deliverables_per_month"),
        package_limits.get("deliverables_per_period"),
        package_limits.get("deliverables_per_month"),
    ]
    for candidate in candidates:
        count = _count_value(candidate)
        if count is not None:
            return count
    return None


def _count_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def _retention(company: Graph, *, profit: dict[str, Any]) -> dict[str, Any]:
    risk_signals = list(
        CompanySignal.objects.filter(company=company, status__in=OPEN_SIGNAL_STATUSES)
        .filter(Q(signal_kind__in={"risk", "exception"}) | Q(signal_type="fulfillment_issue"))
        .order_by("-occurred_at", "-created_at")[:10]
    )
    factors = _retention_factors(company, risk_signals=risk_signals, profit=profit)
    risk_score = min(100, sum(_factor_weight(item) for item in factors))
    return {
        "status": "risk" if risk_score >= 40 else "monitor" if risk_score else "unknown",
        "risk_score": risk_score,
        "level": _risk_level(risk_score),
        "risks": [_signal_payload(signal) for signal in risk_signals],
        "factors": factors,
    }


def _retention_factors(
    company: Graph,
    *,
    risk_signals: list[CompanySignal],
    profit: dict[str, Any],
) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    if risk_signals:
        factors.append(
            _insight(
                "open_retention_signal",
                "high",
                35,
                "Open company signals indicate customer-visible retention risk.",
            )
        )
    stale_approvals = _stale_approval_count(company)
    if stale_approvals:
        factors.append(
            _insight(
                "stale_client_approval",
                "high",
                25,
                "Customer-facing approval work has remained in review past the expected window.",
            )
        )
    reporting = build_recurring_reporting_status(company)
    reporting_summary = _mapping(reporting.get("summary"))
    reporting_risks = reporting.get("risks") if isinstance(reporting.get("risks"), list) else []
    if reporting_summary.get("status") == "attention" or reporting_risks:
        factors.append(
            _insight(
                "reporting_cadence_at_risk",
                "medium",
                20,
                "Recurring reporting is configured but current customer-facing evidence is missing.",
            )
        )
    connectors = build_connector_readiness(company)
    connector_summary = _mapping(connectors.get("summary"))
    connector_gaps = (
        int(connector_summary.get("missing") or 0)
        + int(connector_summary.get("degraded") or 0)
        + int(connector_summary.get("disabled") or 0)
    )
    if connector_gaps:
        factors.append(
            _insight(
                "connector_gap",
                "medium",
                15,
                "Connector readiness gaps can reduce delivery reliability.",
            )
        )
    from application.services.agency_account_health import build_agency_account_health_snapshot

    account_health = build_agency_account_health_snapshot(company, include_growth_signals=False)
    health_summary = _mapping(account_health.get("health"))
    health_score = _int_or_none(health_summary.get("score"))
    if health_score is not None and health_score < 80:
        severity = "high" if health_score < 50 else "medium"
        factors.append(
            _insight(
                "account_health_attention",
                severity,
                25 if severity == "high" else 15,
                "Account health is below the target operating range and needs operator review.",
            )
        )
    if _sla_breach_count(company):
        factors.append(
            _insight(
                "sla_breached",
                "high",
                25,
                "Backend-owned routing records show breached or overdue work.",
            )
        )
    if AtlasLaunchAttempt.objects.filter(
        company=company, status__in={"blocked", "failed"}
    ).exists():
        factors.append(
            _insight(
                "launch_blocked",
                "medium",
                20,
                "A backend-owned launch attempt is blocked or failed.",
            )
        )
    if profit.get("status") == "low_margin":
        factors.append(
            _insight(
                "gross_margin_below_target",
                "medium",
                15,
                "Recorded profitability is below target and may require scope review.",
            )
        )
    return _dedupe_insights(factors)


def _stale_approval_count(company: Graph) -> int:
    threshold = timezone.now() - timedelta(days=STALE_APPROVAL_DAYS)
    return ServiceDeliverable.objects.filter(
        company=company,
        status="in_review",
        updated_at__lt=threshold,
    ).count()


def _sla_breach_count(company: Graph) -> int:
    now = timezone.now()
    active_statuses = {"queued", "assigned", "claimed", "in_progress", "blocked"}
    return (
        TaskRoutingRecord.objects.filter(company=company, status__in=active_statuses)
        .filter(Q(sla_breached_at__isnull=False) | Q(due_at__lt=now))
        .count()
    )


def _insight(slug: str, severity: str, weight: int, summary: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "severity": severity,
        "weight": weight,
        "summary": summary,
    }


def _factor_weight(item: dict[str, Any]) -> int:
    try:
        return int(item.get("weight") or 0)
    except (TypeError, ValueError):
        return 0


def _risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def _summary_status(
    *,
    expansion: dict[str, Any],
    scope: dict[str, Any],
    retention: dict[str, Any],
) -> str:
    if retention["status"] == "risk" or scope["status"] == "warning":
        return "attention"
    if expansion["status"] == "opportunity":
        return "opportunity"
    return "unknown"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        cleaned = str(value).strip().replace(",", "")
        if not cleaned:
            return None
        return Decimal(cleaned)
    except Exception:
        return None


def _ratio_or_none(value: Any) -> float | None:
    decimal_value = _decimal_or_none(str(value).strip().rstrip("%") if value is not None else None)
    if decimal_value is None:
        return None
    if decimal_value > 1:
        decimal_value = decimal_value / Decimal("100")
    if decimal_value < 0:
        return None
    return round(float(decimal_value), 4)


def _currency(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized[:8] if normalized else None


def _safe_text_items(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item or "") for item in value]
    else:
        return []
    return [
        item[:limit]
        for item in (raw.strip() for raw in values)
        if item and not _looks_sensitive_text(item)
    ]


def _looks_sensitive_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered
        for token in ("api_key", "access_token", "secret", "password", "bearer", "sk_live")
    )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug[:80] or "service"


def _dedupe_insights(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        deduped.setdefault(str(item["slug"]), item)
    return list(deduped.values())


def _dedupe_strings(items: list[str]) -> list[str]:
    deduped: dict[str, str] = {}
    for item in items:
        deduped.setdefault(item.lower(), item)
    return list(deduped.values())
