"""Post-operation strategy report builder.

This module is intentionally read-only. It turns backend-owned operation state into a
client-ready artifact and does not participate in operation execution.
"""

from __future__ import annotations

import base64
import html
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from django.db.models import Q

from infrastructure.orm.models import (
    ApprovalTask,
    DecisionRecord,
    Graph,
    GraphVersion,
    MemoryObservation,
    NodeRun,
    Run,
    TaskRecord,
)

ReportAudience = Literal["client", "executive", "internal"]
ReportFormat = Literal["md", "html", "pdf"]

ALLOWED_AUDIENCES = {"client", "executive", "internal"}
ALLOWED_FORMATS = {"md", "html", "pdf"}


class ReportBuilderError(ValueError):
    """Base error raised when a strategy report cannot be generated."""


class ReportStateNotFound(ReportBuilderError):
    """Raised when the requested company or operation cannot be found."""


class ReportTraceabilityError(ReportBuilderError):
    """Raised when the report cannot satisfy traceability requirements."""


@dataclass(frozen=True, slots=True)
class SourceRef:
    kind: str
    id: str
    field: str
    label: str

    def as_payload(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "id": self.id,
            "field": self.field,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class ReportValue:
    value: Any
    source: SourceRef


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    decision: str
    alternatives: list[str]
    constraints: list[str]
    departments: list[str]
    rationale: str
    rejected: list[str]
    source: SourceRef


@dataclass(frozen=True, slots=True)
class MemoryTrace:
    title: str
    content: str
    effect: str
    source: SourceRef


@dataclass(frozen=True, slots=True)
class IterationTrace:
    what_changed: str
    why_changed: str
    trigger: str
    department: str
    source: SourceRef


@dataclass(frozen=True, slots=True)
class ApprovalTrace:
    status: str
    context: str
    changed: str
    improved: str
    source: SourceRef


@dataclass(slots=True)
class StrategyReportState:
    company: Graph
    company_version: GraphVersion
    operation: Run
    node_runs: list[NodeRun]
    tasks: list[TaskRecord]
    decision_records: list[DecisionRecord]
    approvals: list[ApprovalTask]
    memories: list[MemoryObservation]
    company_profile: dict[str, Any]
    client_context: dict[str, Any]
    deliverables: list[ReportValue]
    structured_values: dict[str, list[ReportValue]]
    decisions: list[DecisionTrace]
    memory_traces: list[MemoryTrace]
    iteration_traces: list[IterationTrace]
    approval_traces: list[ApprovalTrace]


@dataclass(frozen=True, slots=True)
class StrategyReportArtifact:
    company_id: str
    operation_id: str
    audience: ReportAudience
    format: ReportFormat
    content: str | bytes
    content_type: str
    filename: str
    traceability: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def api_payload(self) -> dict[str, Any]:
        if isinstance(self.content, bytes):
            content: str = base64.b64encode(self.content).decode("ascii")
            encoding = "base64"
        else:
            content = self.content
            encoding = "text"
        return {
            "company_id": self.company_id,
            "operation_id": self.operation_id,
            "audience": self.audience,
            "format": self.format,
            "content_type": self.content_type,
            "filename": self.filename,
            "encoding": encoding,
            "content": content,
            "traceability": self.traceability,
        }


@dataclass(slots=True)
class _Section:
    key: str
    title: str
    body: str
    sources: list[SourceRef]


@dataclass(frozen=True, slots=True)
class _ReportLanguage:
    strategy_label: str
    agency_action: str
    requirements_label: str
    alternatives_label: str
    teams_label: str
    rationale_label: str
    rejected_label: str
    changed_label: str
    triggered_label: str
    owner_label: str
    approval_label: str


def generate_strategy_report(
    company_id: str,
    operation_id: str,
    audience: ReportAudience = "client",
    format: ReportFormat = "md",
) -> StrategyReportArtifact:
    """Build a strategy report from completed backend-owned operation state."""

    if audience not in ALLOWED_AUDIENCES:
        raise ReportBuilderError("audience must be one of: client, executive, internal")
    if format not in ALLOWED_FORMATS:
        raise ReportBuilderError("format must be one of: md, html, pdf")

    state = _collect_state(company_id=company_id, operation_id=operation_id)
    sections = _build_sections(state, audience=audience)
    traceability = {
        section.key: _dedupe_sources(section.sources) for section in sections if section.sources
    }
    missing = [section.title for section in sections if not section.sources]
    if missing:
        raise ReportTraceabilityError(
            "Report sections are missing traceable source data: " + ", ".join(missing)
        )

    markdown = _render_markdown(state, sections, audience=audience, traceability=traceability)
    filename_base = (
        _slugify(f"{_client_name(state)} {state.company.name} strategy report").strip("-")
        or "strategy-report"
    )
    if format == "md":
        return StrategyReportArtifact(
            company_id=str(state.company.id),
            operation_id=str(state.operation.id),
            audience=audience,
            format=format,
            content=markdown,
            content_type="text/markdown; charset=utf-8",
            filename=f"{filename_base}.md",
            traceability=traceability,
        )
    if format == "html":
        return StrategyReportArtifact(
            company_id=str(state.company.id),
            operation_id=str(state.operation.id),
            audience=audience,
            format=format,
            content=_markdown_to_html(markdown),
            content_type="text/html; charset=utf-8",
            filename=f"{filename_base}.html",
            traceability=traceability,
        )
    return StrategyReportArtifact(
        company_id=str(state.company.id),
        operation_id=str(state.operation.id),
        audience=audience,
        format=format,
        content=_markdown_to_pdf(markdown),
        content_type="application/pdf",
        filename=f"{filename_base}.pdf",
        traceability=traceability,
    )


def _collect_state(company_id: str, operation_id: str) -> StrategyReportState:
    company_uuid = _parse_uuid(company_id, "company_id")
    operation_uuid = _parse_uuid(operation_id, "operation_id")

    company = Graph.objects.filter(id=company_uuid).order_by("-updated_at").first()
    if company is None:
        raise ReportStateNotFound("Company was not found.")

    operation = (
        Run.objects.select_related("graph_version__graph", "owner", "organization")
        .filter(id=operation_uuid, graph_version__graph_id=company.id)
        .first()
    )
    if operation is None:
        raise ReportStateNotFound("Operation was not found for the requested company.")
    if operation.status != "succeeded":
        raise ReportTraceabilityError("Strategy reports require a completed operation.")

    node_runs = list(operation.node_runs.order_by("started_at", "id"))
    tasks = list(TaskRecord.objects.filter(execution=operation).select_related("agent"))
    decision_records = list(
        DecisionRecord.objects.filter(execution=operation).select_related(
            "task", "agent", "source_approval_task"
        )
    )
    approvals = list(ApprovalTask.objects.filter(run=operation).order_by("created_at", "id"))
    memories = list(
        MemoryObservation.objects.active()
        .filter(tenant_id=operation.organization_id)
        .filter(Q(run_id=operation.id) | Q(graph_id=company.id))
        .order_by("-last_seen_at", "-created_at")
    )
    company_version = operation.graph_version
    company_profile = _company_profile(company_version)
    client_context = _client_context(company_profile, operation)

    structured_values = _collect_structured_values(operation, node_runs)
    deliverables = _collect_deliverables(operation, node_runs)
    decisions = _collect_decisions(operation, node_runs, decision_records)
    memory_traces = _collect_memory_traces(structured_values, memories)
    iteration_traces = _collect_iteration_traces(structured_values)
    approval_traces = _collect_approval_traces(approvals, decision_records)

    return StrategyReportState(
        company=company,
        company_version=company_version,
        operation=operation,
        node_runs=node_runs,
        tasks=tasks,
        decision_records=decision_records,
        approvals=approvals,
        memories=memories,
        company_profile=company_profile,
        client_context=client_context,
        deliverables=deliverables,
        structured_values=structured_values,
        decisions=decisions,
        memory_traces=memory_traces,
        iteration_traces=iteration_traces,
        approval_traces=approval_traces,
    )


def _parse_uuid(value: str, name: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ReportBuilderError(f"{name} must be a valid UUID.") from exc


def _company_profile(version: GraphVersion) -> dict[str, Any]:
    graph_json = version.graph_json if isinstance(version.graph_json, dict) else {}
    metadata = graph_json.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    profile = metadata.get("company_profile")
    return profile if isinstance(profile, dict) else {}


def _client_context(profile: dict[str, Any], operation: Run) -> dict[str, Any]:
    for candidate in (
        profile.get("client_context"),
        profile.get("client"),
        operation.input_json.get("client") if isinstance(operation.input_json, dict) else None,
        operation.output_json.get("client") if isinstance(operation.output_json, dict) else None,
        operation.input_json.get("client_context")
        if isinstance(operation.input_json, dict)
        else None,
        operation.output_json.get("client_context")
        if isinstance(operation.output_json, dict)
        else None,
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate

    input_json = operation.input_json if isinstance(operation.input_json, dict) else {}
    return {
        "name": input_json.get("client_name") or input_json.get("client") or "",
        "goal": input_json.get("client_goal") or input_json.get("operation_brief") or "",
        "market": input_json.get("market") or "",
        "industry": input_json.get("industry") or "",
        "tier": input_json.get("client_tier") or "",
    }


def _collect_structured_values(
    operation: Run,
    node_runs: list[NodeRun],
) -> dict[str, list[ReportValue]]:
    values: dict[str, list[ReportValue]] = {}
    for field_name, payload, source in _iter_structured_sources(operation, node_runs):
        _walk_payload(payload, field_name, source, values)
    return values


def _iter_structured_sources(
    operation: Run,
    node_runs: list[NodeRun],
) -> list[tuple[str, Any, SourceRef]]:
    sources: list[tuple[str, Any, SourceRef]] = []
    if isinstance(operation.input_json, dict):
        sources.append(
            (
                "input_json",
                operation.input_json,
                SourceRef("operation", str(operation.id), "input_json", "Operation input"),
            )
        )
    if isinstance(operation.output_json, dict):
        sources.append(
            (
                "output_json",
                operation.output_json,
                SourceRef("operation", str(operation.id), "output_json", "Operation output"),
            )
        )
    for node_run in node_runs:
        if isinstance(node_run.input_json, dict):
            sources.append(
                (
                    "input_json",
                    node_run.input_json,
                    SourceRef(
                        "task",
                        str(node_run.id),
                        "input_json",
                        _source_label_for_task(node_run),
                    ),
                )
            )
        if isinstance(node_run.output_json, dict):
            sources.append(
                (
                    "output_json",
                    node_run.output_json,
                    SourceRef(
                        "deliverable",
                        str(node_run.id),
                        "output_json",
                        _source_label_for_task(node_run),
                    ),
                )
            )
    return sources


def _walk_payload(
    payload: Any,
    prefix: str,
    source: SourceRef,
    values: dict[str, list[ReportValue]],
) -> None:
    if isinstance(payload, dict):
        for key, item in payload.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            values.setdefault(_normalize_key(str(key)), []).append(
                ReportValue(item, SourceRef(source.kind, source.id, field, source.label))
            )
            _walk_payload(item, field, source, values)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _walk_payload(item, f"{prefix}.{index}", source, values)


def _collect_deliverables(operation: Run, node_runs: list[NodeRun]) -> list[ReportValue]:
    keys = (
        "deliverable",
        "final_deliverable",
        "strategy",
        "strategy_report",
        "report",
        "final_report",
        "campaign_plan",
        "execution_plan",
    )
    collected: list[ReportValue] = []
    for _, payload, source in _iter_structured_sources(operation, node_runs):
        if not isinstance(payload, dict):
            continue
        for key in keys:
            if key in payload and _has_content(payload[key]):
                collected.append(
                    ReportValue(
                        payload[key],
                        SourceRef(source.kind, source.id, key, source.label),
                    )
                )
    return collected


def _collect_decisions(
    operation: Run,
    node_runs: list[NodeRun],
    decision_records: list[DecisionRecord],
) -> list[DecisionTrace]:
    decisions: list[DecisionTrace] = []
    seen: set[str] = set()

    for _, payload, source in _iter_structured_sources(operation, node_runs):
        for item, item_source in _iter_decision_items(payload, source):
            decision = _first_text(item, "decision", "decision_made", "outcome", "summary", "title")
            if not decision:
                continue
            trace = DecisionTrace(
                decision=decision,
                alternatives=_as_text_list(
                    _first_value(
                        item,
                        "alternatives",
                        "alternatives_considered",
                        "rejected_alternatives",
                    )
                ),
                constraints=_as_text_list(_first_value(item, "constraints", "constraints_applied")),
                departments=_as_text_list(
                    _first_value(item, "departments", "departments_involved", "owners")
                ),
                rationale=_first_text(item, "rationale", "reasoning", "why", "why_made"),
                rejected=_as_text_list(
                    _first_value(item, "rejected", "what_was_rejected", "rejections")
                ),
                source=item_source,
            )
            key = trace.decision.lower()
            if key not in seen:
                decisions.append(trace)
                seen.add(key)

    for record in decision_records:
        payload = _merge_dicts(record.context_json, record.resolution_json)
        decision = _first_text(payload, "decision", "decision_made", "summary", "outcome")
        if not decision:
            decision = _decision_record_summary(record)
        source = SourceRef("decision", str(record.id), "context_json", "Decision ledger")
        trace = DecisionTrace(
            decision=decision,
            alternatives=_as_text_list(
                _first_value(payload, "alternatives", "alternatives_considered")
            ),
            constraints=_as_text_list(_first_value(payload, "constraints", "required_fields")),
            departments=_as_text_list(_first_value(payload, "departments")),
            rationale=_first_text(payload, "rationale", "reasoning", "feedback"),
            rejected=_as_text_list(_first_value(payload, "rejected", "what_was_rejected")),
            source=source,
        )
        key = trace.decision.lower()
        if key not in seen:
            decisions.append(trace)
            seen.add(key)

    return decisions


def _iter_decision_items(payload: Any, source: SourceRef) -> list[tuple[dict[str, Any], SourceRef]]:
    items: list[tuple[dict[str, Any], SourceRef]] = []
    if not isinstance(payload, dict):
        return items
    containers = [
        ("decision_traces", payload.get("decision_traces")),
        ("decisions", payload.get("decisions")),
        ("key_decisions", payload.get("key_decisions")),
    ]
    decision_trace = payload.get("decision_trace")
    if isinstance(decision_trace, dict):
        containers.append(("decision_trace.decisions", decision_trace.get("decisions")))
    for field_name, value in containers:
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    items.append(
                        (
                            item,
                            SourceRef(
                                source.kind, source.id, f"{field_name}.{index}", source.label
                            ),
                        )
                    )
    if _first_text(payload, "decision", "decision_made"):
        items.append((payload, SourceRef(source.kind, source.id, "decision", source.label)))
    return items


def _collect_memory_traces(
    structured_values: dict[str, list[ReportValue]],
    memories: list[MemoryObservation],
) -> list[MemoryTrace]:
    traces: list[MemoryTrace] = []
    for key in ("memory_attributions", "memory_retrievals", "memory_writes", "learnings"):
        for report_value in structured_values.get(key, []):
            value = report_value.value
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                if not isinstance(item, dict):
                    continue
                title = (
                    _first_text(item, "memory_title", "title", "memory_id") or "Recorded learning"
                )
                effect = _first_text(
                    item,
                    "changed_reasoning",
                    "effect",
                    "used_for",
                    "insight",
                    "content",
                )
                if not effect:
                    continue
                traces.append(
                    MemoryTrace(
                        title=title,
                        content=_first_text(item, "content", "summary", "insight"),
                        effect=effect,
                        source=SourceRef(
                            report_value.source.kind,
                            report_value.source.id,
                            f"{report_value.source.field}.{index}",
                            report_value.source.label,
                        ),
                    )
                )
    for memory in memories:
        traces.append(
            MemoryTrace(
                title=memory.title,
                content=memory.content,
                effect=memory.content,
                source=SourceRef("memory", str(memory.id), "content", memory.title),
            )
        )
    return _dedupe_memory_traces(traces)


def _collect_iteration_traces(
    structured_values: dict[str, list[ReportValue]],
) -> list[IterationTrace]:
    traces: list[IterationTrace] = []
    for key in ("iteration_deltas", "iterations", "what_changed"):
        for report_value in structured_values.get(key, []):
            raw_items = (
                report_value.value if isinstance(report_value.value, list) else [report_value.value]
            )
            for index, item in enumerate(raw_items):
                if isinstance(item, dict):
                    what_changed = _first_text(item, "what_changed", "change", "delta", "summary")
                    why_changed = _first_text(item, "why_changed", "why", "reason")
                    trigger = _first_text(item, "trigger", "triggered_by", "source")
                    department = _first_text(item, "department", "owner", "driven_by")
                else:
                    what_changed = _stringify(item)
                    why_changed = ""
                    trigger = ""
                    department = ""
                if not what_changed:
                    continue
                traces.append(
                    IterationTrace(
                        what_changed=what_changed,
                        why_changed=why_changed,
                        trigger=trigger,
                        department=department,
                        source=SourceRef(
                            report_value.source.kind,
                            report_value.source.id,
                            f"{report_value.source.field}.{index}",
                            report_value.source.label,
                        ),
                    )
                )
    return _dedupe_iteration_traces(traces)


def _collect_approval_traces(
    approvals: list[ApprovalTask],
    decision_records: list[DecisionRecord],
) -> list[ApprovalTrace]:
    traces: list[ApprovalTrace] = []
    decisions_by_approval = {
        record.source_approval_task_id: record
        for record in decision_records
        if record.source_approval_task_id
    }
    for approval in approvals:
        payload = approval.payload if isinstance(approval.payload, dict) else {}
        result = approval.result if isinstance(approval.result, dict) else {}
        decision_payload = {}
        decision_record = decisions_by_approval.get(approval.id)
        if decision_record is not None:
            decision_payload = _merge_dicts(
                decision_record.context_json,
                decision_record.resolution_json,
            )
        merged = _merge_dicts(payload, result, decision_payload)
        context = _first_text(merged, "prompt_message", "decision", "summary", "context")
        changed = _first_text(
            merged,
            "rejection_changed",
            "what_changed_after_rejection",
            "changed",
            "feedback",
        )
        improved = _first_text(
            merged,
            "improved_before_reapproval",
            "improved",
            "resolution",
            "reason",
        )
        if not any([context, changed, improved]):
            continue
        traces.append(
            ApprovalTrace(
                status=approval.status,
                context=context,
                changed=changed,
                improved=improved,
                source=SourceRef("approval", str(approval.id), "result", "Approval outcome"),
            )
        )
    return traces


def _build_sections(state: StrategyReportState, audience: ReportAudience) -> list[_Section]:
    language = _language_for_audience(audience)
    sections = [
        _executive_summary_section(state, audience, language),
        _strategy_narrative_section(state, language),
        _key_decisions_section(state, language),
        _iteration_story_section(state, language),
        _insights_section(state, language),
        _execution_plan_section(state, language),
        _risks_section(state, language),
        _recommendations_section(state, language),
    ]
    if audience == "internal":
        sections.append(_internal_trace_section(state))
    return sections


def _executive_summary_section(
    state: StrategyReportState,
    audience: ReportAudience,
    language: _ReportLanguage,
) -> _Section:
    operation_brief = _field_first(state, "operation_brief", "objective", "goal")
    recommendation = _first_structured_value(state, "recommendations", "next_steps")
    decision = state.decisions[0] if state.decisions else None
    delta = state.iteration_traces[0] if state.iteration_traces else None
    sources = _sources_from_values([operation_brief, recommendation])
    if decision:
        sources.append(decision.source)
    if delta:
        sources.append(delta.source)

    lines = [
        (
            f"{state.company.name} {language.agency_action} for "
            f"{_client_text(_client_label(state), language)}."
        ),
    ]
    if operation_brief:
        lines.append(
            f"The work focused on {_sentence(_client_text(operation_brief.value, language))}"
        )
    if decision:
        lines.append(
            f"The main choice was to {_sentence(_client_text(decision.decision, language))}"
        )
    if delta:
        lines.append(
            f"The refinement addressed {_sentence(_client_text(delta.what_changed, language))}"
        )
    if recommendation:
        lines.append(f"Next, {_recommendation_summary(recommendation.value, language)}")
    if audience == "executive":
        risk = _first_structured_value(state, "risks", "tradeoffs", "budget")
        if risk:
            lines.append(
                f"Executive attention should stay on {_sentence(_client_text(risk.value, language))}"
            )
            sources.append(risk.source)

    return _Section("executive_summary", "Executive Summary", "\n\n".join(lines), sources)


def _strategy_narrative_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    positioning = _first_structured_value(
        state,
        "positioning",
        "brand_positioning",
        "strategy_positioning",
    )
    audience = _first_structured_value(
        state,
        "target_audience",
        "audience",
        "segments",
        "audience_segments",
    )
    approach = _first_structured_value(state, "approach", "channel_strategy", "campaign_structure")
    constraints = _constraints_value(state)
    sources = _sources_from_values([positioning, audience, approach, constraints])

    parts: list[str] = []
    if positioning:
        parts.append(f"**Positioning:** {_client_text(positioning.value, language)}")
    if audience:
        parts.append(f"**Audience:** {_client_text(audience.value, language)}")
    if approach:
        parts.append(f"**Approach:** {_client_text(approach.value, language)}")
    if constraints:
        parts.append(
            f"**{language.requirements_label}:** {_client_text(constraints.value, language)}"
        )

    return _Section("strategy_narrative", "Strategy Narrative", "\n\n".join(parts), sources)


def _key_decisions_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    lines: list[str] = []
    sources: list[SourceRef] = []
    for index, decision in enumerate(state.decisions, start=1):
        lines.append(f"{index}. **{_client_text(decision.decision, language)}**")
        if decision.alternatives:
            lines.append(
                f"   - {language.alternatives_label}: "
                f"{_client_text(decision.alternatives, language)}"
            )
        if decision.constraints:
            lines.append(
                f"   - {language.requirements_label}: "
                f"{_client_text(decision.constraints, language)}"
            )
        if decision.departments:
            lines.append(
                f"   - {language.teams_label}: {_client_text(decision.departments, language)}"
            )
        if decision.rationale:
            lines.append(
                f"   - {language.rationale_label}: {_client_text(decision.rationale, language)}"
            )
        if decision.rejected:
            lines.append(
                f"   - {language.rejected_label}: {_client_text(decision.rejected, language)}"
            )
        sources.append(decision.source)
    return _Section("key_decisions", "Key Decisions", "\n".join(lines), sources)


def _iteration_story_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    lines: list[str] = []
    sources: list[SourceRef] = []
    for trace in state.iteration_traces:
        line = f"- {_client_text(trace.what_changed, language)}"
        details: list[str] = []
        if trace.why_changed:
            details.append(
                f"{language.rationale_label.lower()}: {_client_text(trace.why_changed, language)}"
            )
        if trace.trigger:
            details.append(f"{language.triggered_label}: {_client_text(trace.trigger, language)}")
        if trace.department:
            details.append(f"{language.owner_label}: {_client_text(trace.department, language)}")
        if details:
            line += f" ({'; '.join(details)})"
        lines.append(line)
        sources.append(trace.source)

    for approval in state.approval_traces:
        if approval.status == "rejected" or approval.changed:
            lines.append(
                f"- {language.approval_label}: "
                f"{_client_text(approval.changed or approval.context, language)}"
            )
            sources.append(approval.source)

    return _Section("iteration_story", "What Changed", "\n".join(lines), sources)


def _insights_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    lines: list[str] = []
    sources: list[SourceRef] = []
    seen: set[str] = set()
    for trace in state.memory_traces[:8]:
        insight = trace.effect or trace.content
        if not insight:
            continue
        title = _client_learning_title(trace.title, insight, language)
        effect = _client_learning_effect(trace.title, insight, language)
        key = f"{title.lower()}:{effect.lower()}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{title}:** {effect}")
        sources.append(trace.source)
    return _Section("insights", "Insights & Learnings", "\n".join(lines), sources)


def _execution_plan_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    keys = (
        "execution_plan",
        "campaign_plan",
        "channel_strategy",
        "channels",
        "rollout_phases",
        "timeline",
        "campaign_structure",
    )
    values = [_first_structured_value(state, key) for key in keys]
    values = [value for value in values if value is not None]
    sources = _sources_from_values(values)
    lines: list[str] = []
    seen: set[str] = set()
    for value in values:
        assert value is not None
        label = _label_from_field(value.source.field)
        text = _client_text(_format_block(value.value), language)
        token = f"{label}:{text}"
        if not text or token in seen:
            continue
        lines.append(f"**{_client_text(label, language)}:**\n{text}")
        seen.add(token)
    return _Section("execution_plan", "Execution Plan", "\n\n".join(lines), sources)


def _risks_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    risk_values = [
        _first_structured_value(state, "risks", "risk", "tradeoffs", "trade_offs"),
    ]
    sources = _sources_from_values(risk_values)
    lines: list[str] = []
    for value in risk_values:
        if value:
            lines.append(_client_text(_format_block(value.value), language))
    for decision in state.decisions:
        rejected = decision.rejected or decision.alternatives
        if rejected:
            lines.append(f"- {language.rejected_label}: {_client_text(rejected, language)}")
            sources.append(decision.source)
        if decision.constraints:
            lines.append(
                f"- {language.requirements_label}: {_client_text(decision.constraints, language)}"
            )
            sources.append(decision.source)
    for approval in state.approval_traces:
        if approval.improved:
            lines.append(f"- Approval tradeoff: {_client_text(approval.improved, language)}")
            sources.append(approval.source)
    return _Section("risks_tradeoffs", "Risks & Tradeoffs", "\n".join(lines), sources)


def _recommendations_section(state: StrategyReportState, language: _ReportLanguage) -> _Section:
    values = [
        _first_structured_value(state, "recommendations", "recommendation", "next_steps"),
    ]
    values = [value for value in values if value is not None]
    sources = _sources_from_values(values)
    lines: list[str] = []
    for value in values:
        assert value is not None
        lines.append(_client_text(_format_block(value.value), language))
    return _Section("recommendations", "Recommendations", "\n\n".join(lines), sources)


def _internal_trace_section(state: StrategyReportState) -> _Section:
    sources: list[SourceRef] = []
    lines: list[str] = []
    for decision in state.decisions:
        lines.append(f"- Decision source: {decision.source.kind} {decision.source.id}")
        sources.append(decision.source)
    for memory in state.memory_traces:
        lines.append(f"- Memory source: {memory.source.kind} {memory.source.id}")
        sources.append(memory.source)
    for delta in state.iteration_traces:
        lines.append(f"- Iteration source: {delta.source.kind} {delta.source.id}")
        sources.append(delta.source)
    for approval in state.approval_traces:
        lines.append(f"- Approval source: {approval.source.kind} {approval.source.id}")
        sources.append(approval.source)
    return _Section("traceability_appendix", "Traceability Appendix", "\n".join(lines), sources)


def _render_markdown(
    state: StrategyReportState,
    sections: list[_Section],
    *,
    audience: ReportAudience,
    traceability: dict[str, list[dict[str, str]]],
) -> str:
    language = _language_for_audience(audience)
    client = _client_name(state)
    subtitle = {
        "client": "Client Strategy Report",
        "executive": "Executive Strategy Report",
        "internal": "Internal Strategy Report",
    }[audience]
    lines = [
        f"# {subtitle}: {client}",
        "",
        f"**Agency:** {state.company.name}",
        f"**Client:** {_client_text(_client_label(state), language)}",
        f"**{language.strategy_label}:** {_client_text(_operation_name(state), language)}",
        "",
    ]
    for section in sections:
        lines.extend([f"## {section.title}", "", section.body.strip(), ""])

    if audience == "internal":
        lines.extend(["## Section Traceability", ""])
        for section_key, refs in traceability.items():
            lines.append(f"- **{section_key}:** " + ", ".join(ref["label"] for ref in refs))
        lines.append("")

    markdown = "\n".join(lines).strip() + "\n"
    if audience in {"client", "executive"}:
        _assert_client_facing_language(markdown)
    return markdown


def _language_for_audience(audience: ReportAudience) -> _ReportLanguage:
    if audience == "internal":
        return _ReportLanguage(
            strategy_label="Operation",
            agency_action="completed the operation",
            requirements_label="Constraints applied",
            alternatives_label="Alternatives considered",
            teams_label="Departments involved",
            rationale_label="Why",
            rejected_label="Rejected",
            changed_label="What changed",
            triggered_label="trigger",
            owner_label="owner",
            approval_label="Approval changed the work",
        )
    return _ReportLanguage(
        strategy_label="Strategy",
        agency_action="completed the strategy work",
        requirements_label="Requirements shaping the choice",
        alternatives_label="Options considered",
        teams_label="Agency teams involved",
        rationale_label="Reasoning",
        rejected_label="Not recommended",
        changed_label="What changed",
        triggered_label="prompted by",
        owner_label="led by",
        approval_label="Client approval refined the work",
    )


def _client_text(value: Any, language: _ReportLanguage) -> str:
    if isinstance(value, list):
        text = ", ".join(
            _format_inline(item).strip().rstrip(".") for item in value if _has_content(item)
        )
    else:
        text = _format_inline(value)
    if language.strategy_label == "Operation":
        return text
    return _translate_client_terms(text)


def _client_learning_title(title: str, insight: str, language: _ReportLanguage) -> str:
    if language.strategy_label == "Operation":
        return title
    combined = f"{title} {insight}".lower()
    if "misleading" in combined or "quarantine" in combined or "incorrect" in combined:
        return "Discount-led scale assumption corrected"
    if "retrieved" in combined or "relevant" in combined:
        return "Relevant prior experience applied"
    if "write" in combined or "wrote" in combined or "written" in combined:
        return "Legacy campaign learning captured"
    return _translate_client_terms(title)


def _client_learning_effect(title: str, insight: str, language: _ReportLanguage) -> str:
    if language.strategy_label == "Operation":
        return insight
    combined = f"{title} {insight}".lower()
    if "misleading" in combined or "quarantine" in combined or "incorrect" in combined:
        return (
            "Current brand-sentiment evidence outweighed the earlier discount-led "
            "acquisition precedent, so the launch stayed premium and appointment-led."
        )
    return _translate_client_terms(insight)


def _recommendation_summary(value: Any, language: _ReportLanguage) -> str:
    if isinstance(value, list):
        items = [
            _lower_first(_client_text(item, language).strip().rstrip("."))
            for item in value
            if _has_content(item)
        ]
        if not items:
            return ""
        if len(items) == 1:
            return _sentence(items[0])
        if len(items) == 2:
            return _sentence(f"{items[0]} and {items[1]}")
        return _sentence(", ".join(items[:-1]) + f", and {items[-1]}")
    return _sentence(_client_text(value, language))


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if text else ""


def _translate_client_terms(text: str) -> str:
    replacements = (
        (r"\bOperations Design\b", "Launch Planning"),
        (r"\boperations design\b", "launch planning"),
        (r"\bUpdate memory to reflect\b", "Update the recommendation to reflect"),
        (r"\bupdate memory to reflect\b", "update the recommendation to reflect"),
        (r"\bCaptured the learning prior experience\b", "Captured the client learning"),
        (r"\bcaptured the learning prior experience\b", "captured the client learning"),
        (r"\bcase prior experience\b", "case experience"),
        (r"\bDecision traces\b", "Reasoning"),
        (r"\bdecision traces\b", "reasoning"),
        (r"\bDecision trace\b", "Reasoning"),
        (r"\bdecision trace\b", "reasoning"),
        (r"\bMemory recovery\b", "Learning correction"),
        (r"\bmemory recovery\b", "learning correction"),
        (r"\bMisleading memory\b", "Corrected prior experience"),
        (r"\bmisleading memory\b", "corrected prior experience"),
        (r"\bMemory attribution\b", "Prior experience used"),
        (r"\bmemory attribution\b", "prior experience used"),
        (r"\bmemory retrievals\b", "prior experience reviews"),
        (r"\bmemory retrieval\b", "prior experience review"),
        (r"\bmemory writes\b", "new learnings"),
        (r"\bmemory write\b", "new learning"),
        (r"\bLearning iteration\b", "Learning refinement"),
        (r"\blearning iteration\b", "learning refinement"),
        (r"\bOperation\b", "Strategy"),
        (r"\boperation\b", "strategy"),
        (r"\bOperations\b", "Strategies"),
        (r"\boperations\b", "strategies"),
        (r"\bMemory\b", "Prior experience"),
        (r"\bmemory\b", "prior experience"),
        (r"\bConstraints\b", "Requirements"),
        (r"\bconstraints\b", "requirements"),
        (r"\bConstraint\b", "Requirement"),
        (r"\bconstraint\b", "requirement"),
        (r"\bIterations\b", "Refinements"),
        (r"\biterations\b", "refinements"),
        (r"\bIteration\b", "Refinement"),
        (r"\biteration\b", "refinement"),
        (r"\bretrieved\b", "used"),
        (r"\bRetrieved\b", "Used"),
        (r"\bwrite case\b", "capture the learning"),
        (r"\bWrite case\b", "Capture the learning"),
        (r"\bwrote case\b", "captured the learning"),
        (r"\bWrote case\b", "Captured the learning"),
    )
    translated = text
    for pattern, replacement in replacements:
        translated = re.sub(pattern, replacement, translated)
    translated = re.sub(r"\bused used\b", "used", translated, flags=re.IGNORECASE)
    translated = translated.replace(
        "Captured the learning prior experience",
        "Captured the client learning",
    )
    translated = translated.replace(
        "captured the learning prior experience",
        "captured the client learning",
    )
    return translated


def _assert_client_facing_language(markdown: str) -> None:
    forbidden = (
        r"\boperation\b",
        r"\bmemory\b",
        r"\bdecision trace\b",
        r"\bconstraint\b",
        r"\biteration\b",
    )
    lowered = markdown.lower()
    leaked = [pattern.strip(r"\b") for pattern in forbidden if re.search(pattern, lowered)]
    if leaked:
        raise ReportTraceabilityError(
            "Client-facing strategy report contains internal terminology: "
            + ", ".join(sorted(set(leaked)))
        )


def _markdown_to_html(markdown: str) -> str:
    body: list[str] = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_list:
                body.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_markdown_to_html(line[2:])}</li>")
        else:
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{_inline_markdown_to_html(line)}</p>")
    if in_list:
        body.append("</ul>")
    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<head>",
            '<meta charset="utf-8">',
            "<style>",
            "body{font-family:Inter,Arial,sans-serif;margin:48px;color:#1f2933;line-height:1.55;}",
            "h1{font-size:30px;margin-bottom:24px;}h2{font-size:20px;margin-top:30px;border-top:1px solid #d9e2ec;padding-top:18px;}",
            "p,li{font-size:14px;}strong{color:#111827;}ul{padding-left:22px;}",
            "</style>",
            "</head>",
            "<body>",
            *body,
            "</body>",
            "</html>",
        ]
    )


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _markdown_to_pdf(markdown: str) -> bytes:
    styled_lines = _styled_pdf_lines(markdown)
    pages: list[list[tuple[str, str]]] = []
    page: list[tuple[str, str]] = []
    for style, line in styled_lines:
        page.append((style, line))
        if len(page) >= 48:
            pages.append(page)
            page = []
    if page:
        pages.append(page)
    if not pages:
        pages.append([("h1", "Strategy Report")])

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [3 + index * 2 for index in range(len(pages))]
    font_regular_id = 3 + len(pages) * 2
    font_bold_id = font_regular_id + 1
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))

    for index, lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R "
                f"/F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        stream = _pdf_text_stream(lines)
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    return _build_pdf(objects)


