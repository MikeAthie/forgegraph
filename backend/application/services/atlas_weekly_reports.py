"""Deterministic Atlas weekly retention report artifact builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

NumberLike = int | float | Decimal | str | None
Payload = Mapping[str, Any]


BOTTLENECK_NO_REPLIES = "segment_message_channel"
BOTTLENECK_LOW_QUALIFIED = "offer_targeting"
BOTTLENECK_NO_QUOTES = "trust_pricing_sales_process"
BOTTLENECK_NO_WINS = "closing_fulfillment_economics"
BOTTLENECK_SCALE = "scale"


def build_atlas_weekly_report(
    *,
    campaign_summary: Payload | None = None,
    activity_list: Sequence[Payload] | None = None,
    funnel_metrics_by_stage: Payload | None = None,
    lead_revenue_commission_summary: Payload | None = None,
    blockers_approvals_needed: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build the client report and operator payload for an Atlas retention week.

    Inputs stay as plain dictionaries so this artifact can be produced without
    coupling Atlas reporting to campaign, lead, provider-send, or DB services.
    """

    campaign_summary = campaign_summary or {}
    activity_list = activity_list or []
    funnel_metrics_by_stage = funnel_metrics_by_stage or {}
    lead_revenue_commission_summary = lead_revenue_commission_summary or {}
    blockers_approvals_needed = blockers_approvals_needed or []

    funnel = _normalize_funnel(funnel_metrics_by_stage, lead_revenue_commission_summary)
    economics_acceptable = _economics_are_acceptable(lead_revenue_commission_summary)
    bottleneck = diagnose_funnel_bottleneck(funnel, lead_revenue_commission_summary)
    next_actions = _next_actions_for_bottleneck(bottleneck)
    commission_summary = _commission_summary(lead_revenue_commission_summary, funnel)

    client_sections = [
        {
            "title": "Qué hicimos esta semana",
            "body": _activity_lines(activity_list, campaign_summary),
        },
        {
            "title": "Qué resultados vimos",
            "body": _results_lines(funnel, lead_revenue_commission_summary),
        },
        {
            "title": "Qué aprendimos",
            "body": _learning_lines(bottleneck),
        },
        {
            "title": "Dónde se atoró el funnel",
            "body": [_bottleneck_client_line(bottleneck, funnel)],
        },
        {
            "title": "Qué cambiaremos la próxima semana",
            "body": next_actions,
        },
        {
            "title": "Leads/ventas/comisión",
            "body": commission_summary,
        },
        {
            "title": "Qué necesitamos aprobar o confirmar",
            "body": _approval_lines(blockers_approvals_needed),
        },
    ]

    recommendation = _operator_recommendation(
        bottleneck,
        funnel=funnel,
        economics_acceptable=economics_acceptable,
    )

    return {
        "artifact_type": "atlas_weekly_retention_report",
        "campaign_summary": dict(campaign_summary),
        "diagnosis": {
            "bottleneck": bottleneck,
            "label": _bottleneck_label(bottleneck),
            "reason": _bottleneck_client_line(bottleneck, funnel),
        },
        "client_report": {
            "tone": "concise_owner_friendly",
            "sections": client_sections,
        },
        "operator_payload": {
            "recommendation": recommendation["recommendation"],
            "rationale": recommendation["rationale"],
            "next_actions": next_actions,
            "guardrails": recommendation["guardrails"],
            "funnel": funnel,
        },
    }


def diagnose_funnel_bottleneck(
    funnel_metrics_by_stage: Payload | None,
    lead_revenue_commission_summary: Payload | None = None,
) -> str:
    """Return the deterministic Atlas bottleneck code for a weekly funnel."""

    funnel = _normalize_funnel(
        funnel_metrics_by_stage or {},
        lead_revenue_commission_summary or {},
    )
    economics_ok = _economics_are_acceptable(lead_revenue_commission_summary or {})

    if funnel["replies"] <= 0:
        return BOTTLENECK_NO_REPLIES
    if funnel["qualified"] <= 0 or _rate(funnel["qualified"], funnel["replies"]) < 0.35:
        return BOTTLENECK_LOW_QUALIFIED
    if funnel["quotes_or_appointments"] <= 0:
        return BOTTLENECK_NO_QUOTES
    if funnel["wins"] <= 0:
        return BOTTLENECK_NO_WINS
    if economics_ok:
        return BOTTLENECK_SCALE
    return BOTTLENECK_NO_WINS


