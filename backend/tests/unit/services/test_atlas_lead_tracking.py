from __future__ import annotations

import pytest

from application.services.atlas_lead_tracking import (
    AtlasLeadTrackingError,
    build_lead_record,
    build_lead_tracking_report,
    export_lead_tracker_csv,
    render_commission_statement_markdown,
)


def test_legacy_profit_share_example_tracks_won_sale_and_open_quote() -> None:
    leads = [
        build_lead_record(
            lead_id="legacy-won-001",
            prospect_name="Dormant project",
            source="legacy_reactivation",
            channel="operator",
            campaign_id="legacy-q2",
            status="won",
            attribution="atlas_sourced",
            revenue_collected="100000.00",
            direct_cost="40000.00",
            commission_rate="0.50",
            evidence_notes="Factura cobrada y utilidad acordada.",
        ),
        build_lead_record(
            lead_id="legacy-quote-002",
            prospect_company="Optica Centro",
            source="legacy_reactivation",
            channel="email",
            campaign_id="legacy-q2",
            status="quoted",
            attribution="atlas_sourced",
            next_action="Confirmar aceptacion de cotizacion.",
        ),
    ]

    report = build_lead_tracking_report(leads)
    markdown = render_commission_statement_markdown(report, client_name="Legacy")
    csv_payload = export_lead_tracker_csv(report)

    assert report["summary"]["total_leads"] == 2
    assert report["summary"]["quoted"] == 1
    assert report["summary"]["won"] == 1
    assert report["summary"]["revenue_collected"] == "100000.00"
    assert report["summary"]["profit"] == "60000.00"
    assert report["summary"]["commission_due"] == "30000.00"
    assert report["summary"]["open_followups"] == 1
    assert report["open_followups"][0]["lead_id"] == "legacy-quote-002"
    assert report["attribution_breakdown"]["atlas_sourced"]["total_leads"] == 2
    assert "## Ventas cerradas" in markdown
    assert "$30,000.00" in markdown
    assert csv_payload.splitlines()[0].startswith("lead_id,prospect_name,company")


def test_conservative_baseline_uses_20_percent_commission() -> None:
    lead = build_lead_record(
        lead_id="baseline-001",
        status="won",
        attribution="atlas_sourced",
        revenue_collected="1000.00",
        direct_cost="400.00",
    )

    assert lead["estimated_profit"] == 600.0
    assert lead["commission_rate"] == 0.2
    assert lead["commission_due"] == 120.0


def test_negative_or_zero_profit_never_produces_commission() -> None:
    negative_profit = build_lead_record(
        lead_id="loss-001",
        status="won",
        attribution="atlas_sourced",
        revenue_collected="500.00",
        direct_cost="800.00",
    )
    zero_estimated_profit = build_lead_record(
        lead_id="zero-001",
        status="won",
        attribution="atlas_sourced",
        revenue_collected="1000.00",
        direct_cost="100.00",
        estimated_profit="0.00",
    )

    report = build_lead_tracking_report([negative_profit, zero_estimated_profit])

    assert negative_profit["estimated_profit"] == -300.0
    assert negative_profit["commission_due"] == 0.0
    assert zero_estimated_profit["commission_due"] == 0.0
    assert report["summary"]["commission_due"] == "0.00"


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(AtlasLeadTrackingError) as exc:
        build_lead_record(
            lead_id="bad-001",
            status="closed",
            attribution="atlas_sourced",
        )

    assert exc.value.code == "invalid_status"


def test_markdown_redacts_phone_like_values_from_sensitive_metadata() -> None:
    raw_phone = "+52 55 1234 5678"
    lead = build_lead_record(
        lead_id="pii-001",
        prospect_name="Cliente sensible",
        status="qualified",
        attribution="unknown",
        evidence_notes=f"Contacto por telefono {raw_phone}.",
        metadata={"phone": raw_phone, "note": f"Llamar al {raw_phone}"},
    )

    markdown = render_commission_statement_markdown([lead])

    assert raw_phone not in markdown
    assert raw_phone not in str(lead["metadata"])
    assert "[phone_sha256:" in markdown
    assert "## Partidas en disputa o desconocidas" in markdown
