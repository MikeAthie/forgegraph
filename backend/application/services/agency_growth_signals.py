"""Backend-owned agency retention, expansion, scope, and profit signals."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.utils import timezone

from infrastructure.orm.models import (
    CompanyOpportunity,
    CompanySignal,
    Graph,
    ServiceEngagement,
)

OPEN_OPPORTUNITY_STATUSES = {"new", "qualified", "follow_up", "reserved"}
OPEN_SIGNAL_STATUSES = {"new", "qualified"}


def build_agency_growth_signals(company: Graph) -> dict[str, Any]:
    """Return client-safe commercial and growth signals from backend records."""

    expansion = _expansion(company)
    scope = _scope(company)
    retention = _retention(company)
    profit = _unknown_profit()
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "status": _summary_status(expansion=expansion, scope=scope, retention=retention),
            "open_expansion_opportunities": len(expansion["opportunities"]),
            "scope_warnings": len(scope["warnings"]),
            "retention_risks": len(retention["risks"]),
        },
        "commercial": _unknown_commercial(),
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
    payload = {
        "status": "opportunity" if opportunities or signals else "none",
        "opportunities": [_opportunity_payload(opportunity) for opportunity in opportunities],
        "signals": [_signal_payload(signal) for signal in signals],
    }
    if opportunity_signal_ids and not payload["signals"]:
        payload["signals"] = [
            _signal_payload(signal)
            for signal in CompanySignal.objects.filter(id__in=opportunity_signal_ids)
        ]
    return payload


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


def _retention(company: Graph) -> dict[str, Any]:
    risk_signals = list(
        CompanySignal.objects.filter(company=company, status__in=OPEN_SIGNAL_STATUSES)
        .filter(Q(signal_kind__in={"risk", "exception"}) | Q(signal_type="fulfillment_issue"))
        .order_by("-occurred_at", "-created_at")[:10]
    )
    return {
        "status": "risk" if risk_signals else "unknown",
        "risks": [_signal_payload(signal) for signal in risk_signals],
    }


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
