"""Generic evaluation profile and run services."""

from __future__ import annotations

import re
from typing import Any, cast

from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.company_ops import create_company_signal
from application.services.work_artifacts import canonical_version
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyProgram,
    CompanySignal,
    EvaluationFinding,
    EvaluationProfile,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    MetricSnapshot,
    User,
)


def run_evaluation(
    *,
    company: Graph,
    user: User,
    profile_id: str,
    content: str = "",
    asset: Asset | None = None,
    asset_version: AssetVersion | None = None,
    program: CompanyProgram | None = None,
    input_refs: list[Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> EvaluationRun:
    profile = EvaluationProfile.objects.filter(company=company, profile_id=profile_id).first()
    if _profile_engine(profile) == "threshold_scorecard_v1":
        return _run_threshold_scorecard(
            company=company,
            user=user,
            profile=profile,
            profile_id=profile_id,
            program=program,
            asset=asset,
            asset_version=asset_version,
            input_refs=input_refs or [],
            inputs=inputs or {},
        )
    effective_version = asset_version or (canonical_version(asset) if asset is not None else None)
    text = content or _content_from_version(effective_version)
    findings = _find_issues(text=text, profile_id=profile_id)
    score = max(0, 100 - sum(item["penalty"] for item in findings))
    blocking = any(item["blocking"] for item in findings)
    status = _status_for_score(score=score, findings=findings, profile=profile)
    grade = _grade(score)
    evaluation = EvaluationRun.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        program=program,
        asset=asset,
        asset_version=effective_version,
        profile=profile,
        profile_key=profile_id,
        status=status,
        score=score,
        grade=grade,
        input_refs_json=input_refs or [],
        result_json={"finding_count": len(findings), "blocking": blocking},
        created_by=user,
        evaluated_at=timezone.now(),
    )
    for item in findings:
        EvaluationFinding.objects.create(
            organization=cast(Any, company.organization),
            company=company,
            evaluation=evaluation,
            severity=item["severity"],
            issue_type=item["issue_type"],
            message=item["message"],
            evidence_refs_json=item.get("evidence_refs", []),
            suggested_fix=item["suggested_fix"],
            blocking=item["blocking"],
        )
    EvaluationScorecard.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        evaluation=evaluation,
        dimensions_json=_dimension_scores(score=score, findings=findings),
        composite_score=score,
        grade=grade,
    )
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="evaluation.run",
        resource_type="evaluation",
        resource_id=str(evaluation.id),
        metadata={"company_id": str(company.id), "profile_id": profile_id, "status": status},
    )
    return evaluation


