from application.services.atlas_weekly_reports import (
    BOTTLENECK_NO_QUOTES,
    BOTTLENECK_NO_REPLIES,
    BOTTLENECK_SCALE,
    build_atlas_weekly_report,
)


def _section(report, title):
    return next(
        section
        for section in report["client_report"]["sections"]
        if section["title"] == title
    )


def test_no_reply_scenario_recommends_segment_message_channel_not_spend():
    report = build_atlas_weekly_report(
        campaign_summary={"name": "Atlas retencion"},
        activity_list=[
            {
                "count": 80,
                "description": "prospectos contactados",
                "channel": "WhatsApp aprobado",
            }
        ],
        funnel_metrics_by_stage={"contacted": 80, "replies": 0},
        lead_revenue_commission_summary={"commission": 0},
        blockers_approvals_needed=[],
    )

    assert report["diagnosis"]["bottleneck"] == BOTTLENECK_NO_REPLIES
    assert report["operator_payload"]["recommendation"] == "iterate"

    operator_text = " ".join(
        report["operator_payload"]["next_actions"]
        + report["operator_payload"]["guardrails"]
        + [report["operator_payload"]["rationale"]]
    ).lower()
    assert "segmento" in operator_text
    assert "mensaje" in operator_text
    assert "canal" in operator_text
    assert "no aumentar presupuesto" in operator_text
    assert "meter mas gasto" not in operator_text


def test_qualified_no_sales_scenario_diagnoses_trust_pricing_sales_process():
    report = build_atlas_weekly_report(
        campaign_summary={"name": "Atlas citas"},
        activity_list=[{"description": "seguimiento a leads calificados"}],
        funnel_metrics_by_stage={
            "contacted": 120,
            "replies": 30,
            "qualified": 14,
            "quotes": 0,
            "wins": 0,
        },
        lead_revenue_commission_summary={"commission": 0},
        blockers_approvals_needed=["Confirmar rango de precios"],
    )

    assert report["diagnosis"]["bottleneck"] == BOTTLENECK_NO_QUOTES

    report_text = " ".join(
        line
        for section in report["client_report"]["sections"]
        for line in section["body"]
    ).lower()
    assert "cierre" in report_text
    assert "confianza" in report_text
    assert "precio" in report_text


def test_wins_scenario_recommends_scale_with_guardrails():
    report = build_atlas_weekly_report(
        campaign_summary={"name": "Atlas winback"},
        activity_list=[{"description": "reactivacion de clientes dormidos"}],
        funnel_metrics_by_stage={
            "contacted": 90,
            "replies": 24,
            "qualified": 12,
            "quotes": 5,
            "wins": 2,
        },
        lead_revenue_commission_summary={
            "revenue": 28000,
            "commission": 2800,
            "currency": "MXN",
            "economics_acceptable": True,
        },
        blockers_approvals_needed=[],
    )

    assert report["diagnosis"]["bottleneck"] == BOTTLENECK_SCALE
    assert report["operator_payload"]["recommendation"] == "scale"

    guardrails = " ".join(report["operator_payload"]["guardrails"]).lower()
    assert "costo por lead" in guardrails
    assert "success fee" in guardrails


def test_report_includes_explicit_next_actions_and_commission_summary():
    report = build_atlas_weekly_report(
        campaign_summary={"name": "Atlas semanal"},
        activity_list=[{"description": "secuencia de seguimiento"}],
        funnel_metrics_by_stage={
            "contacted": 60,
            "replies": 15,
            "qualified": 7,
            "citas": 3,
            "wins": 1,
        },
        lead_revenue_commission_summary={
            "leads": 7,
            "sales": 1,
            "revenue": 15000,
            "commission": 1500,
            "currency": "MXN",
            "attribution": "venta confirmada por el negocio",
        },
        blockers_approvals_needed=["Aprobar lista de segmentos de la semana siguiente"],
    )

    next_actions = _section(report, "Qué cambiaremos la próxima semana")["body"]
    commission = _section(report, "Leads/ventas/comisión")["body"]

    assert len(next_actions) >= 2
    assert all(action.endswith(".") for action in next_actions)
    assert any(
        "Comisión / success fee estimada: MXN 1,500." == line
        for line in commission
    )
    assert any("Ingreso atribuido: MXN 15,000." == line for line in commission)
    assert any("Base de atribución" in line for line in commission)
