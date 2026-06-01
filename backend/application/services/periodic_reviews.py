"""Generic periodic review, metric snapshot, and report run services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.company_ops import create_company_signal
from application.services.evaluations import evaluation_payload, run_evaluation
from application.services.state_projections import (
    materialize_current_truth_projection,
    materialize_service_history_projection,
)
from application.services.work_artifacts import artifact_payload, create_work_artifact
from infrastructure.orm.models import (
    Asset,
    CompanyProgram,
    EvaluationProfile,
    EvaluationRun,
    Graph,
    MetricSnapshot,
    PeriodicReviewDefinition,
    ReportRun,
    StateProjection,
    User,
)


class PeriodicReviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ReviewPeriod:
    period_start: date
    period_end: date
    cadence: str
    timezone: str

    def as_payload(self) -> dict[str, str]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "cadence": self.cadence,
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class PeriodicReviewExecutionSummary:
    review_definition_id: str
    period_start: str
    period_end: str
    metric_snapshot_id: str = ""
    evaluation_run_ids: tuple[str, ...] = ()
    report_run_id: str = ""
    artifact_id: str = ""
    artifact_revision_id: str = ""
    history_projection_id: str = ""
    signal_ids: tuple[str, ...] = ()
    recommended_operation_template_ids: tuple[str, ...] = ()
    blockers: tuple[dict[str, Any], ...] = ()
    skipped: bool = False
    dry_run: bool = False
    status: str = "completed"

    def as_payload(self) -> dict[str, Any]:
        return {
            "review_definition_id": self.review_definition_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "metric_snapshot_id": self.metric_snapshot_id,
            "evaluation_run_ids": list(self.evaluation_run_ids),
            "report_run_id": self.report_run_id,
            "artifact_id": self.artifact_id,
            "artifact_revision_id": self.artifact_revision_id,
            "history_projection_id": self.history_projection_id,
            "signal_ids": list(self.signal_ids),
            "recommended_operation_template_ids": list(self.recommended_operation_template_ids),
            "blockers": list(self.blockers),
            "skipped": self.skipped,
            "dry_run": self.dry_run,
            "status": self.status,
        }


def upsert_review_definition_from_template(
    *,
    company: Graph,
    user: User,
    template: dict[str, Any],
    pack_id: str = "",
    program: CompanyProgram | None = None,
) -> PeriodicReviewDefinition:
    """Create or update a company review definition from pack metadata."""

    template_id = _safe_key(template.get("id"))
    if not template_id:
        raise PeriodicReviewError("missing_template_id", "Review template is missing an id.")
    profile_key = _safe_key(template.get("evaluation_profile_id"))
    profile = (
        EvaluationProfile.objects.filter(company=company, profile_id=profile_key).first()
        if profile_key
        else None
    )
    defaults = {
        "organization": company.organization,
        "program": program,
        "pack_id": _safe_key(pack_id),
        "display_name": _safe_text(template.get("display_name") or template.get("label"), 255)
        or template_id,
        "cadence": _safe_choice(
            template.get("cadence"),
            {"weekly", "monthly", "quarterly", "custom"},
            "monthly",
        ),
        "timezone": _safe_text(template.get("timezone"), 64) or "UTC",
        "evaluation_profile": profile,
        "evaluation_profile_key": profile_key,
        "report_template_id": _safe_key(template.get("report_template_id")),
        "history_projection_type": _safe_key(template.get("history_projection_type")),
        "enabled": bool(template.get("enabled", True)),
        "metadata_json": {
            "template": _json_dict(template),
            "report_template": _json_dict(template.get("report_template")),
            "source_pack_id": _safe_key(pack_id),
        },
        "created_by": user,
    }
    review, _ = PeriodicReviewDefinition.objects.update_or_create(
        company=company,
        template_id=template_id,
        program=program,
        defaults=defaults,
    )
    return review


def current_due_review_period(
    review: PeriodicReviewDefinition,
    *,
    as_of: date | datetime | None = None,
) -> ReviewPeriod:
    """Return the latest completed review period for this definition."""

    today = _local_date(review=review, as_of=as_of)
    cadence = _safe_choice(review.cadence, {"weekly", "monthly", "quarterly", "custom"}, "monthly")
    if cadence == "weekly":
        current_start = today - timedelta(days=today.weekday())
        return ReviewPeriod(
            period_start=current_start - timedelta(days=7),
            period_end=current_start - timedelta(days=1),
            cadence=cadence,
            timezone=review.timezone or "UTC",
        )
    if cadence == "quarterly":
        current_start = _quarter_start(today)
        previous_start = _add_months(current_start, -3)
        return ReviewPeriod(
            period_start=previous_start,
            period_end=current_start - timedelta(days=1),
            cadence=cadence,
            timezone=review.timezone or "UTC",
        )
    if cadence == "custom":
        return _custom_due_period(review=review, today=today)
    current_start = date(today.year, today.month, 1)
    previous_start = _add_months(current_start, -1)
    return ReviewPeriod(
        period_start=previous_start,
        period_end=current_start - timedelta(days=1),
        cadence=cadence,
        timezone=review.timezone or "UTC",
    )


def next_review_period(
    review: PeriodicReviewDefinition,
    *,
    as_of: date | datetime | None = None,
) -> ReviewPeriod:
    """Return the review period immediately after the current due period."""

    return _advance_period(review=review, period=current_due_review_period(review, as_of=as_of))


def review_has_report_for_period(
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
) -> bool:
    return _existing_report_run(review=review, period=period) is not None


def due_periodic_reviews(
    *,
    company: Graph | None = None,
    review_definition_id: str | None = None,
    as_of: date | datetime | None = None,
    force: bool = False,
) -> list[tuple[PeriodicReviewDefinition, ReviewPeriod]]:
    """List enabled review definitions whose current due period has no report run."""

    queryset = PeriodicReviewDefinition.objects.select_related("company", "program").filter(
        enabled=True
    )
    if company is not None:
        queryset = queryset.filter(company=company)
    if review_definition_id:
        queryset = queryset.filter(id=review_definition_id)
    due: list[tuple[PeriodicReviewDefinition, ReviewPeriod]] = []
    for review in queryset:
        period = current_due_review_period(review, as_of=as_of)
        if force or not review_has_report_for_period(review, period):
            due.append((review, period))
    return due


def create_metric_snapshot(
    *,
    company: Graph,
    user: User,
    period_start: date,
    period_end: date,
    metric_values: dict[str, Any],
    metric_sources: dict[str, Any] | None = None,
    source_type: str = "manual",
    notes: str = "",
    program: CompanyProgram | None = None,
    review_definition: PeriodicReviewDefinition | None = None,
) -> MetricSnapshot:
    if period_end < period_start:
        raise PeriodicReviewError("invalid_period", "Review period end cannot precede start.")
    if review_definition is not None and review_definition.company_id != company.id:
        raise PeriodicReviewError(
            "review_company_mismatch", "Review definition is not for this company."
        )
    snapshot = MetricSnapshot.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        program=program,
        review_definition=review_definition,
        period_start=period_start,
        period_end=period_end,
        metric_values_json=_json_dict(metric_values),
        metric_sources_json=_json_dict(metric_sources),
        source_type=_safe_choice(
            source_type,
            {"connector", "manual", "imported", "computed", "seed"},
            "manual",
        ),
        notes=_safe_text(notes, 4000),
        created_by=user,
    )
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="metric_snapshot.created",
        resource_type="metric_snapshot",
        resource_id=str(snapshot.id),
        metadata={
            "company_id": str(company.id),
            "program_id": str(program.id) if program else None,
            "review_definition_id": str(review_definition.id) if review_definition else None,
        },
    )
    return snapshot


def execute_periodic_review(
    *,
    review: PeriodicReviewDefinition,
    user: User,
    period_start: date | None = None,
    period_end: date | None = None,
    metric_snapshot: MetricSnapshot | None = None,
    metric_snapshot_id: str | None = None,
    metric_values: dict[str, Any] | None = None,
    metric_sources: dict[str, Any] | None = None,
    source_type: str = "manual",
    notes: str = "",
    force: bool = False,
    dry_run: bool = False,
    as_of: date | datetime | None = None,
) -> PeriodicReviewExecutionSummary:
    """Execute one generic periodic review period.

    This is the backend-owned orchestration layer for the recurring cycle:
    period -> metric snapshot -> evaluation -> report artifact -> history/state.
    """

    if not review.enabled:
        raise PeriodicReviewError("review_disabled", "Periodic review is disabled.")
    if metric_values is not None and not isinstance(metric_values, dict):
        raise PeriodicReviewError("invalid_metric_values", "Metric values must be a JSON object.")

    snapshot = metric_snapshot or _metric_snapshot_by_id(
        review=review, metric_snapshot_id=metric_snapshot_id
    )
    period = _execution_period(
        review=review,
        snapshot=snapshot,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
    )
    existing_report = _existing_report_run(review=review, period=period)
    if existing_report is not None and not force:
        return _summary_from_report(
            review=review,
            report=existing_report,
            period=period,
            status="skipped_duplicate",
            skipped=True,
            dry_run=dry_run,
        )

    if snapshot is None and metric_values is None:
        snapshot = _latest_metric_snapshot_for_period(review=review, period=period)
    if snapshot is not None:
        _assert_snapshot_usable(review=review, snapshot=snapshot, period=period)

    effective_metrics = (
        snapshot.metric_values_json
        if snapshot is not None and isinstance(snapshot.metric_values_json, dict)
        else _json_dict(metric_values)
    )
    blockers = metric_input_blockers(review=review, metric_values=effective_metrics)
    if blockers:
        return _blocked_review_summary(
            review=review,
            period=period,
            user=user,
            snapshot=snapshot,
            blockers=blockers,
            dry_run=dry_run,
        )

    if dry_run:
        return _dry_run_review_summary(review=review, period=period, snapshot=snapshot)

    if snapshot is None:
        snapshot = create_metric_snapshot(
            company=review.company,
            program=review.program,
            review_definition=review,
            user=user,
            period_start=period.period_start,
            period_end=period.period_end,
            metric_values=effective_metrics,
            metric_sources=metric_sources or {},
            source_type=source_type,
            notes=notes,
        )

    with transaction.atomic():
        evaluation = (
            run_evaluation(
                company=review.company,
                user=user,
                profile_id=review.evaluation_profile_key,
                program=snapshot.program or review.program,
                input_refs=[
                    {"type": "periodic_review_definition", "id": str(review.id)},
                    {"type": "metric_snapshot", "id": str(snapshot.id)},
                ],
                inputs={
                    "metric_snapshot_id": str(snapshot.id),
                    "review_definition_id": str(review.id),
                    "period_start": snapshot.period_start.isoformat(),
                    "period_end": snapshot.period_end.isoformat(),
                    "metrics": snapshot.metric_values_json,
                },
            )
            if review.evaluation_profile_key
            else None
        )
        report_run = assemble_report_run(
            review=review,
            metric_snapshot=snapshot,
            evaluation=evaluation,
            user=user,
            notes=notes,
            force=force,
        )

    program = snapshot.program or review.program
    history_projection = None
    if review.history_projection_type:
        history_projection = materialize_service_history_projection(
            company=review.company,
            program=program,
            projection_type=review.history_projection_type,
            display_label=_history_label(review),
        )
    materialize_current_truth_projection(company=review.company, program=program)
    return _summary_from_report(
        review=review,
        report=report_run,
        period=period,
        history_projection_id=str(history_projection.id) if history_projection else "",
        status="completed",
    )


def _blocked_review_summary(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
    user: User,
    snapshot: MetricSnapshot | None,
    blockers: list[dict[str, Any]],
    dry_run: bool,
) -> PeriodicReviewExecutionSummary:
    blocker_signal = None
    if not dry_run:
        blocker_signal = _upsert_metric_input_required_signal(
            review=review,
            period=period,
            user=user,
            blockers=blockers,
        )
    return PeriodicReviewExecutionSummary(
        review_definition_id=str(review.id),
        period_start=period.period_start.isoformat(),
        period_end=period.period_end.isoformat(),
        metric_snapshot_id=str(snapshot.id) if snapshot is not None else "",
        signal_ids=(str(blocker_signal.id),) if blocker_signal is not None else (),
        blockers=tuple(blockers),
        dry_run=dry_run,
        status="blocked",
    )


def _dry_run_review_summary(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
    snapshot: MetricSnapshot | None,
) -> PeriodicReviewExecutionSummary:
    return PeriodicReviewExecutionSummary(
        review_definition_id=str(review.id),
        period_start=period.period_start.isoformat(),
        period_end=period.period_end.isoformat(),
        metric_snapshot_id=str(snapshot.id) if snapshot is not None else "",
        dry_run=True,
        status="dry_run_ready",
    )


def run_periodic_review(
    *,
    review: PeriodicReviewDefinition,
    metric_snapshot: MetricSnapshot,
    user: User,
    notes: str = "",
) -> tuple[EvaluationRun, ReportRun]:
    summary = execute_periodic_review(
        review=review,
        metric_snapshot=metric_snapshot,
        user=user,
        notes=notes,
    )
    if not summary.evaluation_run_ids:
        raise PeriodicReviewError(
            "missing_evaluation_profile", "Review is missing an evaluation profile."
        )
    evaluation = EvaluationRun.objects.get(id=summary.evaluation_run_ids[0])
    report = ReportRun.objects.get(id=summary.report_run_id)
    return evaluation, report


def assemble_report_run(
    *,
    review: PeriodicReviewDefinition,
    metric_snapshot: MetricSnapshot,
    evaluation: EvaluationRun | None,
    user: User,
    notes: str = "",
    force: bool = False,
) -> ReportRun:
    program = metric_snapshot.program or review.program
    report_template = _report_template(review)
    artifact_schema_id = (
        _safe_key(report_template.get("artifact_schema_id"))
        or _safe_key(report_template.get("artifact_type"))
        or "periodic_report"
    )
    report_template_id = _safe_key(review.report_template_id) or _safe_key(
        report_template.get("id")
    )
    sections = _report_sections(
        review=review,
        metric_snapshot=metric_snapshot,
        evaluation=evaluation,
        report_template=report_template,
        notes=notes,
    )
    asset, revision = create_work_artifact(
        company=review.company,
        program=program,
        user=user,
        title=f"{review.display_name} {metric_snapshot.period_start:%Y-%m}",
        artifact_type=artifact_schema_id,
        content=sections,
        metadata={
            "periodic_review_definition_id": str(review.id),
            "metric_snapshot_id": str(metric_snapshot.id),
            "evaluation_run_id": str(evaluation.id) if evaluation is not None else "",
            "report_template_id": report_template_id,
            "period_start": metric_snapshot.period_start.isoformat(),
            "period_end": metric_snapshot.period_end.isoformat(),
        },
        source_key=(
            f"periodic-report:{review.company_id}:{review.id}:"
            f"{metric_snapshot.period_start.isoformat()}:{metric_snapshot.period_end.isoformat()}"
        ),
    )
    defaults = {
        "organization": review.company.organization,
        "program": program,
        "period_start": metric_snapshot.period_start,
        "period_end": metric_snapshot.period_end,
        "artifact": asset,
        "artifact_revision": revision,
        "evaluation_run_ids_json": [str(evaluation.id)] if evaluation is not None else [],
        "generated_sections_json": sections,
        "source_refs_json": _report_source_refs(
            metric_snapshot=metric_snapshot,
            evaluation=evaluation,
            asset=asset,
        ),
        "created_by": user,
    }
    if force:
        run = ReportRun.objects.create(
            company=review.company,
            review_definition=review,
            metric_snapshot=metric_snapshot,
            report_template_id=report_template_id,
            **defaults,
        )
    else:
        run, _ = ReportRun.objects.update_or_create(
            company=review.company,
            review_definition=review,
            metric_snapshot=metric_snapshot,
            report_template_id=report_template_id,
            defaults=defaults,
        )
    record_audit_log(
        actor=user,
        tenant_id=str(review.company.organization_id),
        action="report_run.created",
        resource_type="report_run",
        resource_id=str(run.id),
        metadata={
            "company_id": str(review.company_id),
            "review_definition_id": str(review.id),
            "metric_snapshot_id": str(metric_snapshot.id),
            "evaluation_id": str(evaluation.id) if evaluation is not None else "",
        },
    )
    return run


def periodic_review_payload(review: PeriodicReviewDefinition) -> dict[str, Any]:
    current_period = current_due_review_period(review)
    next_period = next_review_period(review)
    last_run = (
        ReportRun.objects.filter(review_definition=review)
        .order_by("-period_start", "-created_at")
        .first()
    )
    return {
        "id": str(review.id),
        "company_id": str(review.company_id),
        "program_id": str(review.program_id) if review.program_id else None,
        "pack_id": review.pack_id,
        "template_id": review.template_id,
        "display_name": review.display_name,
        "cadence": review.cadence,
        "timezone": review.timezone,
        "evaluation_profile_id": review.evaluation_profile_key,
        "report_template_id": review.report_template_id,
        "history_projection_type": review.history_projection_type,
        "enabled": review.enabled,
        "current_due_period": current_period.as_payload(),
        "next_due_period": next_period.as_payload(),
        "due_status": _due_status(review=review, period=current_period),
        "last_report_run_id": str(last_run.id) if last_run is not None else "",
        "last_report_period": {
            "period_start": last_run.period_start.isoformat(),
            "period_end": last_run.period_end.isoformat(),
        }
        if last_run is not None
        else None,
        "metadata": review.metadata_json,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat(),
    }


def metric_snapshot_payload(snapshot: MetricSnapshot) -> dict[str, Any]:
    return {
        "id": str(snapshot.id),
        "company_id": str(snapshot.company_id),
        "program_id": str(snapshot.program_id) if snapshot.program_id else None,
        "review_definition_id": str(snapshot.review_definition_id)
        if snapshot.review_definition_id
        else None,
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "metric_values": snapshot.metric_values_json,
        "metric_sources": snapshot.metric_sources_json,
        "source_type": snapshot.source_type,
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat(),
    }


def report_run_payload(run: ReportRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "company_id": str(run.company_id),
        "program_id": str(run.program_id) if run.program_id else None,
        "review_definition_id": str(run.review_definition_id) if run.review_definition_id else None,
        "metric_snapshot_id": str(run.metric_snapshot_id) if run.metric_snapshot_id else None,
        "report_template_id": run.report_template_id,
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "evaluation_run_ids": run.evaluation_run_ids_json,
        "artifact": artifact_payload(run.artifact) if run.artifact else None,
        "artifact_revision_id": str(run.artifact_revision_id) if run.artifact_revision_id else None,
        "generated_sections": run.generated_sections_json,
        "source_refs": run.source_refs_json,
        "created_at": run.created_at.isoformat(),
    }


def _report_sections(
    *,
    review: PeriodicReviewDefinition,
    metric_snapshot: MetricSnapshot,
    evaluation: EvaluationRun | None,
    report_template: dict[str, Any],
    notes: str,
) -> dict[str, Any]:
    result = (
        evaluation.result_json
        if evaluation is not None and isinstance(evaluation.result_json, dict)
        else {}
    )
    raw_metrics = result.get("metrics")
    metrics = (
        [item for item in raw_metrics if isinstance(item, dict)]
        if isinstance(raw_metrics, list)
        else []
    )
    findings = [
        {
            "metric_id": item.get("metric_id"),
            "label": item.get("label"),
            "level": item.get("level"),
            "level_label": item.get("level_label"),
            "trend": item.get("trend"),
            "recommended_operation_template_ids": item.get("recommended_operation_template_ids"),
        }
        for item in metrics
        if isinstance(item, dict) and item.get("level") in {"bad_or_risky", "needs_input"}
    ]
    recommendations = _dedupe(
        [
            operation_id
            for item in metrics
            for operation_id in item.get("recommended_operation_template_ids", []) or []
            if isinstance(operation_id, str) and operation_id
        ]
    )
    template_sections = report_template.get("sections")
    return {
        "template_id": _safe_key(report_template.get("id")) or review.report_template_id,
        "section_order": template_sections if isinstance(template_sections, list) else [],
        "period": {
            "start": metric_snapshot.period_start.isoformat(),
            "end": metric_snapshot.period_end.isoformat(),
            "cadence": review.cadence,
            "timezone": review.timezone,
        },
        "summary": {
            "review_definition_id": str(review.id),
            "review_name": review.display_name,
            "evaluation_status": evaluation.status if evaluation is not None else "",
            "score": evaluation.score if evaluation is not None else None,
            "grade": evaluation.grade if evaluation is not None else "",
            "notes": _safe_text(notes, 4000),
        },
        "metric_snapshot": metric_snapshot_payload(metric_snapshot),
        "kpi_scorecard": evaluation_payload(evaluation) if evaluation is not None else None,
        "findings": findings,
        "trend_summary": result.get("trend_summary") if isinstance(result, dict) else {},
        "recommendations": [
            {
                "operation_template_id": operation_id,
                "reason": "Recommended from periodic scorecard finding.",
            }
            for operation_id in recommendations
        ],
        "next_actions": [
            {
                "operation_template_id": operation_id,
                "reason": "Launch through the operating model operation launcher.",
            }
            for operation_id in recommendations[:6]
        ],
    }


def _report_source_refs(
    *,
    metric_snapshot: MetricSnapshot,
    evaluation: EvaluationRun | None,
    asset: Asset,
) -> list[dict[str, str]]:
    refs = [
        {"type": "metric_snapshot", "id": str(metric_snapshot.id)},
        {"type": "asset", "id": str(asset.id)},
    ]
    if evaluation is not None:
        refs.insert(1, {"type": "evaluation", "id": str(evaluation.id)})
    return refs


def _execution_period(
    *,
    review: PeriodicReviewDefinition,
    snapshot: MetricSnapshot | None,
    period_start: date | None,
    period_end: date | None,
    as_of: date | datetime | None,
) -> ReviewPeriod:
    if (period_start is None) != (period_end is None):
        raise PeriodicReviewError(
            "invalid_period", "Both period_start and period_end are required together."
        )
    if period_start is not None and period_end is not None:
        if period_end < period_start:
            raise PeriodicReviewError("invalid_period", "Review period end cannot precede start.")
        return ReviewPeriod(
            period_start=period_start,
            period_end=period_end,
            cadence=review.cadence,
            timezone=review.timezone or "UTC",
        )
    if snapshot is not None:
        return ReviewPeriod(
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            cadence=review.cadence,
            timezone=review.timezone or "UTC",
        )
    return current_due_review_period(review, as_of=as_of)


def _metric_snapshot_by_id(
    *,
    review: PeriodicReviewDefinition,
    metric_snapshot_id: str | None,
) -> MetricSnapshot | None:
    if not metric_snapshot_id:
        return None
    snapshot = MetricSnapshot.objects.filter(
        company=review.company,
        id=str(metric_snapshot_id),
    ).first()
    if snapshot is None:
        raise PeriodicReviewError("metric_snapshot_not_found", "Metric snapshot was not found.")
    return snapshot


def _assert_snapshot_usable(
    *,
    review: PeriodicReviewDefinition,
    snapshot: MetricSnapshot,
    period: ReviewPeriod,
) -> None:
    if snapshot.company_id != review.company_id:
        raise PeriodicReviewError(
            "snapshot_company_mismatch", "Metric snapshot is not for this review company."
        )
    if snapshot.review_definition_id and snapshot.review_definition_id != review.id:
        raise PeriodicReviewError(
            "snapshot_review_mismatch", "Metric snapshot is tied to another review."
        )
    if review.program_id and snapshot.program_id and snapshot.program_id != review.program_id:
        raise PeriodicReviewError(
            "snapshot_program_mismatch", "Metric snapshot is tied to another program."
        )
    if snapshot.period_start != period.period_start or snapshot.period_end != period.period_end:
        raise PeriodicReviewError(
            "snapshot_period_mismatch", "Metric snapshot period does not match the review period."
        )


def _latest_metric_snapshot_for_period(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
) -> MetricSnapshot | None:
    queryset = MetricSnapshot.objects.filter(
        company=review.company,
        review_definition=review,
        period_start=period.period_start,
        period_end=period.period_end,
    )
    if review.program_id:
        queryset = queryset.filter(program=review.program)
    return queryset.order_by("-created_at").first()


def _existing_report_run(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
) -> ReportRun | None:
    return (
        ReportRun.objects.filter(
            company=review.company,
            review_definition=review,
            period_start=period.period_start,
            period_end=period.period_end,
        )
        .order_by("-created_at")
        .first()
    )


def metric_input_blockers(
    *,
    review: PeriodicReviewDefinition,
    metric_values: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return explicit input blockers for a review's scorecard metrics."""

    metrics = _profile_metrics(review)
    if not metrics:
        return []
    blockers: list[dict[str, Any]] = []
    empty_values = not metric_values
    for metric in metrics:
        blocker = _metric_input_blocker(
            metric=metric, metric_values=metric_values, empty=empty_values
        )
        if blocker is not None:
            blockers.append(blocker)
    return blockers


