"""Backend-owned service engagement economics, scope, and SLA snapshots."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.domain_events import record_domain_event
from application.services.idempotency import hash_request_payload
from application.services.service_engagements import ServiceEngagementError
from infrastructure.orm.models import (
    Graph,
    ServiceEngagement,
    ServiceEngagementBusinessSnapshot,
    User,
)

SNAPSHOT_SCHEMA_VERSION = "service_engagement_business_snapshot_v1"
SNAPSHOT_EVENT_TYPE = "service_engagement.business_snapshot_recorded"
SNAPSHOT_OUTBOX_TOPIC = "forgegraph.service_engagements.events.v1"
_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")
_DEFAULT_SCOPE_THRESHOLD = Decimal("0.80")
_DEFAULT_SLA_THRESHOLD = Decimal("0.80")
_SEPARATE_DOMAIN_KEYS = {
    "connector",
    "connector_inventory",
    "connector_readiness",
    "connectors",
    "gateway_connection",
    "gateway_connections",
}
_BLOCKED_FIELD_TOKENS = (
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)


def record_service_engagement_business_snapshot(
    *,
    engagement: ServiceEngagement,
    actor: User | None,
    data: dict[str, Any],
    idempotency_key: str,
) -> ServiceEngagementBusinessSnapshot:
    """Record an idempotent backend-owned business snapshot for an engagement."""

    normalized_key = str(idempotency_key or "").strip()[:255]
    if not normalized_key:
        raise ServiceEngagementError(
            "idempotency_key_required",
            "Service engagement business snapshots require an idempotency key.",
        )
    if engagement.organization_id != engagement.company.organization_id:
        raise ServiceEngagementError(
            "engagement_company_mismatch",
            "Service engagement must belong to its company organization.",
        )

    safe_data = _sanitize_business_snapshot_data(data)
    request_hash = hash_request_payload(safe_data)
    source_key = str(safe_data.get("source_key") or "").strip()[:255]
    existing = _existing_snapshot(
        engagement=engagement,
        idempotency_key=normalized_key,
        source_key=source_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ServiceEngagementError(
                "idempotency_conflict",
                "Idempotency key or source key was already used with a different snapshot body.",
            )
        existing._idempotency_status = "already_applied"
        return existing

    values = _snapshot_values(engagement=engagement, data=safe_data)
    now = timezone.now()
    with transaction.atomic():
        existing = _existing_snapshot_locked(
            engagement=engagement,
            idempotency_key=normalized_key,
            source_key=source_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ServiceEngagementError(
                    "idempotency_conflict",
                    "Idempotency key or source key was already used with a different snapshot body.",
                )
            existing._idempotency_status = "already_applied"
            return existing

        snapshot = ServiceEngagementBusinessSnapshot.objects.create(
            organization=engagement.organization,
            company=engagement.company,
            engagement=engagement,
            source_key=source_key,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            period_start=values["period_start"],
            period_end=values["period_end"],
            currency=values["currency"],
            revenue_amount=values["revenue_amount"],
            delivery_cost_amount=values["delivery_cost_amount"],
            pass_through_cost_amount=values["pass_through_cost_amount"],
            tooling_cost_amount=values["tooling_cost_amount"],
            gross_margin_amount=values["gross_margin_amount"],
            gross_margin_percent=values["gross_margin_percent"],
            profitability_band=values["profitability_band"],
            scope_unit=values["scope_unit"],
            scope_included_units=values["scope_included_units"],
            scope_used_units=values["scope_used_units"],
            scope_overage_units=values["scope_overage_units"],
            scope_utilization_percent=values["scope_utilization_percent"],
            scope_status=values["scope_status"],
            sla_target_hours=values["sla_target_hours"],
            sla_elapsed_hours=values["sla_elapsed_hours"],
            sla_breach_count=values["sla_breach_count"],
            sla_status=values["sla_status"],
            snapshot_json=values["snapshot_json"],
            metadata_json=values["metadata_json"],
            recorded_by=actor,
            recorded_at=now,
        )
        _record_snapshot_audit(snapshot=snapshot, actor=actor)
        _record_snapshot_domain_event(snapshot)

    snapshot._idempotency_status = "applied"
    return snapshot


def service_engagement_business_snapshot_payload(
    snapshot: ServiceEngagementBusinessSnapshot,
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    """Return a client-safe or operator-safe DTO for a business snapshot."""

    snapshot_data = snapshot.snapshot_json if isinstance(snapshot.snapshot_json, dict) else {}
    period = dict(snapshot_data.get("period") or {})
    economics = dict(snapshot_data.get("economics") or {})
    scope = dict(snapshot_data.get("scope") or {})
    sla = dict(snapshot_data.get("sla") or {})
    payload: dict[str, Any] = {
        "id": str(snapshot.id),
        "organization_id": str(snapshot.organization_id),
        "company_id": str(snapshot.company_id),
        "engagement_id": str(snapshot.engagement_id),
        "period": period,
        "economics": {"revenue": economics.get("revenue") or _money_payload(Decimal("0"), snapshot.currency)},
        "scope": scope,
        "sla": sla,
        "recorded_at": snapshot.recorded_at.isoformat() if snapshot.recorded_at else None,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }
    if include_internal:
        payload["economics"] = economics
        payload["profitability"] = dict(snapshot_data.get("profitability") or {})
        payload["source_key"] = snapshot.source_key
        payload["idempotency_key"] = snapshot.idempotency_key
        payload["recorded_by_id"] = str(snapshot.recorded_by_id) if snapshot.recorded_by_id else None
        payload["metadata"] = dict(snapshot.metadata_json or {})
    safe_payload = _drop_separate_domain_data(sanitize_outbox_payload(payload))
    return safe_payload if isinstance(safe_payload, dict) else {}


def latest_business_snapshot_for_company(
    company: Graph,
) -> ServiceEngagementBusinessSnapshot | None:
    return (
        ServiceEngagementBusinessSnapshot.objects.filter(company=company)
        .select_related("engagement", "company")
        .order_by("-recorded_at", "-created_at")
        .first()
    )


def _existing_snapshot(
    *,
    engagement: ServiceEngagement,
    idempotency_key: str,
    source_key: str,
) -> ServiceEngagementBusinessSnapshot | None:
    snapshot = ServiceEngagementBusinessSnapshot.objects.filter(
        engagement=engagement,
        idempotency_key=idempotency_key,
    ).first()
    if snapshot is not None or not source_key:
        return snapshot
    return ServiceEngagementBusinessSnapshot.objects.filter(
        engagement=engagement,
        source_key=source_key,
    ).first()


def _existing_snapshot_locked(
    *,
    engagement: ServiceEngagement,
    idempotency_key: str,
    source_key: str,
) -> ServiceEngagementBusinessSnapshot | None:
    queryset = ServiceEngagementBusinessSnapshot.objects.select_for_update().filter(
        engagement=engagement,
    )
    snapshot = queryset.filter(idempotency_key=idempotency_key).first()
    if snapshot is not None or not source_key:
        return snapshot
    return queryset.filter(source_key=source_key).first()


def _snapshot_values(*, engagement: ServiceEngagement, data: dict[str, Any]) -> dict[str, Any]:
    economics = _economics(data)
    scope = _scope(data)
    sla = _sla(data)
    period_start = _date_value(data.get("period_start"))
    period_end = _date_value(data.get("period_end"))
    period = {
        "start": period_start.isoformat() if period_start else None,
        "end": period_end.isoformat() if period_end else None,
    }
    snapshot_json = sanitize_outbox_payload(
        {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "organization_id": str(engagement.organization_id),
            "company_id": str(engagement.company_id),
            "engagement_id": str(engagement.id),
            "period": period,
            "economics": economics["payload"],
            "profitability": economics["profitability"],
            "scope": scope["payload"],
            "sla": sla["payload"],
        }
    )
    return {
        "period_start": period_start,
        "period_end": period_end,
        "currency": economics["currency"],
        "revenue_amount": economics["revenue_amount"],
        "delivery_cost_amount": economics["delivery_cost_amount"],
        "pass_through_cost_amount": economics["pass_through_cost_amount"],
        "tooling_cost_amount": economics["tooling_cost_amount"],
        "gross_margin_amount": economics["gross_margin_amount"],
        "gross_margin_percent": economics["gross_margin_percent"],
        "profitability_band": economics["profitability_band"],
        "scope_unit": scope["unit"],
        "scope_included_units": scope["included_units"],
        "scope_used_units": scope["used_units"],
        "scope_overage_units": scope["overage_units"],
        "scope_utilization_percent": scope["utilization_percent"],
        "scope_status": scope["status"],
        "sla_target_hours": sla["target_hours"],
        "sla_elapsed_hours": sla["elapsed_hours"],
        "sla_breach_count": sla["breach_count"],
        "sla_status": sla["status"],
        "snapshot_json": snapshot_json,
        "metadata_json": _metadata(data),
    }


def _economics(data: dict[str, Any]) -> dict[str, Any]:
    economics = _mapping(data.get("economics"))
    revenue = _money_amount(
        economics.get("revenue")
        or economics.get("monthly_retainer")
        or data.get("revenue")
        or data.get("monthly_retainer")
    )
    delivery = _money_amount(
        economics.get("delivery_cost")
        or economics.get("labor_cost")
        or economics.get("fulfillment_cost")
        or data.get("delivery_cost")
    )
    pass_through = _money_amount(
        economics.get("pass_through_cost")
        or economics.get("media_spend")
        or economics.get("external_cost")
    )
    tooling = _money_amount(economics.get("tooling_cost") or economics.get("tool_cost"))
    currency = _currency(
        economics.get("revenue"),
        economics.get("monthly_retainer"),
        economics.get("delivery_cost"),
        economics.get("pass_through_cost"),
        default=str(data.get("currency") or "USD"),
    )
    total_cost = _quantize_money(delivery + pass_through + tooling)
    margin = _quantize_money(revenue - total_cost)
    margin_percent = None
    if revenue > 0:
        margin_percent = _quantize_percent((margin / revenue) * Decimal("100"))
    band = _profitability_band(margin_percent=margin_percent, gross_margin_amount=margin)
    return {
        "currency": currency,
        "revenue_amount": revenue,
        "delivery_cost_amount": delivery,
        "pass_through_cost_amount": pass_through,
        "tooling_cost_amount": tooling,
        "gross_margin_amount": margin,
        "gross_margin_percent": margin_percent,
        "profitability_band": band,
        "payload": {
            "revenue": _money_payload(revenue, currency),
            "delivery_cost": _money_payload(delivery, currency),
            "pass_through_cost": _money_payload(pass_through, currency),
            "tooling_cost": _money_payload(tooling, currency),
            "total_cost": _money_payload(total_cost, currency),
        },
        "profitability": {
            "status": "known" if margin_percent is not None else "unknown",
            "band": band,
            "gross_margin_amount": _money_payload(margin, currency),
            "gross_margin_percent": _decimal_text(margin_percent),
        },
    }


def _scope(data: dict[str, Any]) -> dict[str, Any]:
    scope = _mapping(data.get("scope"))
    included = _int_value(
        scope.get("included_units")
        or scope.get("package_limit")
        or scope.get("deliverables_per_period")
    )
    used = _int_value(
        scope.get("used_units")
        or scope.get("consumed_units")
        or scope.get("requested_units")
        or scope.get("requested_deliverables")
    )
    threshold = _ratio_value(scope.get("overage_alert_threshold"), default=_DEFAULT_SCOPE_THRESHOLD)
    utilization = None
    overage = 0
    status = "unknown"
    if included is not None and used is not None and included > 0:
        utilization = _quantize_percent((Decimal(used) / Decimal(included)) * Decimal("100"))
        overage = max(used - included, 0)
        utilization_ratio = Decimal(used) / Decimal(included)
        if overage > 0:
            status = "over_limit"
        elif utilization_ratio >= threshold:
            status = "at_risk"
        else:
            status = "on_track"
    return {
        "unit": str(scope.get("unit") or "unit").strip()[:64],
        "included_units": included,
        "used_units": used,
        "overage_units": overage,
        "utilization_percent": utilization,
        "status": status,
        "payload": {
            "unit": str(scope.get("unit") or "unit").strip()[:64],
            "included_units": included,
            "used_units": used,
            "overage_units": overage,
            "utilization_percent": _decimal_text(utilization),
            "overage_risk": status in {"at_risk", "over_limit"},
            "status": status,
        },
    }


def _sla(data: dict[str, Any]) -> dict[str, Any]:
    sla = _mapping(data.get("sla"))
    target = _decimal_value(sla.get("target_hours"))
    elapsed = _decimal_value(sla.get("elapsed_hours"))
    breaches = _list_of_mappings(sla.get("breaches"))
    breach_count = _int_value(sla.get("breach_count"))
    if breach_count is None:
        breach_count = len(breaches)
    threshold = _ratio_value(sla.get("at_risk_threshold"), default=_DEFAULT_SLA_THRESHOLD)
    status = "unknown"
    if breach_count > 0:
        status = "breached"
    elif target is not None and elapsed is not None and target > 0:
        ratio = elapsed / target
        if elapsed > target:
            status = "breached"
        elif ratio >= threshold:
            status = "at_risk"
        else:
            status = "met"
    return {
        "target_hours": _quantize_percent(target) if target is not None else None,
        "elapsed_hours": _quantize_percent(elapsed) if elapsed is not None else None,
        "breach_count": max(breach_count, 0),
        "status": status,
        "payload": {
            "status": status,
            "target_hours": _decimal_text(target),
            "elapsed_hours": _decimal_text(elapsed),
            "breach_count": max(breach_count, 0),
            "breaches": breaches,
        },
    }


def _metadata(data: dict[str, Any]) -> dict[str, Any]:
    metadata = _mapping(data.get("metadata"))
    return _drop_separate_domain_data(sanitize_outbox_payload(metadata))


def _record_snapshot_audit(
    *,
    snapshot: ServiceEngagementBusinessSnapshot,
    actor: User | None,
) -> None:
    record_audit_log(
        actor=actor,
        tenant_id=str(snapshot.organization_id),
        action=SNAPSHOT_EVENT_TYPE,
        resource_type="service_engagement_business_snapshot",
        resource_id=str(snapshot.id),
        metadata={
            "company_id": str(snapshot.company_id),
            "engagement_id": str(snapshot.engagement_id),
            "profitability_band": snapshot.profitability_band,
            "scope_status": snapshot.scope_status,
            "sla_status": snapshot.sla_status,
        },
    )


def _record_snapshot_domain_event(snapshot: ServiceEngagementBusinessSnapshot) -> None:
    payload = {
        "snapshot_id": str(snapshot.id),
        "organization_id": str(snapshot.organization_id),
        "company_id": str(snapshot.company_id),
        "engagement_id": str(snapshot.engagement_id),
        "profitability_band": snapshot.profitability_band,
        "scope_status": snapshot.scope_status,
        "sla_status": snapshot.sla_status,
        "snapshot": snapshot.snapshot_json,
        "created_at": snapshot.recorded_at.isoformat() if snapshot.recorded_at else None,
    }
    record_domain_event(
        organization=snapshot.organization,
        aggregate_type="service_engagement_business_snapshot",
        aggregate_id=snapshot.id,
        event_type=SNAPSHOT_EVENT_TYPE,
        idempotency_key=f"service-engagement-business-snapshot:{snapshot.id}:recorded",
        payload=payload,
        outbox_topic=SNAPSHOT_OUTBOX_TOPIC,
        outbox_schema_version=SNAPSHOT_SCHEMA_VERSION,
        outbox_payload=payload,
        outbox_visibility="internal",
        outbox_company=snapshot.company,
    )


def _sanitize_business_snapshot_data(data: dict[str, Any]) -> dict[str, Any]:
    return _drop_separate_domain_data(sanitize_outbox_payload(data))


def _drop_separate_domain_data(value: Any, *, field_name: str = "") -> Any:
    normalized = field_name.strip().lower()
    if normalized in _SEPARATE_DOMAIN_KEYS or any(
        token in normalized for token in _BLOCKED_FIELD_TOKENS
    ):
        return None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _drop_separate_domain_data(item, field_name=str(key))
            if cleaned is not None:
                result[str(key)] = cleaned
        return result
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _drop_separate_domain_data(item, field_name=field_name)) is not None
        ]
    return value


def _date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _money_amount(value: Any) -> Decimal:
    mapping = _mapping(value)
    if mapping:
        return _quantize_money(_decimal_value(mapping.get("amount")) or Decimal("0"))
    return _quantize_money(_decimal_value(value) or Decimal("0"))


def _decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (list, tuple, set)):
        return len(value)
    try:
        parsed = int(str(value))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _ratio_value(value: Any, *, default: Decimal) -> Decimal:
    parsed = _decimal_value(value)
    if parsed is None or parsed <= 0:
        return default
    if parsed > 1:
        return parsed / Decimal("100")
    return parsed


def _currency(*values: Any, default: str) -> str:
    for value in values:
        mapping = _mapping(value)
        currency = str(mapping.get("currency") or "").strip().upper()
        if currency:
            return currency[:3]
    return str(default or "USD").strip().upper()[:3] or "USD"


def _profitability_band(
    *,
    margin_percent: Decimal | None,
    gross_margin_amount: Decimal,
) -> str:
    if margin_percent is None:
        return "loss" if gross_margin_amount < 0 else "unknown"
    if margin_percent >= Decimal("50"):
        return "strong"
    if margin_percent >= Decimal("30"):
        return "healthy"
    if margin_percent >= Decimal("15"):
        return "thin"
    if margin_percent >= Decimal("0"):
        return "break_even"
    return "loss"


def _money_payload(amount: Decimal, currency: str) -> dict[str, str]:
    return {"amount": _decimal_text(_quantize_money(amount)) or "0.00", "currency": currency}


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.2f}"


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _quantize_percent(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT, rounding=ROUND_HALF_UP)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
