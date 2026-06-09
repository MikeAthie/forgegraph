"""Deterministic Atlas lead, profit, and commission artifact builders."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from application.services.redaction import REDACTED_VALUE

CONTRACT_VERSION = "atlas_lead_tracking.v1"
LEAD_STATUSES = (
    "prospect",
    "contacted",
    "replied",
    "qualified",
    "quoted",
    "won",
    "lost",
)
LEAD_ATTRIBUTIONS = (
    "atlas_sourced",
    "manual_referral",
    "client_existing",
    "unknown",
)
VALID_STATUSES = LEAD_STATUSES
VALID_ATTRIBUTIONS = LEAD_ATTRIBUTIONS
DEFAULT_COMMISSION_RATE = Decimal("0.20")
MAX_COMMISSION_RATE = Decimal("0.50")
CSV_COLUMNS = (
    "lead_id",
    "prospect_name",
    "company",
    "source",
    "channel",
    "campaign_id",
    "status",
    "attribution",
    "revenue_collected",
    "direct_cost",
    "estimated_profit",
    "commission_rate",
    "commission_due",
    "evidence_notes",
    "next_action",
)

_MONEY_QUANT = Decimal("0.01")
_RATE_QUANT = Decimal("0.0001")
_CLOSED_STATUSES = {"won", "lost"}
_QUALIFIED_STATUSES = {"qualified", "quoted", "won"}
_PHONE_LIKE_PATTERN = re.compile(r"(?<![\w])(?:\+?\d[\d\s().-]{7,}\d)(?![\w])")
_METADATA_REDACT_KEY_TOKENS = (
    "body",
    "message",
    "mensaje",
    "mobile",
    "phone",
    "raw",
    "telefono",
    "whatsapp",
)


class AtlasLeadTrackingError(ValueError):
    """Safe domain error for Atlas lead tracking payloads."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AtlasLeadRecord:
    lead_id: str
    prospect_name: str | None
    company: str | None
    source: str
    channel: str
    campaign_id: str
    status: str
    attribution: str
    revenue_collected: float
    direct_cost: float
    estimated_profit: float
    commission_rate: float
    commission_due: float
    evidence_notes: str
    next_action: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "lead_id": self.lead_id,
            "prospect_name": self.prospect_name,
            "company": self.company,
            "prospect_company": self.company,
            "source": self.source,
            "channel": self.channel,
            "campaign_id": self.campaign_id,
            "status": self.status,
            "attribution": self.attribution,
            "revenue_collected": self.revenue_collected,
            "direct_cost": self.direct_cost,
            "estimated_profit": self.estimated_profit,
            "commission_rate": self.commission_rate,
            "commission_due": self.commission_due,
            "evidence_notes": self.evidence_notes,
            "next_action": self.next_action,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.as_payload()[key]


def normalize_lead_status(status: object) -> str:
    return _normalize_choice(status, allowed=LEAD_STATUSES, field_name="status")


def normalize_lead_attribution(attribution: object) -> str:
    return _normalize_choice(
        attribution,
        allowed=LEAD_ATTRIBUTIONS,
        field_name="attribution",
    )


def build_atlas_lead_record(
    *,
    lead_id: object,
    status: object,
    attribution: object = "unknown",
    prospect_name: object | None = None,
    company: object | None = None,
    prospect_company: object | None = None,
    source: object = "",
    channel: object = "",
    campaign_id: object = "",
    revenue_collected: object = 0,
    direct_cost: object = 0,
    estimated_profit: object | None = None,
    commission_rate: object | None = None,
    evidence_notes: object = "",
    next_action: object = "",
    metadata: Mapping[str, Any] | None = None,
) -> AtlasLeadRecord:
    revenue = _non_negative_money(revenue_collected, field_name="revenue_collected")
    cost = _non_negative_money(direct_cost, field_name="direct_cost")
    profit = (
        _money(estimated_profit, field_name="estimated_profit")
        if estimated_profit is not None
        else revenue - cost
    )
    rate = _commission_rate(commission_rate)
    commission_due = max(profit, Decimal("0")) * rate

    return AtlasLeadRecord(
        lead_id=_required_text(lead_id, field_name="lead_id"),
        prospect_name=_optional_text(prospect_name),
        company=_optional_text(company if company is not None else prospect_company),
        source=_text(source),
        channel=_text(channel),
        campaign_id=_text(campaign_id),
        status=normalize_lead_status(status),
        attribution=normalize_lead_attribution(attribution),
        revenue_collected=_money_payload(revenue),
        direct_cost=_money_payload(cost),
        estimated_profit=_money_payload(profit),
        commission_rate=_rate_payload(rate),
        commission_due=_money_payload(commission_due),
        evidence_notes=_text(evidence_notes),
        next_action=_text(next_action),
        metadata=_redact_metadata(dict(metadata or {})),
    )