def _normalize_funnel(
    funnel_metrics_by_stage: Payload,
    lead_revenue_commission_summary: Payload,
) -> dict[str, int]:
    contacted = _stage_value(
        funnel_metrics_by_stage,
        "contacted",
        "contacts",
        "sent",
        "outreach",
        "prospects",
        "enviados",
    )
    replies = _stage_value(
        funnel_metrics_by_stage,
        "replies",
        "reply",
        "responses",
        "respuestas",
    )
    qualified = _stage_value(
        funnel_metrics_by_stage,
        "qualified",
        "qualified_leads",
        "leads_qualified",
        "calificados",
    )
    quotes = _stage_value(
        funnel_metrics_by_stage,
        "quotes",
        "quote_requests",
        "quotes_or_appointments",
        "appointments",
        "citas",
        "proposals",
        "cotizaciones",
    )
    wins = _stage_value(
        funnel_metrics_by_stage,
        "wins",
        "sales",
        "closed_won",
        "ventas",
    )

    qualified = qualified or _stage_value(
        lead_revenue_commission_summary,
        "qualified",
        "qualified_leads",
        "leads_qualified",
    )
    wins = wins or _stage_value(
        lead_revenue_commission_summary,
        "wins",
        "sales",
        "new_customers",
        "new_business_count",
    )

    return {
        "contacted": contacted,
        "replies": replies,
        "qualified": qualified,
        "quotes_or_appointments": quotes,
        "wins": wins,
    }


def _stage_value(payload: Payload, *aliases: str) -> int:
    for alias in aliases:
        if alias not in payload:
            continue
        raw_value = payload[alias]
        if isinstance(raw_value, Mapping):
            raw_value = (
                raw_value.get("count")
                or raw_value.get("value")
                or raw_value.get("total")
                or raw_value.get("current")
            )
        value = _to_decimal(raw_value)
        if value is not None:
            return max(0, int(value))
    return 0


def _to_decimal(value: NumberLike) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def _economics_are_acceptable(summary: Payload) -> bool:
    explicit = summary.get("economics_acceptable")
    if explicit is not None:
        return bool(explicit)

    roi = _to_decimal(summary.get("roi") or summary.get("return_on_investment"))
    if roi is not None:
        return roi >= Decimal("1")

    revenue = _to_decimal(
        summary.get("revenue")
        or summary.get("new_business_revenue")
        or summary.get("sales_value")
    )
    commission = _to_decimal(summary.get("commission") or summary.get("success_fee"))
    if revenue is not None and commission is not None:
        return revenue > commission and commission >= 0

    return True


def _activity_lines(
    activity_list: Sequence[Payload],
    campaign_summary: Payload,
) -> list[str]:
    if not activity_list:
        campaign_name = campaign_summary.get("name") or campaign_summary.get("campaign_name")
        if campaign_name:
            return [
                f"Operamos la campaña {campaign_name} y medimos el avance "
                "del funnel."
            ]
        return ["Operamos la campaña y medimos el avance del funnel."]

    lines = []
    for activity in activity_list:
        description = _first_text(activity, "description", "summary", "name", "action")
        count = activity.get("count") or activity.get("total")
        channel = _first_text(activity, "channel", "canal")
        result = _first_text(activity, "result", "outcome", "resultado")

        parts = []
        if count:
            parts.append(str(count))
        if description:
            parts.append(description)
        if channel:
            parts.append(f"vía {channel}")
        line = " ".join(parts).strip()
        if result:
            line = f"{line}: {result}" if line else result
        if line:
            lines.append(_sentence(line))

    return lines or ["Operamos la campaña y medimos el avance del funnel."]


def _results_lines(funnel: Payload, summary: Payload) -> list[str]:
    revenue = _money_value(summary, "revenue", "new_business_revenue", "sales_value")
    commission = _money_value(summary, "commission", "success_fee")
    lines = [
        (
            f"{funnel['contacted']} contactos, {funnel['replies']} respuestas, "
            f"{funnel['qualified']} leads calificados, "
            f"{funnel['quotes_or_appointments']} cotizaciones/citas y {funnel['wins']} ventas."
        )
    ]
    if revenue != "0":
        lines.append(f"Nuevo negocio reportado: {revenue}.")
    if commission != "0":
        lines.append(f"Comisión atribuible: {commission}.")
    return lines