def _run_threshold_scorecard(
    *,
    company: Graph,
    user: User,
    profile: EvaluationProfile | None,
    profile_id: str,
    program: CompanyProgram | None,
    asset: Asset | None,
    asset_version: AssetVersion | None,
    input_refs: list[Any],
    inputs: dict[str, Any],
) -> EvaluationRun:
    rubric = profile.rubric_json if profile and isinstance(profile.rubric_json, dict) else {}
    metric_defs = [
        item for item in rubric.get("metrics", []) if isinstance(item, dict) and item.get("id")
    ]
    metric_snapshot = _metric_snapshot_from_inputs(company=company, inputs=inputs)
    metric_inputs = _metric_inputs(inputs)
    if metric_snapshot is not None:
        metric_inputs = {**metric_snapshot.metric_values_json, **metric_inputs}
        input_refs = [
            *input_refs,
            {"type": "metric_snapshot", "id": str(metric_snapshot.id)},
        ]
    review_definition_id = str(
        inputs.get("review_definition_id")
        or (metric_snapshot.review_definition_id if metric_snapshot else "")
        or ""
    )
    results = [
        _evaluate_scorecard_metric(metric=metric, metric_inputs=metric_inputs)
        for metric in metric_defs
    ]
    if not results:
        results = [
            {
                "metric_id": "scorecard_inputs",
                "label": "Scorecard Inputs",
                "level": "needs_input",
                "level_label": "Needs Input",
                "score": 0,
                "value": None,
                "unit": "",
                "notes": "No scorecard metrics were configured.",
                "recommended_operation_template_ids": [],
                "finding": {
                    "severity": "WARNING",
                    "issue_type": "scorecard_profile_empty",
                    "message": "This scorecard profile does not define any metrics.",
                    "suggested_fix": "Add metric definitions to the installed evaluation profile.",
                    "blocking": False,
                },
            }
        ]
    trend_summary = _apply_metric_trends(
        company=company,
        program=program,
        profile_id=profile_id,
        review_definition_id=review_definition_id,
        metric_snapshot=metric_snapshot,
        results=results,
    )
    block_on_bad = bool(rubric.get("block_on_bad_or_risky") is True)
    findings = _scorecard_findings(results=results, block_on_bad=block_on_bad)
    status = _scorecard_status(results=results, findings=findings)
    score = _scorecard_score(results)
    grade = _grade(score)
    recommended = _dedupe(
        [
            operation_id
            for result in results
            for operation_id in result.get("recommended_operation_template_ids", [])
            if isinstance(operation_id, str) and operation_id
        ]
    )
    evaluation = EvaluationRun.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        program=program,
        asset=asset,
        asset_version=asset_version,
        profile=profile,
        profile_key=profile_id,
        status=status,
        score=score,
        grade=grade,
        input_refs_json=input_refs,
        result_json={
            "engine": "threshold_scorecard_v1",
            "review_definition_id": review_definition_id,
            "metric_snapshot_id": str(metric_snapshot.id) if metric_snapshot else "",
            "metric_snapshot": _metric_snapshot_result(metric_snapshot),
            "metric_count": len(results),
            "bad_or_risky_count": len(
                [item for item in results if item.get("level") == "bad_or_risky"]
            ),
            "needs_input_count": len(
                [item for item in results if item.get("level") == "needs_input"]
            ),
            "recommended_operation_template_ids": recommended,
            "metrics": results,
            "trend_summary": trend_summary,
        },
        created_by=user,
        evaluated_at=timezone.now(),
    )
    for finding in findings:
        EvaluationFinding.objects.create(
            organization=cast(Any, company.organization),
            company=company,
            evaluation=evaluation,
            severity=finding["severity"],
            issue_type=finding["issue_type"],
            message=finding["message"],
            evidence_refs_json=finding.get("evidence_refs", []),
            suggested_fix=finding["suggested_fix"],
            blocking=bool(finding["blocking"]),
        )
    scorecard = {
        "engine": "threshold_scorecard_v1",
        "metrics": results,
        "level_counts": _level_counts(results),
        "recommended_operation_template_ids": recommended,
        "trend_summary": trend_summary,
    }
    EvaluationScorecard.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        evaluation=evaluation,
        dimensions_json=scorecard,
        composite_score=score,
        grade=grade,
    )
    signals = _create_scorecard_signals(
        company=company,
        user=user,
        program=program,
        evaluation=evaluation,
        profile_id=profile_id,
        results=results,
    )
    if signals:
        evaluation.result_json = {
            **evaluation.result_json,
            "signal_ids": [str(item.id) for item in signals],
        }
        evaluation.save(update_fields=["result_json"])
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="evaluation.run",
        resource_type="evaluation",
        resource_id=str(evaluation.id),
        metadata={
            "company_id": str(company.id),
            "profile_id": profile_id,
            "status": status,
            "engine": "threshold_scorecard_v1",
        },
    )
    return evaluation


def evaluation_payload(evaluation: EvaluationRun) -> dict[str, Any]:
    findings = EvaluationFinding.objects.filter(evaluation=evaluation)
    return {
        "id": str(evaluation.id),
        "company_id": str(evaluation.company_id),
        "program_id": str(evaluation.program_id) if evaluation.program_id else None,
        "asset_id": str(evaluation.asset_id) if evaluation.asset_id else None,
        "asset_version_id": str(evaluation.asset_version_id)
        if evaluation.asset_version_id
        else None,
        "profile_id": evaluation.profile_key,
        "status": evaluation.status,
        "score": evaluation.score,
        "grade": evaluation.grade,
        "input_refs": evaluation.input_refs_json,
        "result": evaluation.result_json,
        "findings": [
            {
                "id": str(item.id),
                "severity": item.severity,
                "issue_type": item.issue_type,
                "message": item.message,
                "evidence_refs": item.evidence_refs_json,
                "suggested_fix": item.suggested_fix,
                "blocking": item.blocking,
                "created_at": item.created_at.isoformat(),
            }
            for item in findings
        ],
        "scorecard": _scorecard_payload(evaluation),
        "created_at": evaluation.created_at.isoformat(),
        "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
    }