def build_lead_record(**kwargs: Any) -> AtlasLeadRecord:
    return build_atlas_lead_record(**kwargs)


def normalize_lead_record(record: Mapping[str, Any]) -> AtlasLeadRecord:
    return build_atlas_lead_record(
        lead_id=record.get("lead_id"),
        prospect_name=record.get("prospect_name"),
        company=record.get("company"),
        prospect_company=record.get("prospect_company"),
        source=record.get("source", ""),
        channel=record.get("channel", ""),
        campaign_id=record.get("campaign_id", ""),
        status=record.get("status"),
        attribution=record.get("attribution", "unknown"),
        revenue_collected=record.get("revenue_collected", 0),
        direct_cost=record.get("direct_cost", 0),
        estimated_profit=record.get("estimated_profit"),
        commission_rate=record.get("commission_rate"),
        evidence_notes=record.get("evidence_notes", ""),
        next_action=record.get("next_action", ""),
        metadata=_metadata_from_record(record),
    )


def lead_record_payload(record: AtlasLeadRecord | Mapping[str, Any]) -> dict[str, Any]:
    return _coerce_record(record).as_payload()


def build_atlas_lead_tracking_report(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    lead_records = [_coerce_record(record) for record in _records_from_input(records)]
    status_counts = dict.fromkeys(LEAD_STATUSES, 0)
    attribution_breakdown = _empty_attribution_breakdown()
    open_followups: list[dict[str, str]] = []

    revenue = Decimal("0")
    profit = Decimal("0")
    commission_due = Decimal("0")
    for record in lead_records:
        status_counts[record.status] += 1
        revenue += _money(record.revenue_collected, field_name="revenue_collected")
        profit += _money(record.estimated_profit, field_name="estimated_profit")
        commission_due += _money(record.commission_due, field_name="commission_due")
        _add_to_attribution_breakdown(attribution_breakdown, record)
        if record.next_action and record.status not in _CLOSED_STATUSES:
            open_followups.append(
                {
                    "lead_id": record.lead_id,
                    "status": record.status,
                    "next_action": record.next_action,
                }
            )

    open_followup_count = len(open_followups)
    summary = {
        "total_leads": len(lead_records),
        "qualified": status_counts["qualified"],
        "quoted": status_counts["quoted"],
        "won": status_counts["won"],
        "lost": status_counts["lost"],
        "revenue_collected": _money_string(revenue),
        "revenue": _money_string(revenue),
        "profit": _money_string(profit),
        "commission_due": _money_string(commission_due),
        "open_followups": open_followup_count,
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "summary": summary,
        "total_leads": len(lead_records),
        "qualified": status_counts["qualified"],
        "quoted": status_counts["quoted"],
        "won": status_counts["won"],
        "lost": status_counts["lost"],
        "revenue": _money_payload(revenue),
        "profit": _money_payload(profit),
        "commission_due": _money_payload(commission_due),
        "open_followup_count": open_followup_count,
        "open_followups": open_followups,
        "status_counts": status_counts,
        "attribution_breakdown": _finalize_attribution_breakdown(attribution_breakdown),
        "leads": [record.as_payload() for record in lead_records],
    }


def build_lead_tracking_report(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    return build_atlas_lead_tracking_report(records)


def build_commission_statement_markdown(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
    *,
    client_name: str = "Cliente",
) -> str:
    lead_records = [_coerce_record(record) for record in _records_from_input(records)]
    report = build_atlas_lead_tracking_report(lead_records)
    qualified_records = [record for record in lead_records if record.status in _QUALIFIED_STATUSES]
    won_records = [record for record in lead_records if record.status == "won"]
    disputed_records = _disputed_or_unknown_records(lead_records)

    lines = [
        f"# Estado de comisiones Atlas - {_text(client_name)}",
        "",
        "## Resumen",
        f"- Leads registrados: {report['total_leads']}",
        f"- Leads calificados: {len(qualified_records)}",
        f"- Ventas cerradas: {report['won']}",
        f"- Ingresos cobrados: {_format_money(report['revenue'])}",
        f"- Utilidad estimada: {_format_money(report['profit'])}",
        f"- Comision por pagar: {_format_money(report['commission_due'])}",
        "",
        "## Leads",
    ]
    _append_markdown_table(lines, lead_records)
    lines.extend(["", "## Leads calificados"])
    _append_markdown_table(lines, qualified_records)
    lines.extend(["", "## Ventas cerradas"])
    _append_markdown_table(lines, won_records)
    lines.extend(
        [
            "",
            "## Supuestos de utilidad",
            "- La utilidad se calcula como ingresos cobrados menos costo directo.",
            "- Cuando se captura utilidad estimada, esa cifra reemplaza el calculo anterior.",
            "- La comision nunca se calcula sobre utilidad negativa.",
            "",
            "## Comision por pagar",
            f"- Total: {_format_money(report['commission_due'])}",
            "- Tasa base conservadora: 20%. Casos Legacy pueden usar hasta 50%.",
            "",
            "## Partidas en disputa o desconocidas",
        ]
    )
    _append_markdown_table(lines, disputed_records)
    return "\n".join(lines).strip() + "\n"


def build_markdown_commission_statement(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]],
    *,
    client_name: str = "Cliente",
) -> str:
    return build_commission_statement_markdown(records, client_name=client_name)