def _learning_lines(bottleneck: str) -> list[str]:
    return {
        BOTTLENECK_NO_REPLIES: [
            "La prioridad no es meter más gasto; hay que cambiar segmento, "
            "mensaje o canal hasta provocar respuestas."
        ],
        BOTTLENECK_LOW_QUALIFIED: [
            "El mercado sí responde, pero la calidad cae; hay que ajustar "
            "oferta y targeting."
        ],
        BOTTLENECK_NO_QUOTES: [
            "Si hay leads calificados y no avanzan a cita o cotización, falta "
            "confianza, precio claro o proceso comercial de cierre."
        ],
        BOTTLENECK_NO_WINS: [
            "Las citas o cotizaciones llegan, pero no cierran; revisaremos "
            "cierre, cumplimiento prometido y economía de la oferta."
        ],
        BOTTLENECK_SCALE: [
            "La campaña ya generó ventas con economía aceptable; conviene "
            "escalar con límites claros."
        ],
    }[bottleneck]


def _bottleneck_client_line(bottleneck: str, funnel: Payload) -> str:
    if bottleneck == BOTTLENECK_NO_WINS and funnel["wins"] > 0:
        return (
            "El funnel ya produjo venta, pero la economía no permite escalar "
            "sin ajustar precio, margen o promesa de cumplimiento."
        )

    return {
        BOTTLENECK_NO_REPLIES: (
            "Se atoró antes de la respuesta: el segmento, mensaje o canal no "
            "generó conversación suficiente."
        ),
        BOTTLENECK_LOW_QUALIFIED: (
            "Se atoró en calificación: hubo respuestas, pero pocas personas "
            "cumplieron el perfil de compra."
        ),
        BOTTLENECK_NO_QUOTES: (
            "Se atoró antes de cita/cotización: existen leads calificados, "
            "pero falta confianza, precio claro o proceso comercial de cierre."
        ),
        BOTTLENECK_NO_WINS: (
            "Se atoró en cierre: hubo citas o cotizaciones, pero no se "
            "convirtieron en ventas."
        ),
        BOTTLENECK_SCALE: (
            f"El funnel ya produjo {funnel['wins']} venta(s) con economía "
            "aceptable; el siguiente riesgo es escalar sin perder calidad."
        ),
    }[bottleneck]


def _next_actions_for_bottleneck(bottleneck: str) -> list[str]:
    return {
        BOTTLENECK_NO_REPLIES: [
            "Probar un segmento alterno con el mismo volumen base.",
            "Reescribir el primer mensaje con una prueba de valor más concreta.",
            "Mover el canal principal solo después de comparar tasa de "
            "respuesta.",
        ],
        BOTTLENECK_LOW_QUALIFIED: [
            "Endurecer criterios de ICP antes de contactar.",
            "Ajustar la oferta para filtrar por necesidad, presupuesto y urgencia.",
            "Separar respuestas curiosas de oportunidades listas para venta.",
        ],
        BOTTLENECK_NO_QUOTES: [
            "Agregar prueba social y expectativas de precio antes de pedir cita.",
            "Reducir fricción del siguiente paso con una cita corta o "
            "cotización guiada.",
            "Dar seguimiento a cada lead calificado con una razón concreta "
            "para avanzar.",
        ],
        BOTTLENECK_NO_WINS: [
            "Revisar objeciones de cierre y ajustar guión comercial.",
            "Validar que precio, margen y promesa de fulfillment sean "
            "sostenibles.",
            "Priorizar leads con dolor urgente antes de ampliar volumen.",
        ],
        BOTTLENECK_SCALE: [
            "Subir volumen gradualmente manteniendo el mismo ICP ganador.",
            "Mantener tope de costo por lead y pausar segmentos que bajen "
            "calidad.",
            "Duplicar solo los mensajes y canales que ya generaron venta "
            "atribuible.",
        ],
    }[bottleneck]