def _profile_engine(profile: EvaluationProfile | None) -> str:
    if profile is None or not isinstance(profile.rubric_json, dict):
        return ""
    return str(profile.rubric_json.get("engine") or "")


def _metric_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    metrics = inputs.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    return inputs


def _metric_snapshot_from_inputs(
    *, company: Graph, inputs: dict[str, Any]
) -> MetricSnapshot | None:
    snapshot_id = str(inputs.get("metric_snapshot_id") or "").strip()
    if not snapshot_id:
        return None
    return MetricSnapshot.objects.filter(company=company, id=snapshot_id).first()


def _evaluate_scorecard_metric(
    *,
    metric: dict[str, Any],
    metric_inputs: dict[str, Any],
) -> dict[str, Any]:
    metric_id = str(metric.get("id") or "")
    label = str(metric.get("label") or _label_from_id(metric_id))
    unit = str(metric.get("unit") or "")
    mode = str(metric.get("mode") or "threshold").lower()
    raw_input = metric_inputs.get(metric_id)
    notes = ""
    context: dict[str, Any] = {}
    if isinstance(raw_input, dict):
        raw_value = raw_input.get("value")
        manual_level = str(raw_input.get("level") or "").strip()
        notes = str(raw_input.get("notes") or "")
        context = _metric_context(raw_input)
    else:
        raw_value = raw_input
        manual_level = (
            str(raw_input or "").strip()
            if mode in {"qualitative_manual", "threshold_or_manual", "contextual"}
            else ""
        )

    if mode == "qualitative_manual":
        return _manual_metric_result(
            metric=metric,
            metric_id=metric_id,
            label=label,
            unit=unit,
            level=manual_level,
            notes=notes,
        )

    if mode == "threshold_or_manual" and manual_level and _number_value(raw_value) is None:
        return _manual_metric_result(
            metric=metric,
            metric_id=metric_id,
            label=label,
            unit=unit,
            level=manual_level,
            notes=notes,
        )

    if mode == "contextual":
        computed_value, missing = _contextual_metric_value(
            metric=metric,
            raw_value=raw_value,
            context=context,
        )
        if computed_value is None:
            if manual_level:
                return _manual_metric_result(
                    metric=metric,
                    metric_id=metric_id,
                    label=label,
                    unit=unit,
                    level=manual_level,
                    notes=notes,
                )
            missing_text = ", ".join(missing) if missing else "required context"
            return _needs_input_result(
                metric=metric,
                metric_id=metric_id,
                label=label,
                unit=unit,
                notes=f"Missing contextual inputs: {missing_text}.",
            )
        raw_value = computed_value
        notes = notes or "Computed from contextual metric inputs."

    value = _number_value(raw_value)
    if value is None:
        if manual_level and mode == "threshold_or_manual":
            return _manual_metric_result(
                metric=metric,
                metric_id=metric_id,
                label=label,
                unit=unit,
                level=manual_level,
                notes=notes,
            )
        return _needs_input_result(
            metric=metric,
            metric_id=metric_id,
            label=label,
            unit=unit,
            notes="Metric input is missing or not numeric.",
        )

    level = _threshold_level(metric=metric, value=value)
    return _metric_result(
        metric=metric,
        metric_id=metric_id,
        label=label,
        unit=unit,
        level=level,
        value=value,
        notes=notes,
    )


def _metric_context(raw_input: dict[str, Any]) -> dict[str, Any]:
    context = raw_input.get("context")
    if isinstance(context, dict):
        merged = dict(context)
    else:
        merged = {}
    for key, value in raw_input.items():
        if key in {"value", "level", "notes", "context"}:
            continue
        merged.setdefault(str(key), value)
    return merged


