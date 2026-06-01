"""Generic backend-owned state projection services."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from application.services.work_artifacts import artifact_payload
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    CompanyProgram,
    CompanySignal,
    EvaluationFinding,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    PolicyEvaluation,
    ProgramStageState,
    ReportRun,
    StateProjection,
    ValidationDecision,
)


def materialize_current_truth_projection(
    *,
    company: Graph,
    program: CompanyProgram | None = None,
    projection_type: str = "currently_true_state",
    display_label: str = "Currently True",
) -> StateProjection:
    assertion_query = AssertionRecord.objects.filter(company=company)
    asset_query = Asset.objects.filter(company=company)
    if program is not None:
        assertion_query = assertion_query.filter(program=program)
        asset_query = asset_query.filter(metadata_json__program_id=str(program.id))
    validated = list(assertion_query.filter(validation_status="validated").order_by("category"))
    open_questions = list(
        assertion_query.filter(kind="QUESTION").exclude(validation_status="validated")
    )
    active_assumptions = list(
        assertion_query.filter(kind__in=["OPINION", "ASSUMPTION"]).exclude(
            validation_status="validated"
        )
    )
    artifacts = list(asset_query.order_by("-updated_at")[:50])
    stage_blockers = list(
        ProgramStageState.objects.filter(company=company, program=program).filter(
            status__in=["blocked", "rerun_required", "awaiting_validation"]
        )
        if program is not None
        else ProgramStageState.objects.filter(company=company).filter(
            status__in=["blocked", "rerun_required", "awaiting_validation"]
        )
    )
    qa_blockers = list(
        EvaluationFinding.objects.filter(company=company, blocking=True).filter(
            evaluation__program=program
        )[:20]
        if program is not None
        else EvaluationFinding.objects.filter(company=company, blocking=True)[:20]
    )
    policy_blockers = list(
        PolicyEvaluation.objects.filter(
            company=company, status__in=["blocked", "approval_required"]
        ).order_by("-created_at")[:20]
    )
    recent_corrections = list(
        ValidationDecision.objects.filter(company=company)
        .filter(program=program if program is not None else None)
        .order_by("-created_at")[:20]
        if program is not None
        else ValidationDecision.objects.filter(company=company).order_by("-created_at")[:20]
    )
    signals = list(CompanySignal.objects.filter(company=company).order_by("-occurred_at")[:20])
    json_state = {
        "generated_at": timezone.now().isoformat(),
        "validated_facts": [_assertion_ref(item) for item in validated if item.kind == "FACT"],
        "validated_opinions": [
            _assertion_ref(item) for item in validated if item.kind in {"OPINION", "ASSUMPTION"}
        ],
        "active_assumptions": [_assertion_ref(item) for item in active_assumptions],
        "open_questions": [_assertion_ref(item) for item in open_questions],
        "canonical_artifacts": [artifact_payload(item) for item in artifacts],
        "recent_corrections": [_decision_ref(item) for item in recent_corrections],
        "qa_blockers": [_finding_ref(item) for item in qa_blockers],
        "policy_blockers": [_policy_ref(item) for item in policy_blockers],
        "stage_blockers": [_stage_ref(item) for item in stage_blockers],
        "signals": [_signal_ref(item) for item in signals],
        "next_recommended_action": _next_action(
            program=program,
            open_questions=open_questions,
            qa_blockers=qa_blockers,
            policy_blockers=policy_blockers,
            stage_blockers=stage_blockers,
            signals=signals,
        ),
    }
    projection, _ = StateProjection.objects.update_or_create(
        company=company,
        program=program,
        projection_type=projection_type,
        defaults={
            "organization": company.organization,
            "display_label": display_label,
            "source_refs_json": _source_refs(
                validated, active_assumptions, open_questions, artifacts
            ),
            "json_state": json_state,
            "markdown_summary": _markdown_summary(json_state),
            "generated_by": "system",
        },
    )
    return projection


def materialize_service_history_projection(
    *,
    company: Graph,
    program: CompanyProgram | None = None,
    projection_type: str = "client_service_history",
    display_label: str = "Service History",
) -> StateProjection:
    asset_query = Asset.objects.filter(company=company)
    evaluation_query = EvaluationRun.objects.filter(company=company)
    signal_query = CompanySignal.objects.filter(company=company)
    decision_query = ValidationDecision.objects.filter(company=company)
    report_query = ReportRun.objects.filter(company=company)
    if program is not None:
        asset_query = asset_query.filter(metadata_json__program_id=str(program.id))
        evaluation_query = evaluation_query.filter(program=program)
        signal_query = signal_query.filter(metadata_json__program_id=str(program.id))
        decision_query = decision_query.filter(program=program)
        report_query = report_query.filter(program=program)
    service_artifacts = list(
        asset_query.filter(
            metadata_json__artifact_type__in=[
                "monthly_report",
                "monthly_kpi_scorecard",
                "client_service_history_entry",
                "client_file_record",
            ]
        ).order_by("-updated_at")[:30]
    )
    deliverables = list(asset_query.order_by("-updated_at")[:50])
    evaluations = list(evaluation_query.order_by("-created_at")[:20])
    signals = list(signal_query.order_by("-occurred_at")[:20])
    decisions = list(decision_query.order_by("-created_at")[:20])
    report_runs = list(report_query.order_by("-period_start", "-created_at")[:24])
    json_state = {
        "generated_at": timezone.now().isoformat(),
        "entries": [_service_history_entry(item) for item in report_runs],
        "service_artifacts": [artifact_payload(item) for item in service_artifacts],
        "deliverables": [artifact_payload(item) for item in deliverables],
        "evaluation_runs": [_evaluation_ref(item) for item in evaluations],
        "signals": [_signal_ref(item) for item in signals],
        "decisions": [_decision_ref(item) for item in decisions],
        "open_risks": _service_history_risks(evaluations=evaluations, signals=signals),
        "next_actions": _service_history_next_actions(evaluations=evaluations, signals=signals),
    }
    projection, _ = StateProjection.objects.update_or_create(
        company=company,
        program=program,
        projection_type=projection_type,
        defaults={
            "organization": company.organization,
            "display_label": display_label,
            "source_refs_json": _service_history_source_refs(
                artifacts=service_artifacts,
                deliverables=deliverables,
                evaluations=evaluations,
                signals=signals,
                report_runs=report_runs,
            ),
            "json_state": json_state,
            "markdown_summary": _service_history_markdown(json_state, display_label),
            "generated_by": "system",
        },
    )
    return projection


def projection_payload(projection: StateProjection) -> dict[str, Any]:
    return {
        "id": str(projection.id),
        "company_id": str(projection.company_id),
        "program_id": str(projection.program_id) if projection.program_id else None,
        "projection_type": projection.projection_type,
        "display_label": projection.display_label,
        "source_refs": projection.source_refs_json,
        "json_state": projection.json_state,
        "markdown_summary": projection.markdown_summary,
        "generated_by": projection.generated_by,
        "created_at": projection.created_at.isoformat(),
        "updated_at": projection.updated_at.isoformat(),
    }


def _assertion_ref(assertion: AssertionRecord) -> dict[str, Any]:
    return {
        "id": str(assertion.id),
        "kind": assertion.kind,
        "label": assertion.pack_label or assertion.kind.title(),
        "category": assertion.category,
        "statement": assertion.statement,
        "source": assertion.source,
        "confidence": assertion.confidence,
        "validation_status": assertion.validation_status,
    }


def _decision_ref(decision: ValidationDecision) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "decision": decision.decision,
        "category": decision.category,
        "rationale": decision.rationale,
        "assertion_id": str(decision.assertion_id) if decision.assertion_id else None,
        "asset_id": str(decision.asset_id) if decision.asset_id else None,
        "created_at": decision.created_at.isoformat(),
    }


def _finding_ref(finding: EvaluationFinding) -> dict[str, Any]:
    return {
        "id": str(finding.id),
        "severity": finding.severity,
        "issue_type": finding.issue_type,
        "message": finding.message,
        "suggested_fix": finding.suggested_fix,
        "evaluation_id": str(finding.evaluation_id),
    }


def _policy_ref(evaluation: PolicyEvaluation) -> dict[str, Any]:
    return {
        "id": str(evaluation.id),
        "action_type": evaluation.action_type,
        "risk_level": evaluation.risk_level,
        "status": evaluation.status,
        "approval_task_id": str(evaluation.approval_task_id)
        if evaluation.approval_task_id
        else None,
    }


def _stage_ref(stage: ProgramStageState) -> dict[str, Any]:
    return {
        "id": str(stage.id),
        "stage_id": stage.stage_id,
        "label": stage.label,
        "status": stage.status,
    }


def _signal_ref(signal: CompanySignal) -> dict[str, Any]:
    return {
        "id": str(signal.id),
        "signal_type": signal.signal_type,
        "signal_kind": signal.signal_kind,
        "domain_context": signal.domain_context,
        "title": signal.title,
        "summary": signal.summary,
        "status": signal.status,
        "metadata": signal.metadata_json,
    }


def _evaluation_ref(evaluation: EvaluationRun) -> dict[str, Any]:
    scorecard = EvaluationScorecard.objects.filter(evaluation=evaluation).first()
    return {
        "id": str(evaluation.id),
        "profile_id": evaluation.profile_key,
        "status": evaluation.status,
        "score": evaluation.score,
        "grade": evaluation.grade,
        "result": evaluation.result_json,
        "scorecard": {
            "dimensions": scorecard.dimensions_json,
            "composite_score": scorecard.composite_score,
            "grade": scorecard.grade,
        }
        if scorecard is not None
        else None,
        "created_at": evaluation.created_at.isoformat(),
    }


def _service_history_entry(report_run: ReportRun) -> dict[str, Any]:
    generated = (
        report_run.generated_sections_json
        if isinstance(report_run.generated_sections_json, dict)
        else {}
    )
    raw_findings = generated.get("findings")
    findings = (
        [item for item in raw_findings if isinstance(item, dict)]
        if isinstance(raw_findings, list)
        else []
    )
    raw_recommendations = generated.get("recommendations")
    recommendations = (
        [item for item in raw_recommendations if isinstance(item, dict)]
        if isinstance(raw_recommendations, list)
        else []
    )
    raw_next_actions = generated.get("next_actions")
    next_actions = (
        [item for item in raw_next_actions if isinstance(item, dict)]
        if isinstance(raw_next_actions, list)
        else []
    )
    return {
        "period_start": report_run.period_start.isoformat(),
        "period_end": report_run.period_end.isoformat(),
        "report_run_id": str(report_run.id),
        "report_artifact_id": str(report_run.artifact_id) if report_run.artifact_id else None,
        "scorecard_evaluation_run_ids": report_run.evaluation_run_ids_json,
        "metric_snapshot_id": str(report_run.metric_snapshot_id)
        if report_run.metric_snapshot_id
        else None,
        "key_artifacts": [{"type": "asset", "id": str(report_run.artifact_id)}]
        if report_run.artifact_id
        else [],
        "key_decisions": [],
        "execution_receipts": [],
        "findings": findings[:10],
        "recommendations": recommendations[:10],
        "next_actions": next_actions[:10],
        "open_blockers": [item for item in findings if item.get("level") == "needs_input"][:10],
        "created_at": report_run.created_at.isoformat(),
    }


def _service_history_source_refs(
    *,
    artifacts: list[Asset],
    deliverables: list[Asset],
    evaluations: list[EvaluationRun],
    signals: list[CompanySignal],
    report_runs: list[ReportRun] | None = None,
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    refs.extend({"type": "report_run", "id": str(item.id)} for item in (report_runs or []))
    refs.extend({"type": "asset", "id": str(item.id)} for item in artifacts)
    refs.extend({"type": "asset", "id": str(item.id)} for item in deliverables)
    refs.extend({"type": "evaluation", "id": str(item.id)} for item in evaluations)
    refs.extend({"type": "company_signal", "id": str(item.id)} for item in signals)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for ref in refs:
        key = (ref["type"], ref["id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _service_history_risks(
    *,
    evaluations: list[EvaluationRun],
    signals: list[CompanySignal],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for evaluation in evaluations:
        if evaluation.status not in {"WARN", "BLOCK"}:
            continue
        risks.append(
            {
                "type": "evaluation",
                "id": str(evaluation.id),
                "status": evaluation.status,
                "profile_id": evaluation.profile_key,
                "summary": f"{evaluation.profile_key} returned {evaluation.status}.",
            }
        )
    for signal in signals:
        if signal.source != "evaluation_scorecard":
            continue
        risks.append(
            {
                "type": "company_signal",
                "id": str(signal.id),
                "status": signal.status,
                "summary": signal.summary,
            }
        )
    return risks[:20]


def _service_history_next_actions(
    *,
    evaluations: list[EvaluationRun],
    signals: list[CompanySignal],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for signal in signals:
        metadata = signal.metadata_json if isinstance(signal.metadata_json, dict) else {}
        for operation_id in metadata.get("recommended_operation_template_ids", []) or []:
            if not str(operation_id).strip():
                continue
            actions.append(
                {
                    "source_signal_id": str(signal.id),
                    "operation_template_id": str(operation_id),
                    "reason": signal.summary,
                }
            )
    if not actions and any(item.status in {"WARN", "BLOCK"} for item in evaluations):
        actions.append(
            {
                "operation_template_id": "",
                "reason": "Review warning or blocking evaluation results.",
            }
        )
    return actions[:20]


def _service_history_markdown(state: dict[str, Any], display_label: str) -> str:
    lines = [f"# {display_label}", ""]
    entries = state.get("entries", [])
    if entries:
        lines.append("## Periodic Reviews")
        for item in entries[:10]:
            lines.append(
                f"- {item.get('period_start')} to {item.get('period_end')}: "
                f"{len(item.get('findings') or [])} findings, "
                f"{len(item.get('recommendations') or [])} recommendations"
            )
        lines.append("")
    lines.append("## Reports And Files")
    for item in state.get("service_artifacts", [])[:10]:
        lines.append(f"- {item.get('title')} ({item.get('artifact_type')})")
    lines.append("")
    lines.append("## Evaluation Runs")
    for item in state.get("evaluation_runs", [])[:10]:
        lines.append(f"- {item.get('profile_id')}: {item.get('status')} ({item.get('score')})")
    risks = state.get("open_risks", [])
    if risks:
        lines.append("")
        lines.append("## Open Risks")
        for item in risks[:10]:
            lines.append(f"- {item.get('summary')}")
    actions = state.get("next_actions", [])
    if actions:
        lines.append("")
        lines.append("## Next Actions")
        for item in actions[:10]:
            lines.append(f"- {item.get('operation_template_id') or item.get('reason')}")
    return "\n".join(lines)


def _source_refs(
    validated: list[AssertionRecord],
    assumptions: list[AssertionRecord],
    questions: list[AssertionRecord],
    artifacts: list[Asset],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    refs.extend({"type": "assertion", "id": str(item.id)} for item in validated)
    refs.extend({"type": "assertion", "id": str(item.id)} for item in assumptions)
    refs.extend({"type": "assertion", "id": str(item.id)} for item in questions)
    refs.extend({"type": "asset", "id": str(item.id)} for item in artifacts)
    return refs


def _next_action(
    *,
    program: CompanyProgram | None,
    open_questions: list[AssertionRecord],
    qa_blockers: list[EvaluationFinding],
    policy_blockers: list[PolicyEvaluation],
    stage_blockers: list[ProgramStageState],
    signals: list[CompanySignal],
) -> str:
    if qa_blockers:
        return "Resolve blocking evaluation findings before external side effects."
    if policy_blockers:
        return "Resolve policy blockers or approvals before execution."
    rerun_stage = next(
        (stage for stage in stage_blockers if stage.status == "rerun_required"), None
    )
    if rerun_stage is not None:
        return f"Review and execute rework for {rerun_stage.label}."
    if open_questions:
        return "Resolve open research questions before treating them as currently true."
    if signals:
        return "Review recent company signals and launch the next recommended operation."
    if program is not None and program.status != "completed":
        return f"Continue {program.display_label} at stage {program.current_stage_id}."
    return "Review current state and launch the next company operation."


def _markdown_summary(state: dict[str, Any]) -> str:
    lines = ["# Currently True", ""]
    lines.append("## Validated Facts")
    for item in state.get("validated_facts", [])[:10]:
        lines.append(f"- {item.get('statement')}")
    lines.append("")
    lines.append("## Active Assumptions")
    for item in state.get("active_assumptions", [])[:10]:
        lines.append(f"- {item.get('statement')}")
    lines.append("")
    lines.append("## Open Questions")
    for item in state.get("open_questions", [])[:10]:
        lines.append(f"- {item.get('statement')}")
    lines.append("")
    blockers = (
        state.get("qa_blockers", [])
        + state.get("policy_blockers", [])
        + state.get("stage_blockers", [])
    )
    if blockers:
        lines.append("## Blockers")
        for item in blockers[:10]:
            lines.append(f"- {item.get('message') or item.get('action_type') or item.get('label')}")
        lines.append("")
    lines.append("## Canonical Artifacts")
    for item in state.get("canonical_artifacts", [])[:10]:
        lines.append(f"- {item.get('title')} ({item.get('artifact_type')})")
    lines.append("")
    lines.append(f"Next action: {state.get('next_recommended_action')}")
    return "\n".join(lines)