def render_commission_statement_markdown(
    records_or_report: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
    *,
    client_name: str = "Cliente",
    period_label: str = "",
    currency: str = "MXN",
) -> str:
    del period_label, currency
    return build_commission_statement_markdown(
        _records_from_input(records_or_report),
        client_name=client_name,
    )


def export_atlas_lead_tracking_csv(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in (_coerce_record(item) for item in _records_from_input(records)):
        payload = record.as_payload()
        writer.writerow({column: payload.get(column, "") for column in CSV_COLUMNS})
    return output.getvalue()


def export_lead_tracking_csv(
    records: Iterable[AtlasLeadRecord | Mapping[str, Any]],
) -> str:
    return export_atlas_lead_tracking_csv(records)


def export_lead_tracker_csv(
    records_or_report: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
) -> str:
    return export_atlas_lead_tracking_csv(_records_from_input(records_or_report))


build_report_payload = build_lead_tracking_report
export_leads_csv = export_lead_tracker_csv


def _records_from_input(
    records_or_report: Iterable[AtlasLeadRecord | Mapping[str, Any]] | Mapping[str, Any],
) -> Iterable[AtlasLeadRecord | Mapping[str, Any]]:
    if isinstance(records_or_report, Mapping):
        leads = records_or_report.get("leads")
        if isinstance(leads, list):
            return leads
        if "lead_id" in records_or_report:
            return [records_or_report]
    return records_or_report  # type: ignore[return-value]


def _normalize_choice(value: object, *, allowed: tuple[str, ...], field_name: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in allowed:
        raise AtlasLeadTrackingError(
            f"invalid_{field_name}",
            f"Invalid Atlas lead {field_name}.",
        )
    return normalized


def _coerce_record(record: AtlasLeadRecord | Mapping[str, Any]) -> AtlasLeadRecord:
    if isinstance(record, AtlasLeadRecord):
        return record
    if isinstance(record, Mapping):
        return normalize_lead_record(record)
    raise AtlasLeadTrackingError("invalid_record", "Atlas lead record is required.")


def _metadata_from_record(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    metadata = record.get("metadata")
    return metadata if isinstance(metadata, Mapping) else None


def _money(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise AtlasLeadTrackingError(
            f"invalid_{field_name}",
            f"Invalid Atlas lead {field_name}.",
        )
    try:
        cleaned = re.sub(r"[^0-9.\-]", "", str(value).strip())
        if cleaned in {"", "-", ".", "-."}:
            raise InvalidOperation
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise AtlasLeadTrackingError(
            f"invalid_{field_name}",
            f"Invalid Atlas lead {field_name}.",
        ) from None
    if not amount.is_finite():
        raise AtlasLeadTrackingError(
            f"invalid_{field_name}",
            f"Invalid Atlas lead {field_name}.",
        )
    return amount


def _non_negative_money(value: object, *, field_name: str) -> Decimal:
    amount = _money(value, field_name=field_name)
    if amount < 0:
        raise AtlasLeadTrackingError(
            f"invalid_{field_name}",
            f"Invalid Atlas lead {field_name}.",
        )
    return amount


def _commission_rate(value: object | None) -> Decimal:
    if value is None:
        return DEFAULT_COMMISSION_RATE
    text = str(value).strip()
    rate = _money(value, field_name="commission_rate")
    if text.endswith("%") or rate > 1:
        rate = rate / Decimal("100")
    if rate < 0 or rate > MAX_COMMISSION_RATE:
        raise AtlasLeadTrackingError(
            "commission_rate_out_of_range",
            "Invalid Atlas lead commission_rate.",
        )
    return rate


def _money_payload(value: Decimal | int) -> float:
    return float(Decimal(value).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP))


def _rate_payload(value: Decimal) -> float:
    return float(value.quantize(_RATE_QUANT, rounding=ROUND_HALF_UP))


def _text(value: object) -> str:
    return _redact_phone_like_text(str(value or "").strip())


def _required_text(value: object, *, field_name: str) -> str:
    cleaned = _text(value)
    if not cleaned:
        raise AtlasLeadTrackingError(
            f"{field_name}_required",
            f"Invalid Atlas lead {field_name}.",
        )
    return cleaned


def _optional_text(value: object | None) -> str | None:
    cleaned = _text(value)
    return cleaned or None


def _redact_phone_like_text(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_value = match.group(0)
        digits = re.sub(r"\D", "", raw_value)
        if len(digits) < 10:
            return raw_value
        digest = hashlib.sha256(digits.encode("utf-8")).hexdigest()[:12]
        return f"[phone_sha256:{digest}]"

    return _PHONE_LIKE_PATTERN.sub(replace, value)


def _redact_metadata(value: Any, *, field_name: str | None = None) -> Any:
    if field_name and _metadata_key_is_sensitive(field_name):
        return REDACTED_VALUE
    if isinstance(value, Mapping):
        return {str(key): _redact_metadata(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, str):
        return _redact_phone_like_text(value)
    return value


def _metadata_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return any(token in normalized for token in _METADATA_REDACT_KEY_TOKENS)


def _empty_attribution_breakdown() -> dict[str, dict[str, Decimal | int]]:
    return {
        attribution: {
            "total_leads": 0,
            "revenue": Decimal("0"),
            "profit": Decimal("0"),
            "commission_due": Decimal("0"),
        }
        for attribution in LEAD_ATTRIBUTIONS
    }


def _add_to_attribution_breakdown(
    breakdown: dict[str, dict[str, Decimal | int]],
    record: AtlasLeadRecord,
) -> None:
    bucket = breakdown[record.attribution]
    bucket["total_leads"] = int(bucket["total_leads"]) + 1
    bucket["revenue"] = Decimal(bucket["revenue"]) + _money(
        record.revenue_collected,
        field_name="revenue",
    )
    bucket["profit"] = Decimal(bucket["profit"]) + _money(
        record.estimated_profit,
        field_name="profit",
    )
    bucket["commission_due"] = Decimal(bucket["commission_due"]) + _money(
        record.commission_due,
        field_name="commission_due",
    )


def _finalize_attribution_breakdown(
    breakdown: dict[str, dict[str, Decimal | int]],
) -> dict[str, dict[str, float | int]]:
    return {
        attribution: {
            "total_leads": int(values["total_leads"]),
            "revenue": _money_payload(values["revenue"]),
            "profit": _money_payload(values["profit"]),
            "commission_due": _money_payload(values["commission_due"]),
        }
        for attribution, values in breakdown.items()
    }


def _money_string(value: object) -> str:
    amount = _money(value, field_name="money").quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _format_money(value: object) -> str:
    amount = _money(value, field_name="money").quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return f"${amount:,.2f}"


def _append_markdown_table(lines: list[str], records: list[AtlasLeadRecord]) -> None:
    if not records:
        lines.append("Sin partidas.")
        return
    lines.extend(
        [
            "| Lead | Estado | Atribucion | Ingresos | Utilidad | Comision | Evidencia | Siguiente accion |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for record in records:
        lines.append(_markdown_row(record))


def _markdown_row(record: AtlasLeadRecord) -> str:
    label_parts = [record.lead_id]
    if record.prospect_name:
        label_parts.append(record.prospect_name)
    if record.company:
        label_parts.append(record.company)
    label = " / ".join(label_parts)
    return (
        f"| {_markdown_cell(label)} "
        f"| {record.status} "
        f"| {record.attribution} "
        f"| {_format_money(record.revenue_collected)} "
        f"| {_format_money(record.estimated_profit)} "
        f"| {_format_money(record.commission_due)} "
        f"| {_markdown_cell(record.evidence_notes or 'Sin evidencia')} "
        f"| {_markdown_cell(record.next_action or 'Sin accion abierta')} |"
    )


def _markdown_cell(value: str) -> str:
    return _redact_phone_like_text(value).replace("|", "\\|")


def _disputed_or_unknown_records(records: list[AtlasLeadRecord]) -> list[AtlasLeadRecord]:
    return [
        record
        for record in records
        if record.attribution == "unknown" or not record.evidence_notes.strip()
    ]


__all__ = [
    "AtlasLeadRecord",
    "CSV_COLUMNS",
    "DEFAULT_COMMISSION_RATE",
    "LEAD_ATTRIBUTIONS",
    "LEAD_STATUSES",
    "MAX_COMMISSION_RATE",
    "build_atlas_lead_record",
    "build_atlas_lead_tracking_report",
    "build_commission_statement_markdown",
    "build_lead_record",
    "build_lead_tracking_report",
    "build_markdown_commission_statement",
    "export_atlas_lead_tracking_csv",
    "export_lead_tracking_csv",
    "lead_record_payload",
    "normalize_lead_attribution",
    "normalize_lead_record",
    "normalize_lead_status",
]