def _contextual_metric_value(
    *,
    metric: dict[str, Any],
    raw_value: Any,
    context: dict[str, Any],
) -> tuple[float | None, list[str]]:
    formula = str(metric.get("contextual_formula") or metric.get("formula") or "").strip()
    if formula == "cost_per_outcome_profitability":
        required = [
            "cost_per_lead",
            "average_ticket",
            "gross_margin",
            "lead_to_sale_conversion_rate",
            "target_profit_margin",
        ]
        values = _context_values(
            raw_value=raw_value,
            context=context,
            primary_key="cost_per_lead",
            required=required,
        )
        missing = [key for key in required if values.get(key) is None]
        if missing:
            return None, missing
        average_ticket = float(values["average_ticket"] or 0)
        gross_margin = _rate_value(values["gross_margin"])
        conversion = _rate_value(values["lead_to_sale_conversion_rate"])
        target_profit = _rate_value(values["target_profit_margin"])
        sustainable_cost = average_ticket * gross_margin * conversion * max(0.0, 1 - target_profit)
        if sustainable_cost <= 0:
            return None, ["positive sustainable cost"]
        return float(values["cost_per_lead"] or 0) / sustainable_cost, []
    if formula == "cost_vs_profit_ratio":
        required = ["customer_acquisition_cost", "gross_profit_per_customer"]
        values = _context_values(
            raw_value=raw_value,
            context=context,
            primary_key="customer_acquisition_cost",
            required=required,
        )
        missing = [key for key in required if values.get(key) is None]
        if missing:
            return None, missing
        profit = float(values["gross_profit_per_customer"] or 0)
        if profit <= 0:
            return None, ["positive gross_profit_per_customer"]
        return float(values["customer_acquisition_cost"] or 0) / profit, []
    value = _number_value(raw_value)
    if value is None:
        return None, _string_list(
            metric.get("required_context_inputs") or metric.get("contextual_inputs")
        )
    return value, []


def _context_values(
    *,
    raw_value: Any,
    context: dict[str, Any],
    primary_key: str,
    required: list[str],
) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for key in required:
        candidate = raw_value if key == primary_key and raw_value is not None else context.get(key)
        values[key] = _number_value(candidate)
    return values


def _rate_value(value: Any) -> float:
    number = _number_value(value)
    if number is None:
        return 0
    return number / 100 if number > 1 else number


def _manual_metric_result(
    *,
    metric: dict[str, Any],
    metric_id: str,
    label: str,
    unit: str,
    level: str,
    notes: str,
) -> dict[str, Any]:
    clean_level = level.strip().lower()
    if clean_level in {"bad", "risky", "malo", "riesgoso"}:
        clean_level = "bad_or_risky"
    if clean_level not in {"bad_or_risky", "acceptable", "good"}:
        return _needs_input_result(
            metric=metric,
            metric_id=metric_id,
            label=label,
            unit=unit,
            notes=notes or "Manual level is required for this contextual metric.",
        )
    return _metric_result(
        metric=metric,
        metric_id=metric_id,
        label=label,
        unit=unit,
        level=clean_level,
        value=None,
        notes=notes,
    )


def _needs_input_result(
    *,
    metric: dict[str, Any],
    metric_id: str,
    label: str,
    unit: str,
    notes: str,
) -> dict[str, Any]:
    result = _metric_result(
        metric=metric,
        metric_id=metric_id,
        label=label,
        unit=unit,
        level="needs_input",
        value=None,
        notes=notes,
    )
    result["finding"] = {
        "severity": "WARNING",
        "issue_type": "scorecard_metric_needs_input",
        "message": f"{label} needs a metric value or manual level before it can be scored.",
        "suggested_fix": "Provide a numeric value or manual level with notes.",
        "blocking": False,
    }
    return result


def _metric_result(
    *,
    metric: dict[str, Any],
    metric_id: str,
    label: str,
    unit: str,
    level: str,
    value: float | None,
    notes: str,
) -> dict[str, Any]:
    levels = _dict_value(metric.get("levels"))
    level_meta = _dict_value(levels.get(level))
    level_label = str(level_meta.get("label") or _label_from_id(level))
    recommended = _string_list(metric.get("recommended_operation_template_ids"))
    level_recommended = _string_list(level_meta.get("recommended_operation_template_ids"))
    signal_mapping = _dict_value(metric.get("signal_mapping") or metric.get("signal_mappings"))
    return {
        "metric_id": metric_id,
        "label": label,
        "level": level,
        "level_label": level_label,
        "score": _level_score(level),
        "value": value,
        "unit": unit,
        "direction": str(metric.get("direction") or ""),
        "notes": notes,
        "recommended_operation_template_ids": _dedupe([*recommended, *level_recommended]),
        "signal_mapping": signal_mapping,
    }