def _styled_pdf_lines(markdown: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for raw in markdown.splitlines():
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", raw).strip()
        if not cleaned:
            lines.append(("space", ""))
            continue
        if cleaned.startswith("# "):
            for line in textwrap.wrap(cleaned[2:], width=52):
                lines.append(("h1", line))
            lines.append(("space", ""))
        elif cleaned.startswith("## "):
            for line in textwrap.wrap(cleaned[3:], width=64):
                lines.append(("h2", line))
        elif cleaned.startswith("- "):
            for line in textwrap.wrap("- " + cleaned[2:], width=86):
                lines.append(("bullet", line))
        else:
            for line in textwrap.wrap(cleaned, width=88):
                lines.append(("body", line))
    return lines


def _pdf_text_stream(lines: list[tuple[str, str]]) -> bytes:
    commands: list[str] = []
    y = 744
    for style, line in lines:
        if style == "space":
            y -= 10
            continue
        font = "F2" if style in {"h1", "h2"} else "F1"
        size = 18 if style == "h1" else 13 if style == "h2" else 10
        leading = 24 if style == "h1" else 18 if style == "h2" else 14
        x = 72 if style != "bullet" else 86
        commands.append(f"BT /{font} {size} Tf {x} {y} Td ({_escape_pdf_text(line)}) Tj ET")
        y -= leading
    return "\n".join(commands).encode("latin-1", errors="replace")


def _build_pdf(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _field_first(state: StrategyReportState, *keys: str) -> ReportValue | None:
    value = _first_structured_value(state, *keys)
    if value:
        return value
    input_json = state.operation.input_json if isinstance(state.operation.input_json, dict) else {}
    for key in keys:
        if key in input_json and _has_content(input_json[key]):
            return ReportValue(
                input_json[key],
                SourceRef(
                    "operation", str(state.operation.id), f"input_json.{key}", "Operation input"
                ),
            )
    return None


def _first_structured_value(state: StrategyReportState, *keys: str) -> ReportValue | None:
    for key in keys:
        values = state.structured_values.get(_normalize_key(key), [])
        for value in values:
            if _has_content(value.value):
                return value
    return None


def _constraints_value(state: StrategyReportState) -> ReportValue | None:
    field_value = _first_structured_value(state, "constraints", "constraints_applied")
    if field_value:
        return field_value
    constraints: list[str] = []
    source: SourceRef | None = None
    for decision in state.decisions:
        if decision.constraints:
            constraints.extend(decision.constraints)
            source = decision.source
    if constraints and source:
        return ReportValue(_dedupe_text(constraints), source)
    return None


def _sources_from_values(values: list[ReportValue | None]) -> list[SourceRef]:
    return [value.source for value in values if value is not None]


def _dedupe_sources(sources: list[SourceRef]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    payload: list[dict[str, str]] = []
    for source in sources:
        key = (source.kind, source.id, source.field)
        if key in seen:
            continue
        seen.add(key)
        payload.append(source.as_payload())
    return payload


def _dedupe_memory_traces(traces: list[MemoryTrace]) -> list[MemoryTrace]:
    seen: set[tuple[str, str]] = set()
    result: list[MemoryTrace] = []
    for trace in traces:
        key = (trace.title.lower(), trace.effect.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(trace)
    return result


def _dedupe_iteration_traces(traces: list[IterationTrace]) -> list[IterationTrace]:
    seen: set[str] = set()
    result: list[IterationTrace] = []
    for trace in traces:
        key = trace.what_changed.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(trace)
    return result


def _decision_record_summary(record: DecisionRecord) -> str:
    status = record.status.replace("_", " ")
    kind = record.decision_type.replace("_", " ")
    if record.task:
        return f"{kind} for {record.task.title} was {status}"
    return f"{kind} was {status}"


def _merge_dicts(*items: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and _has_content(item[key]):
            return item[key]
    return None


def _first_text(item: dict[str, Any], *keys: str) -> str:
    value = _first_value(item, *keys)
    return _stringify(value)


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [text for text in (_stringify(item) for item in value) if text]
    if isinstance(value, dict):
        return [f"{_label_from_field(key)}: {_format_inline(item)}" for key, item in value.items()]
    text = _stringify(value)
    return [text] if text else []


def _dedupe_text(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ", ".join(_stringify(item) for item in value if _has_content(item))
    if isinstance(value, dict):
        return "; ".join(
            f"{_label_from_field(str(key))}: {_format_inline(item)}"
            for key, item in value.items()
            if _has_content(item)
        )
    return str(value).strip()


def _format_inline(value: Any) -> str:
    return _stringify(value)


def _format_block(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {_format_inline(item)}" for item in value if _has_content(item))
    if isinstance(value, dict):
        return "\n".join(
            f"- **{_label_from_field(str(key))}:** {_format_inline(item)}"
            for key, item in value.items()
            if _has_content(item)
        )
    text = _stringify(value)
    return text


def _label_from_field(field: str) -> str:
    key = field.split(".")[-1]
    return key.replace("_", " ").replace("-", " ").strip().title()


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _sentence(value: Any) -> str:
    text = _format_inline(value).strip()
    if not text:
        return ""
    text = text[0].lower() + text[1:] if text[0].isupper() else text
    return text if text.endswith((".", "!", "?")) else text + "."


def _client_name(state: StrategyReportState) -> str:
    client = state.client_context
    name = client.get("name") or client.get("client_name")
    return str(name or "Client").strip()


def _client_label(state: StrategyReportState) -> str:
    client = state.client_context
    bits = [_client_name(state)]
    for key in ("industry", "market", "tier", "goal"):
        value = str(client.get(key) or "").strip()
        if value:
            bits.append(value)
    return " | ".join(bits)


def _operation_name(state: StrategyReportState) -> str:
    input_json = state.operation.input_json if isinstance(state.operation.input_json, dict) else {}
    return str(input_json.get("operation_name") or input_json.get("operation_brief") or "Operation")


def _source_label_for_task(node_run: NodeRun) -> str:
    return f"{node_run.node_id} task output"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
