"""Backend-owned discovery-to-proposal commercial funnel payloads."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from infrastructure.orm.models import (
    CompanyOpportunity,
    Graph,
    ServiceDeliverable,
    ServiceEngagement,
)

OPEN_OPPORTUNITY_STATUSES = {"new", "qualified", "follow_up", "reserved"}
WON_OPPORTUNITY_STATUSES = {"converted"}
LOST_OPPORTUNITY_STATUSES = {"lost"}

_INTAKE_KEYS = ("commercial_intake", "intake", "discovery", "qualification")
_BLOCKED_TEXT_TOKENS = (
    "api-key",
    "api_key",
    "apikey",
    "bearer ",
    "confidential",
    "credential",
    "do not expose",
    "internal",
    "margin",
    "password",
    "private",
    "secret",
    "token",
)


def normalize_opportunity_intake(
    opportunity: CompanyOpportunity,
    *,
    engagement: ServiceEngagement | None = None,
) -> dict[str, Any]:
    """Normalize explicit discovery and qualification fields from backend metadata."""

    source = _commercial_intake_source(opportunity=opportunity, engagement=engagement)
    return {
        "icp_fit": _icp_fit(source.get("icp_fit")),
        "pain": _pain(source.get("pain")),
        "budget": _money_value(source.get("budget")),
        "authority": _known_text(source.get("authority")),
        "timing": _known_text(source.get("timing")),
        "expected_retainer": _money_value(
            _first_present(
                source.get("expected_retainer"),
                source.get("retainer"),
                source.get("monthly_retainer"),
            )
        ),
        "close_probability": _probability(source.get("close_probability")),
    }


def build_proposal_packet(
    opportunity: CompanyOpportunity,
    *,
    engagement: ServiceEngagement | None = None,
) -> dict[str, Any]:
    """Build a client-safe proposal packet from backend service and metadata records."""

    selected_engagement = engagement or _engagement_for_opportunity(opportunity)
    client_safe = {
        "company_id": str(opportunity.company_id),
        "generated_at": timezone.now().isoformat(),
        "opportunity": {
            "id": str(opportunity.id),
            "title": _safe_text(opportunity.title),
            "summary": _safe_text(opportunity.summary),
            "status": opportunity.status,
            "next_action": _safe_text(opportunity.next_action),
        },
        "intake": normalize_opportunity_intake(
            opportunity,
            engagement=selected_engagement,
        ),
        "proposal": {
            "status": _proposal_status(selected_engagement),
            "engagement_id": str(selected_engagement.id) if selected_engagement else None,
        },
        "sections": {
            "sow": _sow_section(opportunity=opportunity, engagement=selected_engagement),
            "roi_estimate": _roi_estimate(
                opportunity=opportunity,
                engagement=selected_engagement,
            ),
        },
        "pricing": _pricing(selected_engagement),
        "deliverables": _deliverables(selected_engagement),
        "win_loss_summary": build_win_loss_status_summary(
            opportunity.company,
            current_opportunity=opportunity,
        ),
    }
    return {"client_safe": client_safe}


def build_win_loss_status_summary(
    company: Graph,
    *,
    current_opportunity: CompanyOpportunity | None = None,
) -> dict[str, Any]:
    """Summarize company opportunity outcomes from backend-owned opportunity statuses."""

    opportunities = CompanyOpportunity.objects.filter(company=company).only("id", "status")
    return {
        "current_opportunity": _current_opportunity_summary(current_opportunity),
        "company": {
            "open": _status_bucket(opportunities, OPEN_OPPORTUNITY_STATUSES),
            "won": _status_bucket(opportunities, WON_OPPORTUNITY_STATUSES),
            "lost": _status_bucket(opportunities, LOST_OPPORTUNITY_STATUSES),
        },
    }


def _commercial_intake_source(
    *,
    opportunity: CompanyOpportunity,
    engagement: ServiceEngagement | None,
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    if opportunity.signal_id:
        sources.append(_metadata_intake(_mapping(opportunity.signal.metadata_json)))
    sources.append(_metadata_intake(_mapping(opportunity.metadata_json)))
    if engagement is not None:
        sources.append(_metadata_intake(_mapping(engagement.intake_data_json)))
        sources.append(_metadata_intake(_mapping(engagement.metadata_json)))

    merged: dict[str, Any] = {}
    for source in sources:
        merged.update(source)
    return merged


def _metadata_intake(metadata: dict[str, Any]) -> dict[str, Any]:
    values = dict(metadata)
    for key in _INTAKE_KEYS:
        nested = _mapping(metadata.get(key))
        if nested:
            values.update(nested)
    return values


def _icp_fit(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        label = _safe_text(_first_present(value.get("label"), value.get("value"), value.get("tier")))
        score = _int_value(value.get("score"))
        if label is not None or score is not None:
            return {"status": "known", "value": label, "score": score}
    text = _safe_text(value)
    if text is not None:
        return {"status": "known", "value": text, "score": None}
    return {"status": "unknown", "value": None, "score": None}


def _pain(value: Any) -> dict[str, Any]:
    items: list[str] = []
    if isinstance(value, list | tuple | set):
        items = [_safe_text(item) for item in value]
    elif isinstance(value, str):
        items = [_safe_text(item) for item in value.split(";")]
    else:
        text = _safe_text(value)
        items = [text] if text is not None else []
    safe_items = [item for item in items if item]
    if not safe_items:
        return {"status": "unknown", "items": []}
    return {"status": "known", "items": safe_items}


def _known_text(value: Any) -> dict[str, Any]:
    text = _safe_text(value)
    if text is None:
        return {"status": "unknown", "value": None}
    return {"status": "known", "value": text}


def _money_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        amount = _decimal_value(
            _first_present(
                value.get("amount"),
                value.get("value"),
                value.get("monthly_amount"),
            )
        )
        currency = _safe_text(value.get("currency"))
        if amount is not None and currency is not None:
            return {
                "status": "known",
                "amount": _format_money(amount),
                "currency": currency.lower(),
            }
    elif value is not None:
        amount = _decimal_value(value)
        if amount is not None:
            return {"status": "known", "amount": _format_money(amount), "currency": None}
    return _unknown_money()


def _unknown_money() -> dict[str, Any]:
    return {"status": "unknown", "amount": None, "currency": None}


def _probability(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("%"):
            parsed = _decimal_value(raw[:-1])
            if parsed is not None:
                return {"status": "known", "value": float(parsed / Decimal("100"))}
        parsed = _decimal_value(raw)
    else:
        parsed = _decimal_value(value)
    if parsed is None:
        return {"status": "unknown", "value": None}
    if parsed > 1:
        parsed = parsed / Decimal("100")
    if parsed < 0 or parsed > 1:
        return {"status": "unknown", "value": None}
    return {"status": "known", "value": float(parsed)}


def _engagement_for_opportunity(opportunity: CompanyOpportunity) -> ServiceEngagement | None:
    return (
        ServiceEngagement.objects.filter(company=opportunity.company)
        .filter(metadata_json__opportunity_id=str(opportunity.id))
        .select_related("catalog_item")
        .order_by("-updated_at", "-created_at")
        .first()
    )


def _proposal_status(engagement: ServiceEngagement | None) -> str:
    if engagement is None:
        return "unknown"
    proposal = _proposal_deliverable(engagement)
    if proposal is not None:
        return proposal.status
    return engagement.status


def _sow_section(
    *,
    opportunity: CompanyOpportunity,
    engagement: ServiceEngagement | None,
) -> dict[str, Any]:
    source = _proposal_metadata(opportunity=opportunity, engagement=engagement).get("sow")
    sow = _mapping(source)
    objective = _safe_text(sow.get("objective"))
    in_scope = _safe_text_list(sow.get("in_scope"))
    out_of_scope = _safe_text_list(sow.get("out_of_scope"))
    assumptions = _safe_text_list(sow.get("assumptions"))
    if not any([objective, in_scope, out_of_scope, assumptions]):
        return {
            "status": "unknown",
            "objective": None,
            "in_scope": [],
            "out_of_scope": [],
            "assumptions": [],
        }
    return {
        "status": "known",
        "objective": objective,
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "assumptions": assumptions,
    }


def _roi_estimate(
    *,
    opportunity: CompanyOpportunity,
    engagement: ServiceEngagement | None,
) -> dict[str, Any]:
    source = _mapping(_proposal_metadata(opportunity=opportunity, engagement=engagement).get("roi_estimate"))
    projected_value = _money_value(
        _first_present(
            source.get("projected_value"),
            source.get("expected_value"),
            source.get("incremental_revenue"),
        )
    )
    payback = _int_value(source.get("payback_period_months"))
    basis = _safe_text(source.get("basis"))
    if projected_value["status"] == "unknown" and payback is None and basis is None:
        return {
            "status": "unknown",
            "projected_value": _unknown_money(),
            "payback_period_months": {"status": "unknown", "value": None},
            "basis": "ROI cannot be estimated until explicit client-approved inputs are recorded.",
        }
    return {
        "status": "known",
        "projected_value": projected_value,
        "payback_period_months": {
            "status": "known" if payback is not None else "unknown",
            "value": payback,
        },
        "basis": basis or "",
    }


def _proposal_metadata(
    *,
    opportunity: CompanyOpportunity,
    engagement: ServiceEngagement | None,
) -> dict[str, Any]:
    proposal: dict[str, Any] = {}
    metadata_sources = [_mapping(opportunity.metadata_json)]
    if engagement is not None:
        metadata_sources.extend(
            [
                _mapping(engagement.metadata_json),
                _mapping(engagement.intake_data_json),
            ]
        )
    for metadata in metadata_sources:
        proposal.update(_mapping(metadata.get("proposal")))
    return proposal


def _pricing(engagement: ServiceEngagement | None) -> dict[str, Any]:
    if engagement is None:
        return {"status": "unknown", "package": {}, "setup_fee": _unknown_money()}
    pricing = _mapping(engagement.catalog_item.pricing_metadata_json)
    package = _mapping(pricing.get("package"))
    setup_fee = _money_value(pricing.get("setup_fee"))
    package_payload = {
        "slug": _safe_text(package.get("slug")),
        "name": _safe_text(package.get("name")),
        "billing_period": _safe_text(package.get("billing_period")),
        "retainer": _money_value(package.get("retainer")),
    }
    if not any(package_payload.values()) and setup_fee["status"] == "unknown":
        return {"status": "unknown", "package": {}, "setup_fee": _unknown_money()}
    return {
        "status": "known",
        "package": package_payload,
        "setup_fee": setup_fee,
    }


def _deliverables(engagement: ServiceEngagement | None) -> list[dict[str, Any]]:
    if engagement is None:
        return []
    actuals = list(
        ServiceDeliverable.objects.filter(engagement=engagement, visibility="customer")
        .exclude(status="archived")
        .order_by("created_at")
    )
    actuals_by_type = {deliverable.deliverable_type: deliverable for deliverable in actuals}
    payload: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for definition in _schema_definitions(engagement):
        deliverable_type = str(definition.get("type") or "")
        actual = actuals_by_type.get(deliverable_type)
        if actual is not None:
            payload.append(_deliverable_payload(actual))
            seen_types.add(deliverable_type)
            continue
        payload.append(
            {
                "id": None,
                "title": _safe_text(definition.get("title")) or deliverable_type,
                "type": deliverable_type,
                "status": "planned",
            }
        )
        seen_types.add(deliverable_type)
    for actual in actuals:
        if actual.deliverable_type not in seen_types:
            payload.append(_deliverable_payload(actual))
    return payload


def _schema_definitions(engagement: ServiceEngagement) -> list[dict[str, Any]]:
    definitions = engagement.catalog_item.deliverables_schema_json or []
    return [definition for definition in definitions if isinstance(definition, dict)]


def _deliverable_payload(deliverable: ServiceDeliverable) -> dict[str, Any]:
    return {
        "id": str(deliverable.id),
        "title": _safe_text(deliverable.title),
        "type": deliverable.deliverable_type,
        "status": deliverable.status,
    }


def _proposal_deliverable(engagement: ServiceEngagement) -> ServiceDeliverable | None:
    return (
        ServiceDeliverable.objects.filter(
            engagement=engagement,
            deliverable_type__in={"approval_packet", "proposal_packet", "proposal"},
        )
        .exclude(status="archived")
        .order_by("-updated_at", "-created_at")
        .first()
    )


def _current_opportunity_summary(opportunity: CompanyOpportunity | None) -> dict[str, Any]:
    if opportunity is None:
        return {"opportunity_id": None, "status": "unknown", "raw_status": None}
    return {
        "opportunity_id": str(opportunity.id),
        "status": _status_group(opportunity.status),
        "raw_status": opportunity.status,
    }


def _status_bucket(opportunities: Any, statuses: set[str]) -> dict[str, Any]:
    bucket_statuses = sorted(
        {
            opportunity.status
            for opportunity in opportunities
            if opportunity.status in statuses
        }
    )
    return {
        "count": sum(1 for opportunity in opportunities if opportunity.status in statuses),
        "statuses": bucket_statuses,
    }


def _status_group(status: str) -> str:
    if status in OPEN_OPPORTUNITY_STATUSES:
        return "open"
    if status in WON_OPPORTUNITY_STATUSES:
        return "won"
    if status in LOST_OPPORTUNITY_STATUSES:
        return "lost"
    return "unknown"


def _safe_text_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [text for item in value if (text := _safe_text(item))]
    text = _safe_text(value)
    return [text] if text else []


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.lower()
    if any(token in normalized for token in _BLOCKED_TEXT_TOKENS):
        return None
    return text


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    parsed = _decimal_value(value)
    if parsed is None:
        return None
    return int(parsed)


def _format_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
