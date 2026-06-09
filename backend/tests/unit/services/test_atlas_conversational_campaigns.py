import json
import re

import pytest

from application.services.atlas_conversational_campaigns import (
    AtlasCampaignContext,
    build_campaign_brief,
    build_campaign_package,
    build_funnel_map,
    build_launch_readiness_scorecard,
    build_scale_kill_criteria,
    render_campaign_package_markdown,
)

LEGACY_CONTEXT = {
    "business_name": "Legacy Glassware",
    "city_neighborhood": "CDMX",
    "business_type": "cristalería B2B",
    "target_segment": "bares, restaurantes y hoteles boutique en CDMX",
    "offer": "paquetes de cristalería Legacy para reposición y apertura",
    "primary_cta": "solicitar cotización por WhatsApp",
    "primary_channel": "outreach directo por WhatsApp",
    "success_metric": "cotizaciones calificadas y ventas atribuibles",
    "commission_model": "20-50% de utilidad",
}

READY_SCORES = {
    "segment_clarity": 5,
    "offer_strength": 4,
    "economics": 4,
    "channel_fit": 5,
    "attribution": 4,
    "client_effort": 4,
    "speed_to_signal": 4,
    "trust_assets": 4,
    "follow_up": 4,
    "scale_path": 4,
}


def test_legacy_glassware_package_names_offer_cta_segment_and_readiness_gates():
    package = build_campaign_package(LEGACY_CONTEXT, readiness_scores=READY_SCORES)

    assert (
        package["campaign_brief"]["target_segment"]
        == "bares, restaurantes y hoteles boutique en CDMX"
    )
    assert (
        package["campaign_brief"]["offer"]
        == "paquetes de cristalería Legacy para reposición y apertura"
    )
    assert (
        package["campaign_brief"]["primary_cta"]
        == "solicitar cotización por WhatsApp"
    )
    assert package["campaign_brief"]["commission_model"] == "20-50% de utilidad"
    assert package["offer_sheet"]["para_quien"] == LEGACY_CONTEXT["target_segment"]
    assert package["offer_sheet"]["cta"] == LEGACY_CONTEXT["primary_cta"]
    assert package["offer_sheet"]["CTA"] == LEGACY_CONTEXT["primary_cta"]

    scorecard = package["launch_readiness_scorecard"]
    assert scorecard["ready"] is True
    assert scorecard["gates"] == {
        "average_at_least_4": True,
        "no_score_below_3": True,
    }
    assert scorecard["minimum_average"] == 4.0
    assert scorecard["minimum_dimension_score"] == 3

    markdown = package["markdown"]
    assert "Legacy Glassware" in markdown
    assert "bares, restaurantes y hoteles boutique en CDMX" in markdown
    assert "paquetes de cristalería Legacy para reposición y apertura" in markdown
    assert "solicitar cotización por WhatsApp" in markdown
    assert "Gate promedio >= 4: cumple" in markdown
    assert "Gate sin dimensión < 3: cumple" in markdown
    assert "Listo para lanzar" in markdown
    assert "## Criterio de escalar/matar" in markdown
    json.dumps(package, ensure_ascii=False)


def test_scripts_use_safe_placeholders_without_fake_phone_numbers():
    package = build_campaign_package(LEGACY_CONTEXT, readiness_scores=READY_SCORES)
    scripts = package["scripts_and_followups"]

    assert "{nombre_contacto}" in scripts["placeholders"]
    assert "{link_catalogo_o_pdf}" in scripts["placeholders"]
    assert "No incluir teléfonos falsos" in " ".join(scripts["safety_notes"])
    assert scripts["initial_message"] == scripts["messages"]["initial_message"]
    assert scripts["followup_24h"] == scripts["messages"]["followup_24h"]
    assert scripts["followup_72h"] == scripts["messages"]["followup_72h"]
    assert scripts["cold_lead_recovery"] == scripts["messages"]["cold_lead_recovery"]

    messages = " ".join(scripts["messages"].values())
    assert "{nombre_contacto}" in messages
    assert "cotización" in messages
    assert re.search(r"\b\d{10,}\b", messages) is None