def _metric_input_blocker(
    *,
    metric: dict[str, Any],
    metric_values: dict[str, Any],
    empty: bool,
) -> dict[str, Any] | None:
    metric_id = _safe_key(metric.get("id"))
    if not metric_id:
        return None
    raw_value = metric_values.get(metric_id)
    label = _safe_text(metric.get("label") or metric_id.replace("_", " ").title(), 160)
    if metric_id not in metric_values:
        if empty or metric.get("required") is True:
            return _metric_blocker(
                metric_id=metric_id,
                label=label,
                reason="metric_value_missing",
                missing=["value"],
            )
        return None
    return _present_metric_input_blocker(
        metric=metric, metric_id=metric_id, label=label, raw_value=raw_value
    )


def _present_metric_input_blocker(
    *,
    metric: dict[str, Any],
    metric_id: str,
    label: str,
    raw_value: Any,
) -> dict[str, Any] | None:
    mode = str(metric.get("mode") or "threshold").strip().lower()
    if mode == "contextual":
        missing = _missing_contextual_inputs(metric=metric, raw_value=raw_value)
        if missing:
            return _metric_blocker(
                metric_id=metric_id,
                label=label,
                reason="metric_context_missing",
                missing=missing,
            )
        return None
    if mode == "qualitative_manual" and not _manual_level(raw_value):
        return _metric_blocker(
            metric_id=metric_id,
            label=label,
            reason="manual_level_missing",
            missing=["level"],
        )
    if (
        mode == "threshold_or_manual"
        and _number_value(raw_value) is None
        and not _manual_level(raw_value)
    ):
        return _metric_blocker(
            metric_id=metric_id,
            label=label,
            reason="metric_value_or_manual_level_missing",
            missing=["value", "level"],
        )
    if mode == "threshold" and _number_value(raw_value) is None:
        return _metric_blocker(
            metric_id=metric_id,
            label=label,
            reason="metric_value_not_numeric",
            missing=["numeric_value"],
        )
    return None


