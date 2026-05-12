from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest

from application.services.operating_model_packs import install_pack_for_company
from application.services.periodic_reviews import (
    current_due_review_period,
    due_periodic_reviews,
    execute_periodic_review,
    metric_input_blockers,
    next_review_period,
    upsert_review_definition_from_template,
)
from infrastructure.orm.models import (
    CompanySignal,
    Graph,
    MetricSnapshot,
    PeriodicReviewDefinition,
    ReportRun,
)

pytestmark = pytest.mark.django_db


def _company(user, name: str = "Periodic Review Co") -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=user.default_organization,
            name=name,
            description="Run generic periodic reviews.",
        ),
    )


def _review(
    *,
    company: Graph,
    user,
    cadence: str,
    template_id: str,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> PeriodicReviewDefinition:
    return upsert_review_definition_from_template(
        company=company,
        user=user,
        template={
            "id": template_id,
            "display_name": template_id.replace("_", " ").title(),
            "cadence": cadence,
            "timezone": "America/Mexico_City",
            "enabled": enabled,
            **(metadata or {}),
        },
    )


def _atlas_review(*, company: Graph, user) -> PeriodicReviewDefinition:
    install_pack_for_company(
        company=company,
        user=user,
        pack_id="digital_marketing_pro.v1",
        config={},
    )
    return PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )


def _metric_values() -> dict[str, Any]:
    return {
        "social_engagement_rate": 0.7,
        "roas": 3.2,
        "website_bounce_rate": 55,
        "cost_per_lead_services": {
            "level": "acceptable",
            "notes": "Manual profitability level for the review period.",
        },
        "cac_vs_profit": {"level": "good"},
        "publishing_frequency": 18,
    }


def test_due_period_calculation_supports_common_cadences(user):
    company = _company(user)
    weekly = _review(company=company, user=user, cadence="weekly", template_id="weekly")
    monthly = _review(company=company, user=user, cadence="monthly", template_id="monthly")
    quarterly = _review(company=company, user=user, cadence="quarterly", template_id="quarterly")
    custom = _review(
        company=company,
        user=user,
        cadence="custom",
        template_id="custom",
        metadata={"custom_period_days": 10, "anchor_date": "2026-05-01"},
    )

    assert current_due_review_period(weekly, as_of=date(2026, 5, 12)).as_payload() == {
        "period_start": "2026-05-04",
        "period_end": "2026-05-10",
        "cadence": "weekly",
        "timezone": "America/Mexico_City",
    }
    assert current_due_review_period(monthly, as_of=date(2026, 5, 12)).period_start == date(
        2026, 4, 1
    )
    assert next_review_period(monthly, as_of=date(2026, 5, 12)).period_end == date(2026, 5, 31)
    assert current_due_review_period(quarterly, as_of=date(2026, 5, 12)).period_start == date(
        2026, 1, 1
    )
    custom_period = current_due_review_period(custom, as_of=date(2026, 5, 22))
    assert custom_period.period_start == date(2026, 5, 11)
    assert custom_period.period_end == date(2026, 5, 20)


def test_due_periodic_reviews_skip_disabled_and_existing_reports(user):
    company = _company(user)
    due_review = _review(company=company, user=user, cadence="monthly", template_id="due_review")
    completed = _review(
        company=company, user=user, cadence="monthly", template_id="completed_review"
    )
    _review(
        company=company,
        user=user,
        cadence="monthly",
        template_id="disabled_review",
        enabled=False,
    )
    period = current_due_review_period(completed, as_of=date(2026, 5, 12))
    ReportRun.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        review_definition=completed,
        report_template_id="test_report",
        period_start=period.period_start,
        period_end=period.period_end,
        created_by=user,
    )

    due = due_periodic_reviews(company=company, as_of=date(2026, 5, 12))

    assert [review.template_id for review, _period in due] == [due_review.template_id]


def test_execute_periodic_review_creates_snapshot_evaluation_report_and_summary(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    summary = execute_periodic_review(
        review=review,
        user=user,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        metric_values=_metric_values(),
        source_type="manual",
    )

    assert summary.status == "completed"
    assert summary.metric_snapshot_id
    assert summary.evaluation_run_ids
    assert summary.report_run_id
    assert summary.artifact_id
    assert summary.history_projection_id
    assert "dmp.campaign_performance_review" in summary.recommended_operation_template_ids
    assert MetricSnapshot.objects.filter(company=company).count() == 1
    assert ReportRun.objects.filter(company=company).count() == 1
    assert CompanySignal.objects.filter(company=company, source="evaluation_scorecard").exists()


def test_execute_periodic_review_is_idempotent_and_force_creates_new_run(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    snapshot = MetricSnapshot.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        review_definition=review,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        metric_values_json=_metric_values(),
        metric_sources_json={},
        source_type="manual",
        created_by=user,
    )

    first = execute_periodic_review(review=review, user=user, metric_snapshot=snapshot)
    second = execute_periodic_review(review=review, user=user, metric_snapshot=snapshot)
    forced = execute_periodic_review(
        review=review,
        user=user,
        metric_snapshot=snapshot,
        force=True,
    )

    assert first.status == "completed"
    assert second.status == "skipped_duplicate"
    assert second.skipped is True
    assert second.report_run_id == first.report_run_id
    assert forced.status == "completed"
    assert forced.report_run_id != first.report_run_id
    assert ReportRun.objects.filter(company=company).count() == 2


def test_execute_periodic_review_missing_metrics_creates_generic_input_signal(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)

    summary = execute_periodic_review(
        review=review,
        user=user,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )

    assert summary.status == "blocked"
    assert summary.blockers
    assert summary.signal_ids
    signal = CompanySignal.objects.get(id=summary.signal_ids[0])
    assert signal.source == "periodic_review_input_gap"
    assert signal.metadata_json["blockers"][0]["type"] == "metric_input_required"
    assert ReportRun.objects.filter(company=company).count() == 0


def test_metric_input_blockers_detect_missing_contextual_inputs(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)

    blockers = metric_input_blockers(
        review=review,
        metric_values={"cost_per_lead_services": {"value": 120}},
    )

    assert blockers
    assert blockers[0]["metric_id"] == "cost_per_lead_services"
    assert "average_ticket" in blockers[0]["missing"]


def test_execute_periodic_review_dry_run_does_not_persist_outputs(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)

    summary = execute_periodic_review(
        review=review,
        user=user,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        metric_values=_metric_values(),
        dry_run=True,
    )

    assert summary.status == "dry_run_ready"
    assert summary.dry_run is True
    assert MetricSnapshot.objects.filter(company=company).count() == 0
    assert ReportRun.objects.filter(company=company).count() == 0