def _threshold_level(*, metric: dict[str, Any], value: float) -> str:
    thresholds = _dict_value(metric.get("thresholds")) or metric
    direction = str(metric.get("direction") or "higher_is_better")
    if direction == "target_band":
        target_min = _number_value(thresholds.get("target_min"))
        target_max = _number_value(thresholds.get("target_max"))
        warning_min = _number_value(thresholds.get("warning_min"))
        warning_max = _number_value(thresholds.get("warning_max"))
        if target_min is not None and target_max is not None and target_min <= value <= target_max:
            return "good"
        if (
            warning_min is not None
            and warning_max is not None
            and warning_min <= value <= warning_max
        ):
            return "acceptable"
        return "bad_or_risky"
    if direction == "lower_is_better":
        bad_gte = _number_value(thresholds.get("bad_gte"))
        bad_gt = _number_value(thresholds.get("bad_gt"))
        good_lte = _number_value(thresholds.get("good_lte"))
        good_lt = _number_value(thresholds.get("good_lt"))
        if bad_gte is not None and value >= bad_gte:
            return "bad_or_risky"
        if bad_gt is not None and value > bad_gt:
            return "bad_or_risky"
        if good_lte is not None and value <= good_lte:
            return "good"
        if good_lt is not None and value < good_lt:
            return "good"
        return "acceptable"
    bad_lte = _number_value(thresholds.get("bad_lte"))
    bad_lt = _number_value(thresholds.get("bad_lt"))
    good_gte = _number_value(thresholds.get("good_gte"))
    good_gt = _number_value(thresholds.get("good_gt"))
    if bad_lte is not None and value <= bad_lte:
        return "bad_or_risky"
    if bad_lt is not None and value < bad_lt:
        return "bad_or_risky"
    if good_gte is not None and value >= good_gte:
        return "good"
    if good_gt is not None and value > good_gt:
        return "good"
    return "acceptable"


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


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric_snapshot_result(snapshot: MetricSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "id": str(snapshot.id),
        "review_definition_id": str(snapshot.review_definition_id)
        if snapshot.review_definition_id
        else "",
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "source_type": snapshot.source_type,
        "notes": snapshot.notes,
    }