def _metric_blocker(
    *,
    metric_id: str,
    label: str,
    reason: str,
    missing: list[str],
) -> dict[str, Any]:
    return {
        "type": "metric_input_required",
        "metric_id": metric_id,
        "label": label,
        "reason": reason,
        "missing": missing,
    }


def _upsert_metric_input_required_signal(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
    user: User,
    blockers: list[dict[str, Any]],
) -> Any:
    external_key = (
        f"periodic-review-input-gap:{review.id}:"
        f"{period.period_start.isoformat()}:{period.period_end.isoformat()}"
    )
    signal = create_company_signal(
        company=review.company,
        actor=user,
        signal_type="manual",
        signal_kind="capability_gap",
        domain_context="reporting",
        title=f"{review.display_name} needs metric inputs",
        summary=(
            f"{review.display_name} cannot run for {period.period_start.isoformat()} "
            f"to {period.period_end.isoformat()} until required metrics are supplied."
        ),
        source="periodic_review_input_gap",
        external_key=external_key,
        metadata={
            "review_definition_id": str(review.id),
            "program_id": str(review.program_id) if review.program_id else None,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "blockers": blockers,
        },
    )
    signal.status = "new"
    signal.metadata_json = {
        **(signal.metadata_json if isinstance(signal.metadata_json, dict) else {}),
        "review_definition_id": str(review.id),
        "program_id": str(review.program_id) if review.program_id else None,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "blockers": blockers,
    }
    signal.occurred_at = timezone.now()
    signal.save(update_fields=["status", "metadata_json", "occurred_at", "updated_at"])
    return signal


