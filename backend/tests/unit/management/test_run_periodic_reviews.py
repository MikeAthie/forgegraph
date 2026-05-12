from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import call_command

from application.services.operating_model_packs import install_pack_for_company
from application.services.periodic_reviews import (
    create_metric_snapshot,
    current_due_review_period,
)
from infrastructure.orm.models import (
    CompanySignal,
    Graph,
    MetricSnapshot,
    PeriodicReviewDefinition,
    ReportRun,
)

pytestmark = pytest.mark.django_db


def _company(user, name: str = "Periodic Command Co") -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=user.default_organization,
            name=name,
            description="Run periodic review command tests.",
        ),
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


def _values() -> dict[str, Any]:
    return {
        "social_engagement_rate": 0.7,
        "roas": 3.5,
        "cost_per_lead_services": {"level": "acceptable"},
        "cac_vs_profit": {"level": "good"},
        "publishing_frequency": 18,
    }


def _run_command(*args: str) -> dict[str, Any]:
    output = StringIO()
    call_command("run_periodic_reviews", *args, stdout=output)
    payload = json.loads(output.getvalue())
    assert isinstance(payload, dict)
    return payload


def test_run_periodic_reviews_due_executes_due_review_with_snapshot(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    period = current_due_review_period(review)
    snapshot = create_metric_snapshot(
        company=company,
        user=user,
        review_definition=review,
        period_start=period.period_start,
        period_end=period.period_end,
        metric_values=_values(),
        source_type="manual",
    )

    payload = _run_command("--due", "--company-id", str(company.id), "--json")

    assert payload["error_count"] == 0
    assert payload["executions"][0]["metric_snapshot_id"] == str(snapshot.id)
    assert payload["executions"][0]["report_run_id"]
    assert ReportRun.objects.filter(company=company).count() == 1


def test_run_periodic_reviews_skips_duplicates_and_force_reruns(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    period = current_due_review_period(review)
    create_metric_snapshot(
        company=company,
        user=user,
        review_definition=review,
        period_start=period.period_start,
        period_end=period.period_end,
        metric_values=_values(),
        source_type="manual",
    )
    first = _run_command("--due", "--company-id", str(company.id), "--json")
    second = _run_command("--due", "--company-id", str(company.id), "--json")
    forced = _run_command(
        "--review-definition-id",
        str(review.id),
        "--period-start",
        period.period_start.isoformat(),
        "--period-end",
        period.period_end.isoformat(),
        "--force",
        "--json",
    )

    assert first["created_or_skipped_count"] == 1
    assert second["executions"] == []
    assert forced["executions"][0]["status"] == "completed"
    assert ReportRun.objects.filter(company=company).count() == 2


def test_run_periodic_reviews_dry_run_does_not_persist_report(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    period = current_due_review_period(review)
    create_metric_snapshot(
        company=company,
        user=user,
        review_definition=review,
        period_start=period.period_start,
        period_end=period.period_end,
        metric_values=_values(),
        source_type="manual",
    )

    payload = _run_command(
        "--review-definition-id",
        str(review.id),
        "--period-start",
        period.period_start.isoformat(),
        "--period-end",
        period.period_end.isoformat(),
        "--dry-run",
        "--json",
    )

    assert payload["executions"][0]["status"] == "dry_run_ready"
    assert ReportRun.objects.filter(company=company).count() == 0


def test_run_periodic_reviews_creates_missing_input_signal(user):
    company = _company(user)
    review = _atlas_review(company=company, user=user)
    period = current_due_review_period(review)

    payload = _run_command(
        "--review-definition-id",
        str(review.id),
        "--period-start",
        period.period_start.isoformat(),
        "--period-end",
        period.period_end.isoformat(),
        "--json",
    )

    assert payload["executions"][0]["status"] == "blocked"
    assert payload["executions"][0]["blockers"]
    assert CompanySignal.objects.filter(
        company=company,
        source="periodic_review_input_gap",
    ).exists()
    assert MetricSnapshot.objects.filter(company=company).count() == 0
