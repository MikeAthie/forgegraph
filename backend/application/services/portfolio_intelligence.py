"""Privacy-safe portfolio intelligence benchmarks for company operations."""

from __future__ import annotations

from statistics import median
from typing import Any

from django.utils import timezone

from application.services.agency_account_health import build_agency_account_health_snapshot
from application.services.agency_growth_signals import build_agency_growth_signals
from application.services.company_access import accessible_company_queryset
from infrastructure.orm.models import User


def portfolio_intelligence_payload(user: User) -> dict[str, Any]:
    """Return aggregate-only benchmarks across companies visible to the user."""

    companies = list(accessible_company_queryset(user, minimum_role="viewer").order_by("id"))
    rows: list[dict[str, Any]] = []
    for company in companies:
        growth = build_agency_growth_signals(company)
        health = build_agency_account_health_snapshot(company)
        retention = growth.get("retention") if isinstance(growth.get("retention"), dict) else {}
        expansion = growth.get("expansion") if isinstance(growth.get("expansion"), dict) else {}
        rows.append(
            {
                "health_score": _int_value(_mapping(health.get("health")).get("score")),
                "churn_risk_score": _int_value(retention.get("risk_score")),
                "churn_level": str(retention.get("level") or "unknown"),
                "expansion_opportunity_score": _int_value(expansion.get("opportunity_score")),
                "expansion_status": str(expansion.get("status") or "none"),
                "open_expansion_opportunities": len(_list(expansion.get("opportunities"))),
                "connector_gap": _connector_gap(health),
                "reporting_attention": _reporting_attention(health),
            }
        )

    summary = _summary(rows)
    return {
        "source": "computed",
        "organization_id": str(user.default_organization_id or ""),
        "generated_at": timezone.now().isoformat(),
        "privacy": {
            "mode": "aggregate_only",
            "raw_company_payloads_exposed": False,
            "company_names_exposed": False,
            "minimum_peer_count": 2,
        },
        "summary": summary,
        "benchmarks": {
            "account_health_score": _benchmark(
                [row["health_score"] for row in rows if row["health_score"] is not None]
            ),
            "churn_risk_score": _benchmark(
                [row["churn_risk_score"] for row in rows if row["churn_risk_score"] is not None]
            ),
            "expansion_opportunity_score": _benchmark(
                [
                    row["expansion_opportunity_score"]
                    for row in rows
                    if row["expansion_opportunity_score"] is not None
                ]
            ),
        },
        "segments": _segments(summary),
        "priority_queue": _priority_queue(summary),
        "insights": _insights(summary),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    high = sum(1 for row in rows if row["churn_level"] == "high")
    medium = sum(1 for row in rows if row["churn_level"] == "medium")
    low = sum(1 for row in rows if row["churn_level"] == "low")
    unknown = total - high - medium - low
    expansion_accounts = sum(1 for row in rows if row["expansion_status"] == "opportunity")
    return {
        "companies_analyzed": total,
        "high_churn_risk": high,
        "medium_churn_risk": medium,
        "low_churn_risk": low,
        "unknown_churn_risk": unknown,
        "expansion_opportunity_accounts": expansion_accounts,
        "open_expansion_opportunities": sum(
            int(row["open_expansion_opportunities"]) for row in rows
        ),
        "connector_gap_accounts": sum(1 for row in rows if row["connector_gap"]),
        "reporting_attention_accounts": sum(1 for row in rows if row["reporting_attention"]),
    }


def _benchmark(values: list[int]) -> dict[str, Any]:
    sample_size = len(values)
    if sample_size < 2:
        return {
            "sample_size": sample_size,
            "suppressed": True,
            "suppression_reason": "minimum_peer_count" if sample_size else "no_data",
            "average": None,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    sorted_values = sorted(values)
    return {
        "sample_size": sample_size,
        "suppressed": False,
        "suppression_reason": None,
        "average": round(sum(sorted_values) / sample_size, 2),
        "median": float(median(sorted_values)),
        "minimum": sorted_values[0],
        "maximum": sorted_values[-1],
    }


def _segments(summary: dict[str, Any]) -> list[dict[str, Any]]:
    total = max(int(summary.get("companies_analyzed") or 0), 1)
    segments = [
        ("high_churn_risk", "high_churn_risk"),
        ("medium_churn_risk", "medium_churn_risk"),
        ("expansion_opportunity_accounts", "expansion_opportunity_accounts"),
        ("connector_gap_accounts", "connector_gap_accounts"),
        ("reporting_attention_accounts", "reporting_attention_accounts"),
    ]
    return [
        {
            "slug": slug,
            "company_count": int(summary.get(key) or 0),
            "share": round(int(summary.get(key) or 0) / total, 4),
        }
        for slug, key in segments
    ]


def _priority_queue(summary: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    high_risk = int(summary.get("high_churn_risk") or 0)
    if high_risk:
        queue.append(
            {
                "priority": "protect",
                "company_count": high_risk,
                "summary": "Protect the aggregate high churn-risk account segment.",
            }
        )
    expansion_accounts = int(summary.get("expansion_opportunity_accounts") or 0)
    if expansion_accounts:
        queue.append(
            {
                "priority": "expand",
                "company_count": expansion_accounts,
                "summary": "Expand the aggregate account segment with qualified opportunities.",
            }
        )
    if int(summary.get("connector_gap_accounts") or 0):
        queue.append(
            {
                "priority": "unblock",
                "company_count": int(summary.get("connector_gap_accounts") or 0),
                "summary": "Unblock the aggregate account segment with connector gaps.",
            }
        )
    return queue


def _insights(summary: dict[str, Any]) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    if int(summary.get("high_churn_risk") or 0):
        insights.append(
            {
                "slug": "retention_risk_concentration",
                "severity": "high",
                "summary": "At least one accessible account is in a high churn-risk segment.",
            }
        )
    if int(summary.get("expansion_opportunity_accounts") or 0):
        insights.append(
            {
                "slug": "expansion_pipeline_available",
                "severity": "medium",
                "summary": "Accessible accounts include aggregate expansion opportunities.",
            }
        )
    if int(summary.get("connector_gap_accounts") or 0):
        insights.append(
            {
                "slug": "connector_gaps_limit_delivery",
                "severity": "medium",
                "summary": "Connector gaps appear across the accessible portfolio.",
            }
        )
    return insights


def _connector_gap(health: dict[str, Any]) -> bool:
    readiness = _mapping(health.get("connector_readiness"))
    summary = _mapping(readiness.get("summary"))
    return any(int(summary.get(key) or 0) for key in ("missing", "degraded", "disabled"))


def _reporting_attention(health: dict[str, Any]) -> bool:
    reporting = _mapping(health.get("recurring_reporting"))
    summary = _mapping(reporting.get("summary"))
    return str(summary.get("status") or "") == "attention"


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