def _summary_from_report(
    *,
    review: PeriodicReviewDefinition,
    report: ReportRun,
    period: ReviewPeriod,
    history_projection_id: str = "",
    status: str,
    skipped: bool = False,
    dry_run: bool = False,
) -> PeriodicReviewExecutionSummary:
    evaluation_ids = _string_list(report.evaluation_run_ids_json)
    evaluations = EvaluationRun.objects.filter(company=review.company, id__in=evaluation_ids)
    signal_ids: list[str] = []
    recommendations: list[str] = []
    for evaluation in evaluations:
        result = evaluation.result_json if isinstance(evaluation.result_json, dict) else {}
        signal_ids.extend(_string_list(result.get("signal_ids")))
        recommendations.extend(_string_list(result.get("recommended_operation_template_ids")))
    if not history_projection_id:
        history_projection_id = _history_projection_id(
            review=review,
            program=report.program or review.program,
        )
    return PeriodicReviewExecutionSummary(
        review_definition_id=str(review.id),
        period_start=period.period_start.isoformat(),
        period_end=period.period_end.isoformat(),
        metric_snapshot_id=str(report.metric_snapshot_id) if report.metric_snapshot_id else "",
        evaluation_run_ids=tuple(evaluation_ids),
        report_run_id=str(report.id),
        artifact_id=str(report.artifact_id) if report.artifact_id else "",
        artifact_revision_id=str(report.artifact_revision_id)
        if report.artifact_revision_id
        else "",
        history_projection_id=history_projection_id,
        signal_ids=tuple(_dedupe(signal_ids)),
        recommended_operation_template_ids=tuple(_dedupe(recommendations)),
        skipped=skipped,
        dry_run=dry_run,
        status=status,
    )