def _apply_metric_trends(
    *,
    company: Graph,
    program: CompanyProgram | None,
    profile_id: str,
    review_definition_id: str,
    metric_snapshot: MetricSnapshot | None,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    previous = _previous_scorecard_run(
        company=company,
        program=program,
        profile_id=profile_id,
        review_definition_id=review_definition_id,
        metric_snapshot=metric_snapshot,
    )
    previous_metrics = _previous_metric_map(previous)
    summary = {
        "previous_evaluation_id": str(previous.id) if previous is not None else "",
        "improved": [],
        "worsened": [],
        "unchanged": [],
        "new": [],
        "persistent_bad_or_risky": [],
        "newly_bad_or_risky": [],
        "recovered": [],
    }
    for result in results:
        metric_id = str(result.get("metric_id") or "")
        previous_result = previous_metrics.get(metric_id)
        trend = _metric_trend(current=result, previous=previous_result)
        result["trend"] = trend
        movement = trend["movement"]
        if movement in summary:
            cast(list[str], summary[movement]).append(metric_id)
        if trend.get("persistent_bad_or_risky"):
            cast(list[str], summary["persistent_bad_or_risky"]).append(metric_id)
        if trend.get("newly_bad_or_risky"):
            cast(list[str], summary["newly_bad_or_risky"]).append(metric_id)
        if trend.get("recovered"):
            cast(list[str], summary["recovered"]).append(metric_id)
    return summary


def _previous_scorecard_run(
    *,
    company: Graph,
    program: CompanyProgram | None,
    profile_id: str,
    review_definition_id: str,
    metric_snapshot: MetricSnapshot | None,
) -> EvaluationRun | None:
    query = EvaluationRun.objects.filter(company=company, profile_key=profile_id).exclude(
        status="FAILED"
    )
    query = (
        query.filter(program=program) if program is not None else query.filter(program__isnull=True)
    )
    candidates = list(query.order_by("-created_at")[:25])
    current_start = metric_snapshot.period_start.isoformat() if metric_snapshot else ""
    for candidate in candidates:
        result = candidate.result_json if isinstance(candidate.result_json, dict) else {}
        if (
            review_definition_id
            and str(result.get("review_definition_id") or "") != review_definition_id
        ):
            continue
        snapshot_value = result.get("metric_snapshot")
        snapshot = cast(dict[str, Any], snapshot_value) if isinstance(snapshot_value, dict) else {}
        previous_end = str(snapshot.get("period_end") or "")
        if current_start and previous_end and previous_end >= current_start:
            continue
        return candidate
    return None


def _previous_metric_map(previous: EvaluationRun | None) -> dict[str, dict[str, Any]]:
    if previous is None or not isinstance(previous.result_json, dict):
        return {}
    metrics = previous.result_json.get("metrics")
    if not isinstance(metrics, list):
        return {}
    return {
        str(item.get("metric_id")): item
        for item in metrics
        if isinstance(item, dict) and item.get("metric_id")
    }


def _metric_trend(
    *,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous is None:
        return {
            "movement": "new",
            "previous_level": "",
            "current_level": str(current.get("level") or ""),
            "numeric_delta": None,
            "persistent_bad_or_risky": False,
            "newly_bad_or_risky": current.get("level") == "bad_or_risky",
            "recovered": False,
        }
    current_level = str(current.get("level") or "")
    previous_level = str(previous.get("level") or "")
    current_rank = _level_rank(current_level)
    previous_rank = _level_rank(previous_level)
    movement = "unchanged"
    if current_level != previous_level:
        if previous_level == "bad_or_risky" and current_level != "bad_or_risky":
            movement = "recovered"
        elif current_rank > previous_rank:
            movement = "improved"
        elif current_rank < previous_rank:
            movement = "worsened"
    current_value = _number_value(current.get("value"))
    previous_value = _number_value(previous.get("value"))
    delta = (
        round(current_value - previous_value, 4)
        if current_value is not None and previous_value is not None
        else None
    )
    return {
        "movement": movement,
        "previous_level": previous_level,
        "current_level": current_level,
        "previous_value": previous.get("value"),
        "current_value": current.get("value"),
        "numeric_delta": delta,
        "persistent_bad_or_risky": previous_level == "bad_or_risky"
        and current_level == "bad_or_risky",
        "newly_bad_or_risky": previous_level != "bad_or_risky" and current_level == "bad_or_risky",
        "recovered": previous_level == "bad_or_risky" and current_level != "bad_or_risky",
    }


def _level_rank(level: str) -> int:
    if level == "good":
        return 3
    if level == "acceptable":
        return 2
    if level == "needs_input":
        return 1
    if level == "bad_or_risky":
        return 0
    return 1


def _scorecard_findings(
    *,
    results: list[dict[str, Any]],
    block_on_bad: bool,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in results:
        prebuilt = result.get("finding")
        if isinstance(prebuilt, dict):
            findings.append(
                {
                    **prebuilt,
                    "evidence_refs": [
                        {
                            "type": "scorecard_metric",
                            "metric_id": result.get("metric_id"),
                            "level": result.get("level"),
                        }
                    ],
                }
            )
            continue
        if result.get("level") != "bad_or_risky":
            continue
        recommended = _string_list(result.get("recommended_operation_template_ids"))
        trend = _dict_value(result.get("trend"))
        persistent = bool(trend.get("persistent_bad_or_risky"))
        findings.append(
            {
                "severity": "CRITICAL" if persistent else "WARNING",
                "issue_type": "scorecard_bad_or_risky",
                "message": (
                    f"{result.get('label')} is persistently classified as "
                    f"{result.get('level_label')}."
                    if persistent
                    else f"{result.get('label')} is classified as {result.get('level_label')}."
                ),
                "suggested_fix": (
                    "Review recommended operations: " + ", ".join(recommended)
                    if recommended
                    else "Review this metric and define the next operation."
                ),
                "blocking": block_on_bad,
                "evidence_refs": [
                    {
                        "type": "scorecard_metric",
                        "metric_id": result.get("metric_id"),
                        "level": result.get("level"),
                        "value": result.get("value"),
                        "trend": trend,
                        "recommended_operation_template_ids": recommended,
                    }
                ],
            }
        )
    return findings


def _scorecard_status(
    *,
    results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    if any(bool(item.get("blocking")) for item in findings):
        return "BLOCK"
    if any(item.get("level") in {"bad_or_risky", "needs_input"} for item in results):
        return "WARN"
    return "PASS"


def _scorecard_score(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0
    return round(sum(float(item.get("score") or 0) for item in results) / len(results), 2)


def _level_score(level: str) -> int:
    if level == "good":
        return 100
    if level == "acceptable":
        return 70
    if level == "needs_input":
        return 50
    return 25


def _level_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"bad_or_risky": 0, "acceptable": 0, "good": 0, "needs_input": 0}
    for result in results:
        level = str(result.get("level") or "")
        if level in counts:
            counts[level] += 1
    return counts


def _create_scorecard_signals(
    *,
    company: Graph,
    user: User,
    program: CompanyProgram | None,
    evaluation: EvaluationRun,
    profile_id: str,
    results: list[dict[str, Any]],
) -> list[Any]:
    signals = []
    for result in results:
        metric_id = str(result.get("metric_id") or "")
        signal_key = _scorecard_signal_external_key(
            program=program,
            profile_id=profile_id,
            metric_id=metric_id,
        )
        trend = _dict_value(result.get("trend"))
        if trend.get("recovered"):
            _mark_recovered_scorecard_signal(
                company=company,
                external_key=signal_key,
                evaluation=evaluation,
                result=result,
            )
            continue
        if result.get("level") != "bad_or_risky":
            continue
        recommended = _string_list(result.get("recommended_operation_template_ids"))
        signal_mapping = _dict_value(result.get("signal_mapping"))
        signal_type_label = str(signal_mapping.get("signal_type") or metric_id)
        signal = create_company_signal(
            company=company,
            actor=user,
            signal_type="manual",
            title=f"{result.get('label')} needs review",
            summary=f"{result.get('label')} was classified as {result.get('level_label')}.",
            source="evaluation_scorecard",
            external_key=signal_key,
            metadata={
                "program_id": str(program.id) if program else None,
                "evaluation_id": str(evaluation.id),
                "profile_id": profile_id,
                "metric_id": metric_id,
                "scorecard_signal_type": signal_type_label,
                "severity": signal_mapping.get("severity") or "high",
                "level": result.get("level"),
                "level_label": result.get("level_label"),
                "value": result.get("value"),
                "unit": result.get("unit"),
                "trend": trend,
                "recommended_operation_template_ids": recommended,
            },
        )
        _refresh_scorecard_signal(signal=signal, evaluation=evaluation, result=result)
        signals.append(signal)
    return signals


def _scorecard_signal_external_key(
    *,
    program: CompanyProgram | None,
    profile_id: str,
    metric_id: str,
) -> str:
    scope = f"program:{program.id}" if program is not None else "company"
    return f"scorecard:{scope}:{profile_id}:{metric_id}"


def _refresh_scorecard_signal(
    *,
    signal: CompanySignal,
    evaluation: EvaluationRun,
    result: dict[str, Any],
) -> None:
    metadata = signal.metadata_json if isinstance(signal.metadata_json, dict) else {}
    signal.title = f"{result.get('label')} needs review"[:255]
    signal.summary = f"{result.get('label')} was classified as {result.get('level_label')}."
    signal.metadata_json = {
        **metadata,
        "latest_evaluation_id": str(evaluation.id),
        "latest_level": result.get("level"),
        "latest_value": result.get("value"),
        "trend": result.get("trend"),
        "recommended_operation_template_ids": _string_list(
            result.get("recommended_operation_template_ids")
        ),
    }
    signal.occurred_at = timezone.now()
    if signal.status == "converted":
        signal.status = "new"
    signal.save(
        update_fields=["title", "summary", "metadata_json", "occurred_at", "status", "updated_at"]
    )


def _mark_recovered_scorecard_signal(
    *,
    company: Graph,
    external_key: str,
    evaluation: EvaluationRun,
    result: dict[str, Any],
) -> None:
    signal = CompanySignal.objects.filter(
        company=company,
        source="evaluation_scorecard",
        external_key=external_key,
    ).first()
    if signal is None:
        return
    metadata = signal.metadata_json if isinstance(signal.metadata_json, dict) else {}
    signal.status = "converted"
    signal.summary = f"{result.get('label')} recovered to {result.get('level_label')}."
    signal.metadata_json = {
        **metadata,
        "recovered_evaluation_id": str(evaluation.id),
        "latest_level": result.get("level"),
        "latest_value": result.get("value"),
        "trend": result.get("trend"),
    }
    signal.occurred_at = timezone.now()
    signal.save(update_fields=["status", "summary", "metadata_json", "occurred_at", "updated_at"])


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _label_from_id(value: str) -> str:
    return re.sub(r"[_-]+", " ", str(value or "")).strip().title()


def _content_from_version(version: AssetVersion | None) -> str:
    if version is None:
        return ""
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    content = provenance.get("inline_content")
    if isinstance(content, str):
        return content
    if content is not None:
        return str(content)
    return ""


def _find_issues(*, text: str, profile_id: str) -> list[dict[str, Any]]:
    normalized = text.lower()
    issues: list[dict[str, Any]] = []
    if not text.strip():
        issues.append(
            {
                "severity": "CRITICAL",
                "issue_type": "empty_content",
                "message": "No evaluable content was provided.",
                "suggested_fix": "Provide artifact content or inline content before running the evaluation.",
                "blocking": True,
                "penalty": 100,
            }
        )
        return issues
    if "lorem ipsum" in normalized or "todo" in normalized or "placeholder" in normalized:
        issues.append(
            {
                "severity": "CRITICAL",
                "issue_type": "placeholder_content",
                "message": "Content contains placeholder text.",
                "suggested_fix": "Replace placeholders with final, source-backed content.",
                "blocking": True,
                "penalty": 45,
            }
        )
    if re.search(r"\b(guaranteed|guarantee|risk-free|100%)\b", normalized):
        issues.append(
            {
                "severity": "CRITICAL"
                if "compliance" in profile_id or "claims" in profile_id
                else "WARNING",
                "issue_type": "high_risk_claim",
                "message": "Content contains a high-risk claim that needs evidence or qualification.",
                "suggested_fix": "Add substantiation, qualification, or remove the claim.",
                "blocking": "compliance" in profile_id or "claims" in profile_id,
                "penalty": 30,
            }
        )
    if len(text.split()) < 25 and "quick" not in profile_id:
        issues.append(
            {
                "severity": "WARNING",
                "issue_type": "thin_content",
                "message": "Content is thin for this evaluation profile.",
                "suggested_fix": "Add enough context, evidence, and structure for review.",
                "blocking": False,
                "penalty": 15,
            }
        )
    if "hallucination" in profile_id and re.search(
        r"\b(no source|made up|invented|unknown source)\b", normalized
    ):
        issues.append(
            {
                "severity": "CRITICAL",
                "issue_type": "hallucination_risk",
                "message": "Content indicates unsupported or invented information.",
                "suggested_fix": "Replace with source-backed evidence or mark the claim as an assumption.",
                "blocking": True,
                "penalty": 50,
            }
        )
    return issues


def _status_for_score(
    *,
    score: float,
    findings: list[dict[str, Any]],
    profile: EvaluationProfile | None,
) -> str:
    thresholds = (
        profile.thresholds_json if profile and isinstance(profile.thresholds_json, dict) else {}
    )
    pass_min = float(thresholds.get("pass_min_score") or 80)
    warn_min = float(thresholds.get("warn_min_score") or 40)
    block_on_critical = thresholds.get("block_on_critical", True) is not False
    if block_on_critical and any(item["blocking"] for item in findings):
        return "BLOCK"
    if score >= pass_min and not findings:
        return "PASS"
    if score >= warn_min:
        return "WARN"
    return "BLOCK"


def _grade(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "A-"
    if score >= 80:
        return "B+"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _dimension_scores(*, score: float, findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "composite": score,
        "issue_count": len(findings),
        "blocking_count": len([item for item in findings if item["blocking"]]),
    }


def _scorecard_payload(evaluation: EvaluationRun) -> dict[str, Any] | None:
    scorecard = getattr(evaluation, "scorecard", None)
    if scorecard is None:
        return None
    return {
        "dimensions": scorecard.dimensions_json,
        "composite_score": scorecard.composite_score,
        "grade": scorecard.grade,
    }