def test_funnel_map_uses_standard_atlas_stages():
    funnel = build_funnel_map(LEGACY_CONTEXT)

    assert [
        stage["name"] for stage in funnel["stages"]
    ] == [
        "descubrimiento",
        "WhatsApp/landing",
        "calificación",
        "cita/cotización",
        "cierre",
        "postventa/reseña/referido",
    ]
    assert (
        funnel["standard_path"]
        == "descubrimiento -> WhatsApp/landing -> calificación -> cita/cotización "
        "-> cierre -> postventa/reseña/referido"
    )


def test_campaign_brief_accepts_dataclass_and_defaults_to_low_no_spend_budget():
    context = AtlasCampaignContext(
        business_name="Atlas Demo",
        city_neighborhood="Condesa, CDMX",
        business_type="servicio local",
        target_segment="administradores de edificios residenciales",
        offer="diagnóstico de fugas con visita rápida",
        primary_cta="agendar diagnóstico",
        primary_channel="WhatsApp",
    )

    brief = build_campaign_brief(context)

    assert brief["budget_mode"] == "bajo/sin pauta"
    assert brief["success_metric"] == "cotizaciones calificadas y ventas atribuibles"
    assert brief["commission_model"] == "success fee sobre venta atribuida"
    json.dumps(brief, ensure_ascii=False)


def test_context_accepts_city_neighborhood_key_variant_and_scale_kill_payload():
    context = {
        **LEGACY_CONTEXT,
        "city_neighborhood": "",
        "city/neighborhood": "Roma Norte, CDMX",
    }

    brief = build_campaign_brief(context)
    criteria = build_scale_kill_criteria(context)

    assert brief["city_neighborhood"] == "Roma Norte, CDMX"
    assert criteria["artifact_type"] == "scale_kill_criteria"
    assert "promedio >= 4" in " ".join(criteria["scale_if"])
    assert "debajo de 3" in " ".join(criteria["fix_or_kill_if"])


def test_context_accepts_split_city_neighborhood_and_empty_response_override():
    context = {
        **LEGACY_CONTEXT,
        "city_neighborhood": "",
        "city/neighborhood": "",
        "city": "CDMX",
        "neighborhood": "Polanco",
        "objeciones": ["¿Me puedes mandar precio primero?"],
        "respuestas": [],
    }

    package = build_campaign_package(context, readiness_scores=READY_SCORES)

    assert package["campaign_brief"]["city_neighborhood"] == "Polanco, CDMX"
    assert package["offer_sheet"]["objeciones"] == [
        "¿Me puedes mandar precio primero?"
    ]
    assert package["offer_sheet"]["respuestas"]
    assert "Polanco, CDMX" in package["markdown"]


def test_markdown_renderer_accepts_package_without_scale_kill_payload():
    package = build_campaign_package(LEGACY_CONTEXT, readiness_scores=READY_SCORES)
    partial_package = {
        key: value
        for key, value in package.items()
        if key not in {"markdown", "scale_kill_criteria"}
    }
    partial_package["offer_sheet"] = {
        key: value
        for key, value in package["offer_sheet"].items()
        if key != "cta"
    }

    markdown = render_campaign_package_markdown(partial_package)

    assert "CTA: solicitar cotización por WhatsApp" in markdown
    assert "## Criterio de escalar/matar" in markdown


def test_readiness_scorecard_requires_average_and_no_dimension_below_three():
    scorecard = build_launch_readiness_scorecard(
        LEGACY_CONTEXT,
        scores={
            **READY_SCORES,
            "trust_assets": 2,
            "follow_up": 5,
            "scale_path": 5,
        },
    )

    assert scorecard["average_score"] >= 4
    assert scorecard["lowest_score"] == 2
    assert scorecard["ready"] is False
    assert scorecard["gates"]["average_at_least_4"] is True
    assert scorecard["gates"]["no_score_below_3"] is False
    assert scorecard["readiness_label"] == "No lanzar todavía"


def test_readiness_scorecard_rejects_scores_outside_one_to_five():
    with pytest.raises(ValueError, match="between 1 and 5"):
        build_launch_readiness_scorecard(LEGACY_CONTEXT, scores={"economics": 6})