def _history_projection_id(
    *,
    review: PeriodicReviewDefinition,
    program: CompanyProgram | None,
) -> str:
    if not review.history_projection_type:
        return ""
    projection = StateProjection.objects.filter(
        company=review.company,
        program=program,
        projection_type=review.history_projection_type,
    ).first()
    return str(projection.id) if projection is not None else ""


def _due_status(*, review: PeriodicReviewDefinition, period: ReviewPeriod) -> str:
    if not review.enabled:
        return "disabled"
    return "complete" if review_has_report_for_period(review, period) else "due"


def _profile_metrics(review: PeriodicReviewDefinition) -> list[dict[str, Any]]:
    profile = review.evaluation_profile
    if profile is None and review.evaluation_profile_key:
        profile = EvaluationProfile.objects.filter(
            company=review.company,
            profile_id=review.evaluation_profile_key,
        ).first()
    rubric = profile.rubric_json if profile and isinstance(profile.rubric_json, dict) else {}
    raw_metrics = rubric.get("metrics")
    if not isinstance(raw_metrics, list):
        return []
    return [item for item in raw_metrics if isinstance(item, dict) and item.get("id")]


def _missing_contextual_inputs(*, metric: dict[str, Any], raw_value: Any) -> list[str]:
    if _manual_level(raw_value):
        return []
    formula = str(metric.get("contextual_formula") or metric.get("formula") or "").strip()
    if formula == "cost_per_outcome_profitability":
        required = [
            "cost_per_lead",
            "average_ticket",
            "gross_margin",
            "lead_to_sale_conversion_rate",
            "target_profit_margin",
        ]
        return _missing_context_keys(
            raw_value=raw_value,
            required=required,
            primary_key="cost_per_lead",
        )
    if formula == "cost_vs_profit_ratio":
        return _missing_context_keys(
            raw_value=raw_value,
            required=["customer_acquisition_cost", "gross_profit_per_customer"],
            primary_key="customer_acquisition_cost",
        )
    required = [
        _safe_key(item)
        for item in (metric.get("required_context_inputs") or metric.get("contextual_inputs") or [])
        if _safe_key(item)
    ]
    if not required:
        return []
    return _missing_context_keys(raw_value=raw_value, required=required, primary_key="")