def _commission_summary(summary: Payload, funnel: Payload) -> list[str]:
    leads = _stage_value(summary, "leads", "lead_count") or funnel["qualified"]
    sales = _stage_value(summary, "sales", "wins", "new_business_count") or funnel["wins"]
    revenue = _money_value(summary, "revenue", "new_business_revenue", "sales_value")
    commission = _money_value(summary, "commission", "success_fee")
    attribution = _first_text(summary, "attribution", "attribution_basis", "basis")

    lines = [
        f"Leads calificados: {leads}.",
        f"Ventas o nuevo negocio: {sales}.",
        f"Ingreso atribuido: {revenue}.",
        f"Comisión / success fee estimada: {commission}.",
    ]
    if attribution:
        lines.append(_sentence(f"Base de atribución: {attribution}"))
    return lines


def _approval_lines(blockers_approvals_needed: Sequence[Any]) -> list[str]:
    lines = []
    for item in blockers_approvals_needed:
        if isinstance(item, Mapping):
            text = _first_text(item, "description", "summary", "name", "approval", "blocker")
        else:
            text = str(item).strip()
        if text:
            lines.append(_sentence(text))
    return lines or [
        "Sin aprobaciones pendientes; seguiremos con el plan de la próxima semana."
    ]


def _operator_recommendation(
    bottleneck: str,
    *,
    funnel: Payload,
    economics_acceptable: bool,
) -> dict[str, Any]:
    if (
        bottleneck == BOTTLENECK_NO_WINS
        and funnel["wins"] > 0
        and not economics_acceptable
    ):
        return {
            "recommendation": "kill",
            "rationale": (
                "Hay venta atribuible, pero la economía no sostiene success fee "
                "ni escala rentable."
            ),
            "guardrails": [
                "No escalar hasta corregir precio, margen o fulfillment.",
                "Cerrar esta variante si no se puede recuperar economía.",
            ],
        }

    payloads = {
        BOTTLENECK_NO_REPLIES: {
            "recommendation": "iterate",
            "rationale": (
                "No hay evidencia para aumentar gasto; primero hay que generar "
                "respuesta."
            ),
            "guardrails": [
                "No aumentar presupuesto hasta recuperar tasa de respuesta.",
                "Cambiar una variable por prueba: segmento, mensaje o canal.",
            ],
        },
        BOTTLENECK_LOW_QUALIFIED: {
            "recommendation": "iterate",
            "rationale": (
                "La respuesta existe, pero la calidad no sostiene ventas."
            ),
            "guardrails": [
                "No optimizar por volumen bruto de respuestas.",
                "Medir calificados sobre respuestas por segmento.",
            ],
        },
        BOTTLENECK_NO_QUOTES: {
            "recommendation": "iterate",
            "rationale": (
                "Hay demanda calificada; el avance depende de confianza, "
                "precio y proceso comercial de cierre."
            ),
            "guardrails": [
                "No ampliar volumen hasta destrabar citas o cotizaciones.",
                "Registrar motivo de no avance sin guardar mensajes sensibles.",
            ],
        },
        BOTTLENECK_NO_WINS: {
            "recommendation": "iterate",
            "rationale": (
                "El cuello de botella está en cierre o economía, no en "
                "adquisición."
            ),
            "guardrails": [
                "No escalar canales hasta cerrar al menos una venta atribuible.",
                "Validar margen antes de prometer descuentos o tiempos de entrega.",
            ],
        },
        BOTTLENECK_SCALE: {
            "recommendation": "scale",
            "rationale": "Hay ventas atribuibles con economía aceptable.",
            "guardrails": [
                "Escalar por incrementos semanales controlados.",
                "Mantener limites de costo por lead, calidad y success fee.",
            ],
        },
    }
    return payloads[bottleneck]


def _money_value(summary: Payload, *aliases: str) -> str:
    for alias in aliases:
        value = _to_decimal(summary.get(alias))
        if value is not None:
            currency = summary.get("currency", "MXN")
            return f"{currency} {_format_decimal(value)}"
    return "0"


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _first_text(payload: Payload, *aliases: str) -> str:
    for alias in aliases:
        value = payload.get(alias)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text[-1] in ".!?":
        return text
    return f"{text}."


def _bottleneck_label(bottleneck: str) -> str:
    return {
        BOTTLENECK_NO_REPLIES: "Sin respuestas",
        BOTTLENECK_LOW_QUALIFIED: "Baja calificación",
        BOTTLENECK_NO_QUOTES: "Sin citas/cotizaciones",
        BOTTLENECK_NO_WINS: "Sin cierres",
        BOTTLENECK_SCALE: "Escalar",
    }[bottleneck]
