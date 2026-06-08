"""Deterministic Atlas campaign package artifact builders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from statistics import mean
from typing import Any

DEFAULT_BUDGET_MODE = "bajo/sin pauta"
DEFAULT_SUCCESS_METRIC = "cotizaciones calificadas y ventas atribuibles"
DEFAULT_COMMISSION_MODEL = "success fee sobre venta atribuida"
READINESS_MINIMUM_AVERAGE = 4.0
READINESS_MINIMUM_DIMENSION_SCORE = 3


@dataclass(frozen=True)
class AtlasCampaignContext:
    business_name: str
    city_neighborhood: str
    business_type: str
    target_segment: str
    offer: str
    primary_cta: str
    primary_channel: str
    budget_mode: str = DEFAULT_BUDGET_MODE
    success_metric: str = DEFAULT_SUCCESS_METRIC
    commission_model: str = DEFAULT_COMMISSION_MODEL
    rango_precio_optional: str = "por confirmar con el cliente"


READINESS_DIMENSIONS: tuple[dict[str, str], ...] = (
    {
        "key": "segment_clarity",
        "name": "Claridad del segmento",
        "ready_evidence": "segmento estrecho, localizable y con dolor visible",
        "risk_evidence": "segmento demasiado amplio o difícil de priorizar",
    },
    {
        "key": "offer_strength",
        "name": "Fuerza de la oferta",
        "ready_evidence": "oferta concreta con resultado comprensible",
        "risk_evidence": "oferta genérica o sin motivo claro para responder",
    },
    {
        "key": "economics",
        "name": "Economía de la campaña",
        "ready_evidence": "margen y comisión permiten operar sin fricción",
        "risk_evidence": "unit economics débiles o comisión ambigua",
    },
    {
        "key": "channel_fit",
        "name": "Ajuste del canal",
        "ready_evidence": "canal usado por el comprador y apto para respuesta rápida",
        "risk_evidence": "canal no validado para el segmento",
    },
    {
        "key": "attribution",
        "name": "Atribución",
        "ready_evidence": "CTA, canal y métrica conectan el lead con la venta",
        "risk_evidence": "sin forma práctica de atribuir oportunidad o cierre",
    },
    {
        "key": "client_effort",
        "name": "Esfuerzo del cliente",
        "ready_evidence": "requiere poca participación del cliente para iniciar",
        "risk_evidence": "depende de mucha producción o aprobación del cliente",
    },
    {
        "key": "speed_to_signal",
        "name": "Velocidad a señal",
        "ready_evidence": "puede mostrar respuestas o cotizaciones en días",
        "risk_evidence": "la señal tardaría demasiado para probar retención",
    },
    {
        "key": "trust_assets",
        "name": "Activos de confianza",
        "ready_evidence": "hay prueba, catálogo, casos, reseñas o evidencia útil",
        "risk_evidence": "faltan pruebas para reducir incertidumbre",
    },
    {
        "key": "follow_up",
        "name": "Seguimiento",
        "ready_evidence": "cadencia definida para rescatar interés sin saturar",
        "risk_evidence": "sin seguimiento o con mensajes improvisados",
    },
    {
        "key": "scale_path",
        "name": "Ruta de escala",
        "ready_evidence": "hay criterio para escalar, pausar o matar la campaña",
        "risk_evidence": "sin umbrales de decisión después del piloto",
    },
)

DEFAULT_READINESS_SCORES = {
    "segment_clarity": 4,
    "offer_strength": 4,
    "economics": 4,
    "channel_fit": 4,
    "attribution": 4,
    "client_effort": 4,
    "speed_to_signal": 4,
    "trust_assets": 4,
    "follow_up": 4,
    "scale_path": 4,
}


def build_campaign_brief(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    """Build the narrow campaign brief for an Atlas local conversion package."""

    normalized = _normalize_context(context)
    return {
        "artifact_type": "campaign_brief",
        "business_name": normalized["business_name"],
        "city_neighborhood": normalized["city_neighborhood"],
        "business_type": normalized["business_type"],
        "target_segment": normalized["target_segment"],
        "offer": normalized["offer"],
        "primary_cta": normalized["primary_cta"],
        "primary_channel": normalized["primary_channel"],
        "budget_mode": normalized["budget_mode"],
        "success_metric": normalized["success_metric"],
        "commission_model": normalized["commission_model"],
        "operating_principle": (
            "Un segmento, una oferta, un CTA y un canal hasta obtener señal medible."
        ),
    }


def build_offer_sheet(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_context(context)
    objections = _as_string_list(
        normalized.get("objeciones"),
        default=[
            "No tengo tiempo para revisar esto ahora.",
            "Ya tengo proveedor o solución.",
            "Necesito saber precio antes de avanzar.",
        ],
    )
    responses = _as_string_list(
        normalized.get("respuestas"),
        default=[
            "Le mando una opción concreta para comparar sin compromiso.",
            "Perfecto; la idea es cubrir reposición, urgencias o una segunda cotización.",
            "Para cotizar bien necesito el uso, volumen aproximado y fecha objetivo.",
        ],
    )

    return {
        "artifact_type": "offer_sheet",
        "para_quien": normalized["target_segment"],
        "que_incluye": [
            normalized["offer"],
            "mensaje inicial y secuencia de seguimiento",
            "calificación básica para separar curiosos de oportunidades reales",
            "registro de CTA, fuente y resultado para atribución",
        ],
        "rango_precio_optional": normalized["rango_precio_optional"],
        "por_que_convierte": [
            f"Habla a un segmento específico: {normalized['target_segment']}.",
            f"Reduce fricción con un CTA claro: {normalized['primary_cta']}.",
            "Permite probar demanda sin depender de pauta alta ni producción pesada.",
        ],
        "objeciones": objections,
        "respuestas": responses,
        "cta": normalized["primary_cta"],
        "CTA": normalized["primary_cta"],
    }


def build_funnel_map(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_context(context)
    whatsapp_goal = (
        f"Llevar a {normalized['primary_cta']} desde "
        f"{normalized['primary_channel']}."
    )
    stages = [
        {
            "key": "descubrimiento",
            "name": "descubrimiento",
            "goal": f"Encontrar cuentas del segmento: {normalized['target_segment']}.",
            "owner": "Atlas/operator",
        },
        {
            "key": "whatsapp_landing",
            "name": "WhatsApp/landing",
            "goal": whatsapp_goal,
            "owner": "Atlas/operator",
        },
        {
            "key": "calificacion",
            "name": "calificación",
            "goal": "Confirmar necesidad, urgencia, volumen y autoridad de compra.",
            "owner": "Atlas/operator",
        },
        {
            "key": "cita_cotizacion",
            "name": "cita/cotización",
            "goal": "Convertir interés en cotización, llamada o visita con datos mínimos.",
            "owner": "cliente con soporte de Atlas",
        },
        {
            "key": "cierre",
            "name": "cierre",
            "goal": f"Registrar venta atribuible contra la métrica: {normalized['success_metric']}.",
            "owner": "cliente",
        },
        {
            "key": "postventa_resena_referido",
            "name": "postventa/reseña/referido",
            "goal": "Pedir evidencia, reseña o referido para alimentar el siguiente ciclo.",
            "owner": "cliente con soporte de Atlas",
        },
    ]

    return {
        "artifact_type": "funnel_map",
        "standard_path": (
            "descubrimiento -> WhatsApp/landing -> calificación -> cita/cotización "
            "-> cierre -> postventa/reseña/referido"
        ),
        "stages": stages,
    }


def build_scale_kill_criteria(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_context(context)
    return {
        "artifact_type": "scale_kill_criteria",
        "pilot_window": "7-14 días o hasta tener una muestra operativa suficiente",
        "scale_if": [
            f"El segmento responde al CTA: {normalized['primary_cta']}.",
            f"La oferta genera {normalized['success_metric']} con atribución clara.",
            "El scorecard mantiene promedio >= 4 y ninguna dimensión < 3.",
            "El cliente puede cumplir cotizaciones/cierres sin elevar demasiado su esfuerzo.",
        ],
        "fix_or_kill_if": [
            "El promedio del scorecard cae debajo de 4.",
            "Cualquier dimensión queda debajo de 3.",
            "No aparece señal útil después del piloto acordado.",
            "La atribución o la economía no sostienen el modelo de comisión.",
        ],
    }


def build_scripts_and_followups(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_context(context)
    business_name = normalized["business_name"]
    offer = normalized["offer"]
    cta = normalized["primary_cta"]
    segment = normalized["target_segment"]
    messages = {
        "initial_message": (
            "Hola {nombre_contacto}, soy parte del equipo de "
            f"{business_name}. Estamos ayudando a {segment} con {offer}. "
            f"Si te sirve, puedo mandarte una propuesta breve para {cta}. "
            "¿A quién se la puedo dirigir?"
        ),
        "followup_24h": (
            "Hola {nombre_contacto}, retomo el mensaje de ayer. "
            f"La idea es enviarte algo concreto de {offer}, sin compromiso y con "
            "los datos mínimos para cotizar bien. ¿Te lo mando por aquí?"
        ),
        "followup_72h": (
            "Último seguimiento por ahora, {nombre_contacto}. "
            f"Si {offer} no es prioridad esta semana, lo dejo pausado. "
            "Si sí hay interés, dime volumen aproximado y fecha objetivo para avanzar."
        ),
        "cold_lead_recovery": (
            "Hola {nombre_contacto}, vuelvo a escribir porque estamos cerrando "
            f"una ronda para {segment}. Si todavía te interesa {cta}, responde con "
            "\"cotización\" y retomamos desde ahí."
        ),
    }

    return {
        "artifact_type": "scripts_and_followups",
        "channel": normalized["primary_channel"],
        "safety_notes": [
            "Usar placeholders hasta tener datos aprobados.",
            "No incluir teléfonos falsos ni datos personales no verificados.",
            "Registrar resultados con datos mínimos, hash o redacción cuando aplique.",
        ],
        "placeholders": [
            "{nombre_contacto}",
            "{nombre_negocio}",
            "{oferta}",
            "{cta}",
            "{link_catalogo_o_pdf}",
            "{horario_preferido}",
        ],
        "initial_message": messages["initial_message"],
        "followup_24h": messages["followup_24h"],
        "followup_72h": messages["followup_72h"],
        "cold_lead_recovery": messages["cold_lead_recovery"],
        "messages": messages,
    }


def build_launch_readiness_scorecard(
    context: AtlasCampaignContext | Mapping[str, Any],
    scores: Mapping[str, int | float] | None = None,
    *,
    readiness_scores: Mapping[str, int | float] | None = None,
) -> dict[str, Any]:
    _normalize_context(context)
    score_overrides = readiness_scores if readiness_scores is not None else scores
    merged_scores = {**DEFAULT_READINESS_SCORES, **dict(score_overrides or {})}
    dimensions = []
    for dimension in READINESS_DIMENSIONS:
        score = _coerce_score(merged_scores.get(dimension["key"], 0))
        dimensions.append(
            {
                "key": dimension["key"],
                "name": dimension["name"],
                "score": score,
                "ready": score >= READINESS_MINIMUM_DIMENSION_SCORE,
                "evidence": (
                    dimension["ready_evidence"]
                    if score >= READINESS_MINIMUM_DIMENSION_SCORE
                    else dimension["risk_evidence"]
                ),
            }
        )

    average_score = round(mean(item["score"] for item in dimensions), 2)
    lowest_score = min(item["score"] for item in dimensions)
    average_gate = average_score >= READINESS_MINIMUM_AVERAGE
    floor_gate = lowest_score >= READINESS_MINIMUM_DIMENSION_SCORE
    ready = average_gate and floor_gate

    return {
        "artifact_type": "launch_readiness_scorecard",
        "scale": "1-5",
        "minimum_average": READINESS_MINIMUM_AVERAGE,
        "minimum_dimension_score": READINESS_MINIMUM_DIMENSION_SCORE,
        "average_score": average_score,
        "lowest_score": lowest_score,
        "ready": ready,
        "readiness_label": "Listo para lanzar" if ready else "No lanzar todavía",
        "gates": {
            "average_at_least_4": average_gate,
            "no_score_below_3": floor_gate,
        },
        "dimensions": dimensions,
    }


def build_campaign_package(
    context: AtlasCampaignContext | Mapping[str, Any],
    readiness_scores: Mapping[str, int | float] | None = None,
    *,
    scores: Mapping[str, int | float] | None = None,
) -> dict[str, Any]:
    campaign_brief = build_campaign_brief(context)
    offer_sheet = build_offer_sheet(context)
    funnel_map = build_funnel_map(context)
    scripts_and_followups = build_scripts_and_followups(context)
    scale_kill_criteria = build_scale_kill_criteria(context)
    launch_readiness_scorecard = build_launch_readiness_scorecard(
        context,
        readiness_scores=readiness_scores if readiness_scores is not None else scores,
    )
    package = {
        "artifact_type": "atlas_conversational_campaign_package",
        "campaign_brief": campaign_brief,
        "offer_sheet": offer_sheet,
        "funnel_map": funnel_map,
        "scripts_and_followups": scripts_and_followups,
        "scale_kill_criteria": scale_kill_criteria,
        "launch_readiness_scorecard": launch_readiness_scorecard,
    }
    package["markdown"] = render_campaign_package_markdown(package)
    return package


def render_campaign_package_markdown(
    package_or_context: Mapping[str, Any] | AtlasCampaignContext,
) -> str:
    if _is_package(package_or_context):
        package = dict(package_or_context)
    else:
        package = {
            "campaign_brief": build_campaign_brief(package_or_context),
            "offer_sheet": build_offer_sheet(package_or_context),
            "funnel_map": build_funnel_map(package_or_context),
            "scripts_and_followups": build_scripts_and_followups(package_or_context),
            "scale_kill_criteria": build_scale_kill_criteria(package_or_context),
            "launch_readiness_scorecard": build_launch_readiness_scorecard(
                package_or_context
            ),
        }

    brief = package["campaign_brief"]
    offer = package["offer_sheet"]
    funnel = package["funnel_map"]
    scripts = package["scripts_and_followups"]
    scale_kill = package.get("scale_kill_criteria") or _scale_kill_from_brief(brief)
    scorecard = package["launch_readiness_scorecard"]
    offer_cta = offer.get("cta") or offer.get("CTA")
    average_gate_result = (
        "cumple" if scorecard["gates"]["average_at_least_4"] else "no cumple"
    )
    score_floor_result = (
        "cumple" if scorecard["gates"]["no_score_below_3"] else "no cumple"
    )

    lines = [
        f"# Paquete Atlas Conversión Local IA: {brief['business_name']}",
        "",
        "## Brief de campaña",
        f"- Negocio: {brief['business_name']}",
        f"- Ubicación: {brief['city_neighborhood']}",
        f"- Tipo de negocio: {brief['business_type']}",
        f"- Segmento objetivo: {brief['target_segment']}",
        f"- Oferta: {brief['offer']}",
        f"- CTA principal: {brief['primary_cta']}",
        f"- Canal principal: {brief['primary_channel']}",
        f"- Presupuesto: {brief['budget_mode']}",
        f"- Métrica de éxito: {brief['success_metric']}",
        f"- Comisión: {brief['commission_model']}",
        "",
        "## Ficha de oferta",
        f"- Para quién: {offer['para_quien']}",
        "- Qué incluye:",
        *_bullet_lines(offer["que_incluye"], indent="  "),
        f"- Rango/precio: {offer['rango_precio_optional']}",
        "- Por qué convierte:",
        *_bullet_lines(offer["por_que_convierte"], indent="  "),
        "- Objeciones y respuestas:",
        *_paired_bullet_lines(offer["objeciones"], offer["respuestas"]),
        f"- CTA: {offer_cta}",
        "",
        "## Mapa de embudo",
        f"- Ruta estándar: {funnel['standard_path']}",
        *_stage_lines(funnel["stages"]),
        "",
        "## Scripts y seguimientos",
        "- Notas de seguridad:",
        *_bullet_lines(scripts["safety_notes"], indent="  "),
        f"- Mensaje inicial: {scripts['messages']['initial_message']}",
        f"- Seguimiento 24h: {scripts['messages']['followup_24h']}",
        f"- Seguimiento 72h: {scripts['messages']['followup_72h']}",
        f"- Recuperación de lead frío: {scripts['messages']['cold_lead_recovery']}",
        "",
        "## Scorecard de readiness",
        f"- Estado: {scorecard['readiness_label']}",
        f"- Promedio: {scorecard['average_score']} / 5",
        f"- Gate promedio >= 4: {average_gate_result}",
        f"- Gate sin dimensión < 3: {score_floor_result}",
        *_scorecard_lines(scorecard["dimensions"]),
        "",
        "## Criterio de escalar/matar",
        f"- Ventana piloto: {scale_kill['pilot_window']}",
        "- Escalar si:",
        *_bullet_lines(scale_kill["scale_if"], indent="  "),
        "- Corregir o matar si:",
        *_bullet_lines(scale_kill["fix_or_kill_if"], indent="  "),
    ]
    return "\n".join(lines).strip() + "\n"


def _normalize_context(
    context: AtlasCampaignContext | Mapping[str, Any],
) -> dict[str, Any]:
    if is_dataclass(context) and not isinstance(context, type):
        raw_context = asdict(context)
    elif isinstance(context, Mapping):
        raw_context = dict(context)
    else:
        raise TypeError("context must be a dataclass instance or mapping")

    normalized = {
        "business_name": _required_string(raw_context, "business_name"),
        "city_neighborhood": _city_neighborhood(raw_context),
        "business_type": _required_string(raw_context, "business_type"),
        "target_segment": _required_string(raw_context, "target_segment"),
        "offer": _required_string(raw_context, "offer"),
        "primary_cta": _required_string(raw_context, "primary_cta"),
        "primary_channel": _required_string(raw_context, "primary_channel"),
        "budget_mode": _optional_string(
            raw_context,
            "budget_mode",
            DEFAULT_BUDGET_MODE,
        ),
        "success_metric": _optional_string(
            raw_context,
            "success_metric",
            DEFAULT_SUCCESS_METRIC,
        ),
        "commission_model": _optional_string(
            raw_context,
            "commission_model",
            DEFAULT_COMMISSION_MODEL,
        ),
        "rango_precio_optional": _optional_string(
            raw_context,
            "rango_precio_optional",
            "por confirmar con el cliente",
            fallback_keys=("price_range_optional", "rango_precio"),
        ),
    }
    if "objeciones" in raw_context:
        normalized["objeciones"] = raw_context["objeciones"]
    if "respuestas" in raw_context:
        normalized["respuestas"] = raw_context["respuestas"]
    return normalized


def _required_string(
    raw_context: Mapping[str, Any],
    key: str,
    *,
    fallback_keys: tuple[str, ...] = (),
) -> str:
    value = raw_context.get(key)
    for fallback_key in fallback_keys:
        if value is not None and value != "":
            break
        value = raw_context.get(fallback_key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{key} is required")
    return str(value).strip()


def _optional_string(
    raw_context: Mapping[str, Any],
    key: str,
    default: str,
    *,
    fallback_keys: tuple[str, ...] = (),
) -> str:
    value = raw_context.get(key)
    for fallback_key in fallback_keys:
        if value is not None and value != "":
            break
        value = raw_context.get(fallback_key)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _as_string_list(value: Any, *, default: list[str]) -> list[str]:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else default
    if isinstance(value, set):
        items = [str(item).strip() for item in sorted(value, key=str) if str(item).strip()]
        return items or default
    try:
        items = [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        item = str(value).strip()
        return [item] if item else default
    return items or default


def _coerce_score(value: int | float) -> int | float:
    score = round(float(value), 2)
    if score < 1 or score > 5:
        raise ValueError("readiness scores must be between 1 and 5")
    return int(score) if score.is_integer() else score


def _is_package(value: Any) -> bool:
    return isinstance(value, Mapping) and "campaign_brief" in value


def _city_neighborhood(raw_context: Mapping[str, Any]) -> str:
    direct = _first_nonempty(
        raw_context,
        (
            "city_neighborhood",
            "city/neighborhood",
            "city_neighbourhood",
            "ubicacion",
            "location",
        ),
    )
    if direct:
        return direct

    city = _first_nonempty(raw_context, ("city", "ciudad"))
    neighborhood = _first_nonempty(
        raw_context,
        ("neighborhood", "neighbourhood", "colonia"),
    )
    if city and neighborhood:
        return f"{neighborhood}, {city}"
    if city:
        return city
    if neighborhood:
        return neighborhood
    raise ValueError("city_neighborhood is required")


def _first_nonempty(raw_context: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw_context.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _scale_kill_from_brief(brief: Mapping[str, Any]) -> dict[str, Any]:
    return build_scale_kill_criteria(
        {
            "business_name": brief["business_name"],
            "city_neighborhood": brief["city_neighborhood"],
            "business_type": brief["business_type"],
            "target_segment": brief["target_segment"],
            "offer": brief["offer"],
            "primary_cta": brief["primary_cta"],
            "primary_channel": brief["primary_channel"],
            "budget_mode": brief.get("budget_mode", DEFAULT_BUDGET_MODE),
            "success_metric": brief.get("success_metric", DEFAULT_SUCCESS_METRIC),
            "commission_model": brief.get("commission_model", DEFAULT_COMMISSION_MODEL),
        }
    )


def _bullet_lines(items: list[str], *, indent: str = "") -> list[str]:
    return [f"{indent}- {item}" for item in items]


def _paired_bullet_lines(objections: list[str], responses: list[str]) -> list[str]:
    lines = []
    safe_responses = responses or ["Respuesta pendiente de validar con el cliente."]
    for index, objection in enumerate(objections):
        response = (
            safe_responses[index]
            if index < len(safe_responses)
            else safe_responses[-1]
        )
        lines.append(f"  - Objeción: {objection} Respuesta: {response}")
    return lines


def _stage_lines(stages: list[dict[str, str]]) -> list[str]:
    return [f"- {stage['name']}: {stage['goal']}" for stage in stages]


def _scorecard_lines(dimensions: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {dimension['name']}: {dimension['score']} / 5. {dimension['evidence']}"
        for dimension in dimensions
    ]