def _missing_context_keys(
    *,
    raw_value: Any,
    required: list[str],
    primary_key: str,
) -> list[str]:
    context = raw_value if isinstance(raw_value, dict) else {}
    missing: list[str] = []
    for key in required:
        candidate = context.get(key)
        if key == primary_key:
            candidate = context.get("value", context.get(key)) if context else raw_value
        if _number_value(candidate) is None:
            missing.append(key)
    return missing


def _manual_level(value: Any) -> str:
    if isinstance(value, dict):
        candidate = value.get("level")
    else:
        candidate = value
    level = str(candidate or "").strip().lower()
    return level if level in {"bad_or_risky", "acceptable", "good"} else ""


def _local_date(
    *,
    review: PeriodicReviewDefinition,
    as_of: date | datetime | None,
) -> date:
    zone = _review_zone(review)
    if as_of is None:
        return timezone.now().astimezone(zone).date()
    if isinstance(as_of, datetime):
        value = as_of
        if timezone.is_naive(value):
            value = timezone.make_aware(value, ZoneInfo("UTC"))
        return value.astimezone(zone).date()
    return as_of


def _review_zone(review: PeriodicReviewDefinition) -> ZoneInfo:
    try:
        return ZoneInfo(review.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _quarter_start(day: date) -> date:
    month = ((day.month - 1) // 3) * 3 + 1
    return date(day.year, month, 1)


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _custom_due_period(*, review: PeriodicReviewDefinition, today: date) -> ReviewPeriod:
    days = max(1, _custom_period_days(review))
    anchor = (
        _custom_anchor_date(review) or review.created_at.astimezone(_review_zone(review)).date()
    )
    due_index = ((today - anchor).days - days) // days
    period_start = anchor + timedelta(days=due_index * days)
    return ReviewPeriod(
        period_start=period_start,
        period_end=period_start + timedelta(days=days - 1),
        cadence="custom",
        timezone=review.timezone or "UTC",
    )


def _custom_period_days(review: PeriodicReviewDefinition) -> int:
    metadata = review.metadata_json if isinstance(review.metadata_json, dict) else {}
    raw_template = metadata.get("template")
    template = cast(dict[str, Any], raw_template) if isinstance(raw_template, dict) else {}
    for key in ("custom_period_days", "cadence_days", "period_days"):
        value = template.get(key) or metadata.get(key)
        number = _number_value(value)
        if number is not None and number >= 1:
            return int(number)
    return 30


def _custom_anchor_date(review: PeriodicReviewDefinition) -> date | None:
    metadata = review.metadata_json if isinstance(review.metadata_json, dict) else {}
    raw_template = metadata.get("template")
    template = cast(dict[str, Any], raw_template) if isinstance(raw_template, dict) else {}
    for key in ("anchor_date", "period_anchor"):
        value = str(template.get(key) or metadata.get(key) or "").strip()
        if not value:
            continue
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return None


def _advance_period(
    *,
    review: PeriodicReviewDefinition,
    period: ReviewPeriod,
) -> ReviewPeriod:
    cadence = _safe_choice(review.cadence, {"weekly", "monthly", "quarterly", "custom"}, "monthly")
    if cadence == "weekly":
        start = period.period_start + timedelta(days=7)
        end = period.period_end + timedelta(days=7)
    elif cadence == "quarterly":
        start = _add_months(period.period_start, 3)
        end = _add_months(start, 3) - timedelta(days=1)
    elif cadence == "custom":
        days = max(1, _custom_period_days(review))
        start = period.period_start + timedelta(days=days)
        end = start + timedelta(days=days - 1)
    else:
        start = _add_months(period.period_start, 1)
        end = _add_months(start, 1) - timedelta(days=1)
    return ReviewPeriod(
        period_start=start,
        period_end=end,
        cadence=cadence,
        timezone=review.timezone or "UTC",
    )


def _number_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace("%", "").replace("x", "")
        cleaned = cleaned.replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _report_template(review: PeriodicReviewDefinition) -> dict[str, Any]:
    metadata = review.metadata_json if isinstance(review.metadata_json, dict) else {}
    template = metadata.get("report_template")
    if isinstance(template, dict) and template:
        return template
    parent = metadata.get("template")
    if isinstance(parent, dict):
        nested = parent.get("report_template")
        if isinstance(nested, dict):
            return nested
    return {"id": review.report_template_id, "artifact_schema_id": "periodic_report"}


def _history_label(review: PeriodicReviewDefinition) -> str:
    template = (
        review.metadata_json.get("template") if isinstance(review.metadata_json, dict) else {}
    )
    if isinstance(template, dict):
        label = template.get("history_display_label")
        if label:
            return _safe_text(label, 160)
    return "History"


def _safe_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _safe_key(value: Any) -> str:
    return str(value or "").strip()


def _safe_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _json_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
